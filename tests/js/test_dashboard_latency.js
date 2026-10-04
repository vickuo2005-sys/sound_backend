const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const html = fs.readFileSync(require('node:path').join(__dirname, '../../templates/dashboard_v2_4.html'), 'utf8');
let writes = 0, content = '', breakdownContent = '', now = 2000, socket, handled = [], fail = false;
const target = {set innerHTML(value) { writes++; content = value; }};
const breakdownTarget = {set innerHTML(value) { breakdownContent = value; }};
const context = vm.createContext({
    state: {browserMessageLatencySamples: [], runtime: null},
    document: {getElementById: id => id === 'latencyDiagnosticsBreakdown' ? breakdownTarget : target}, window: {},
    safe: value => String(value).replaceAll('<', '&lt;'),
    performance: {now: () => now}, location: {protocol: 'http:', host: 'localhost'},
    WebSocket: function () { socket = this; },
    handleWebSocketMessage: data => { handled.push(data); now += 2; if (fail) throw Error('handler failure'); },
    scheduleReconnect() {}, renderCommandBar() {}, renderHealth() {}, refreshSnapshot() {}
});
vm.runInContext(html.slice(html.indexOf('        function healthRow('), html.indexOf('        function renderHealth()')), context);
vm.runInContext(html.slice(html.indexOf('        function connectWebSocket()'), html.indexOf('        function scheduleReconnect()')), context);
context.renderLatencyDiagnostics();
assert.match(content, /尚無樣本/);
assert.match(breakdownContent, /Fusion · Lock wait/);
const good = {count: 10, p50_ms: 1, p95_ms: 2, p99_ms: 3};
for (const bad of [null, {}, {count: 1}, {...good, p95_ms: '2'}, {...good, p95_ms: NaN},
    {...good, p99_ms: Infinity}, {...good, p50_ms: -1}, {...good, count: '<img>'}, {...good, p50_ms: 4}]) {
    context.state.runtime = {latency_diagnostics: {stages: {event_db_write: bad}, pending_jobs: {post_ingest: '<img>', device_status: -1}}};
    assert.doesNotThrow(() => context.renderLatencyDiagnostics());
    assert.match(content, /尚無樣本/);
    assert.match(content, /post-ingest 0 · device-status 0/);
    assert(!content.includes('<img>'));
}
context.state.runtime = {latency_diagnostics: {stages: {event_db_write: good}, pending_jobs: {post_ingest: 3, device_status: 2}}};
context.renderLatencyDiagnostics();
assert.match(content, /P50 1 · P95 2 · P99 3 ms · n=10/);
assert.match(content, /post-ingest 3 · device-status 2/);
for (const bad of [null, -1, NaN, Infinity, '1']) context.recordBrowserMessageLatency(bad);
assert.equal(context.state.browserMessageLatencySamples.length, 0);
for (let n=0; n<300; n++) context.recordBrowserMessageLatency(n);
assert.equal(context.state.browserMessageLatencySamples.length, 256);
assert.equal(context.state.browserMessageLatencySamples[0], 44);
assert.equal(context.browserLatencyPercentile(.95), 287); // Browser uses nearest rank.
context.state.browserMessageLatencySamples = [];
context.connectWebSocket();
socket.onmessage({data: '{bad json'});
assert.equal(handled.length, 0);
assert.equal(context.state.browserMessageLatencySamples.length, 0);
writes = 0;
for (let n=0; n<1000; n++) socket.onmessage({data: JSON.stringify({type: 'event_trigger', id: n})});
assert.equal(handled.length, 1000);
assert.equal(handled[999].id, 999);
assert.equal(context.state.browserMessageLatencySamples.length, 256);
assert.equal(context.browserLatencyPercentile(.95), 2);
assert(writes <= 3, 'diagnostics panel is throttled during a high frequency burst');
fail = true;
assert.throws(() => socket.onmessage({data: '{}'}), /handler failure/);
assert.equal(context.state.browserMessageLatencySamples.at(-1), 2);
assert.match(content, /Browser message handler/);
assert(html.includes("fetchJson('/runtime-status')"));
assert(html.includes("setInterval(() => { refreshSnapshot('periodic').catch(() => { state.snapshotInFlight = false; }); }, 30000)"));
console.log('Latency dashboard: malformed API data, rolling samples, handler preservation, errors and 1000-message burst passed');

// Actual renderHealth calls use the shared diagnostics throttle; runtime refresh bypasses it.
context.state.runtime={latency_diagnostics:{stages:{event_db_write:good}}};
writes=0;
for(let n=0;n<1000;n++){now+=.01;context.renderLatencyDiagnostics(false);}
assert(writes<=2,'health rendering must not repaint diagnostics on every WS message');
const previousWrites=writes;
now+=1001;context.renderLatencyDiagnostics(false);assert.equal(writes,previousWrites+1);
context.state.runtime={latency_diagnostics:{stages:{event_db_write:good}}};
context.renderLatencyDiagnostics(false);assert.equal(writes,previousWrites+2,'new runtime snapshot renders immediately');

// Execute the production snapshot loader, including failed runtime requests.
const requested = [];
let rejectRuntime = false;
context.deviceSnapshotPollInFlight = false;
context.state.events = [];
context.state.devices = new Map();
context.state.tracks = new Map();
context.state.groups = new Map();
context.showToast = () => {};
context.renderAll = () => context.renderLatencyDiagnostics();
context.fetchJson = async url => {
    requested.push(url);
    if (url === '/runtime-status') {
        if (rejectRuntime) throw Error('runtime unavailable');
        return {latency_diagnostics: {stages: {event_db_write: good}}};
    }
    return {};
};
vm.runInContext(html.slice(html.indexOf('        async function refreshSnapshot('), html.indexOf('        async function refreshDeviceSnapshot(')), context);
(async () => {
    await context.refreshSnapshot('periodic');
    assert(requested.includes('/runtime-status'));
    assert.match(content, /P50 1 · P95 2 · P99 3 ms · n=10/);
    rejectRuntime = true;
    await context.refreshSnapshot('periodic');
    assert.equal(context.state.runtime, null);
    assert.equal(context.state.snapshotInFlight, false);
    assert.match(content, /尚無樣本/);
    // Reproduce coincident 5s device / 30s runtime timers. Both successful and
    // failed device polls must release a deferred full refresh exactly once.
    vm.runInContext(html.slice(html.indexOf('        async function refreshDeviceSnapshot('), html.indexOf('        function renderOverview(')), context);
    for (const name of ['renderMetrics','renderNodeStatus','renderNodesView','renderHealth','renderMap','renderCommandBar','renderOverview']) context[name] = () => {};
    for (const pollFails of [false, true]) {
        let finishPoll;
        let runtimeCalls = 0;
        context.fetchJson = url => {
            if (url === '/device-status' && !context.state.snapshotInFlight)
                return new Promise((resolve, reject) => { finishPoll = () => pollFails ? reject(Error('poll failed')) : resolve({devices: []}); });
            if (url === '/runtime-status') {
                runtimeCalls++;
                return Promise.resolve({latency_diagnostics: {stages: {event_db_write: {...good, count: 11}}}});
            }
            return Promise.resolve({});
        };
        const polling = context.refreshDeviceSnapshot();
        await context.refreshSnapshot('periodic');
        await context.refreshSnapshot('periodic');
        assert.equal(runtimeCalls, 0, 'full refresh waits for device poll');
        finishPoll();
        await polling;
        assert.equal(runtimeCalls, 1, 'coalesced full refresh must not be lost');
        assert.equal(context.state.pendingSnapshotReason, null);
        assert.equal(context.deviceSnapshotPollInFlight, false);
        assert.match(content, /n=11/);
    }
    console.log('Coincident 5s/30s polling, coalescing and failure recovery passed');
    console.log('Runtime snapshot API loading and failure recovery passed');
})().catch(error => { console.error(error); process.exitCode = 1; });
