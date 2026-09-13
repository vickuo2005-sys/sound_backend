const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const html = fs.readFileSync(path.join(__dirname, '../../templates/dashboard_v2_4.html'), 'utf8');

// Exercise the actual template functions, including the API and WebSocket entry points.
// A missing/renamed function fails this extraction instead of testing a copied implementation.
function include(context, name) {
    const declaration = new RegExp(`^ {8}(?:async )?function ${name}\\(`, 'm');
    const start = html.search(declaration);
    assert(start >= 0, `Template function ${name} must exist`);
    const rest = html.slice(start + 1);
    const next = rest.search(/^ {8}(?:async )?function /m);
    assert(next >= 0, `Template function ${name} must have a following declaration`);
    vm.runInContext(html.slice(start, start + 1 + next), context, {filename: `template:${name}`});
}

const fixed = {device_id: 'node_A01', latitude: 25, longitude: 121, accuracy_m: 4};
const oldDevice = {
    device_id: 'node_A01', status: 'offline', fixed_latitude: 25, fixed_longitude: 121,
    marker_latitude: 25, marker_longitude: 121, effective_latitude: 25, effective_longitude: 121,
};
const clearedDevice = {
    device_id: 'node_A01', status: 'online', fixed_latitude: null, fixed_longitude: null,
    fixed_location_accuracy_m: null, marker_latitude: 26, marker_longitude: 122,
    effective_latitude: 26, effective_longitude: 122, effective_location_source: 'gps',
};

function harness(deleteDevice = null) {
    const pending = [];
    const writes = [];
    const toasts = [];
    const state = {
        locationsVersion: 0, snapshotInFlight: false, loaded: false, devicesAt: 0,
        devices: new Map([['node_A01', {...oldDevice}], ['node_A02', {device_id: 'node_A02'}]]),
        fixedLocations: new Map([['node_A01', {...fixed}]]),
        events: [], tracks: new Map(), groups: new Map(),
        locationEditDeviceId: 'node_A01', locationClearArmed: true,
    };
    const context = vm.createContext({
        state, Date, deviceSnapshotPollInFlight: false, locationTokenRequired: false,
        normalizeEvent: event => event, eventTime: event => Date.parse(event.timestamp),
        trackId: track => String(track.id), groupId: group => String(group.id),
        fetchJson: url => new Promise((resolve, reject) => pending.push({url, resolve, reject})),
        fetch: async (url, options) => {
            writes.push({url, options});
            return {ok: true, json: async () => ({status: 'success', device_id: 'node_A01', deleted: true, device: deleteDevice})};
        },
        locationRequestHeaders: () => ({'Content-Type': 'application/json'}),
        setLocationBusy: busy => {state.locationBusy = busy;},
        closeLocationEditor: () => {state.locationEditDeviceId = null;},
        shortNodeId: value => value,
        showToast: value => toasts.push(value),
        renderAll: () => {}, renderMetrics: () => {}, renderNodeStatus: () => {},
        renderNodesView: () => {}, renderHealth: () => {}, renderMap: () => {},
        renderCommandBar: () => {}, renderOverview: () => {},
    });
    ['finite', 'upsertDevice', 'updateFixedLocationCache', 'refreshSnapshot', 'refreshDeviceSnapshot',
        'clearFixedLocation', 'handleWebSocketMessage'].forEach(name => include(context, name));
    return {context, state, pending, writes, toasts};
}

function responseFor(url, devices = [oldDevice], locations = [fixed]) {
    if (url === '/device-status') return {devices};
    if (url === '/device-locations') return {status: 'success', device_locations: locations};
    if (url.startsWith('/events?')) return {events: []};
    if (url.startsWith('/tracks?')) return {tracks: []};
    if (url.startsWith('/event-groups?')) return {event_groups: []};
    if (url === '/health') return {status: 'ok'};
    if (url === '/runtime-status') return {app_env: 'staging'};
    throw new Error(`Unexpected read ${url}`);
}

function assertCleared(h, hasStatus) {
    assert.equal(h.state.fixedLocations.has('node_A01'), false, 'Fixed configuration must stay removed');
    assert.equal(h.state.devices.has('node_A01'), hasStatus, 'Configuration-only nodes must disappear; reported devices remain');
    if (hasStatus) {
        const current = h.state.devices.get('node_A01');
        assert.equal(current.fixed_latitude, null, 'Cleared fixed fields must not be restored');
        assert.equal(current.marker_latitude, 26, 'The reported GPS marker must survive the old snapshot');
        assert.equal(current.effective_longitude, 122);
    }
}

async function clearDuringSnapshot(kind, hasStatus) {
    const h = harness(hasStatus ? clearedDevice : null);
    const request = kind === 'full' ? h.context.refreshSnapshot('periodic') : h.context.refreshDeviceSnapshot();
    assert.equal(h.pending.length, kind === 'full' ? 7 : 1);
    await h.context.clearFixedLocation();
    assertCleared(h, hasStatus);
    assert.equal(h.state.locationsVersion, 1, 'Every successful location clear invalidates in-flight snapshots');
    assert.equal(h.pending.length, kind === 'full' ? 7 : 1, 'Clear does not start a competing refresh');
    assert.equal(h.writes.length, 1);
    assert.equal(h.writes[0].url, '/device-locations/node_A01');
    assert.equal(h.writes[0].options.method, 'DELETE');

    // These replies were captured before DELETE committed and still contain the old position.
    h.pending.forEach(p => p.resolve(responseFor(p.url)));
    await request;
    assertCleared(h, hasStatus);
    assert.equal(h.state.devices.has('node_A02'), true, 'Discarding a stale reply must not erase unrelated current state');
    assert.equal(h.state.snapshotInFlight, false);
    assert.equal(h.context.deviceSnapshotPollInFlight, false, 'Discarded polls release their in-flight guard');
    assert(!h.toasts.some(text => text.includes('失敗')), 'Successful DELETE must not fall into its error path');

    // The guard is a race check, not a permanent refusal to update future snapshots.
    const count = h.pending.length;
    const next = h.context.refreshSnapshot('periodic');
    const newDevice = {device_id: 'node_A03', status: 'online'};
    h.pending.slice(count).forEach(p => p.resolve(responseFor(p.url, [newDevice], [])));
    await next;
    assert.equal(h.state.devices.has('node_A03'), true, 'A later current snapshot must be accepted');
    assert.equal(h.state.fixedLocations.size, 0);
}

(async () => {
    const websocket = harness();
    websocket.context.handleWebSocketMessage({type: 'device_location_updated', device_id: 'node_A01', device: null});
    assertCleared(websocket, false);
    assert.equal(websocket.state.locationsVersion, 1, 'Null WebSocket payload also invalidates old requests');
    assert.equal(websocket.state.devices.has('node_A02'), true);

    for (const kind of ['full', 'device']) {
        for (const hasStatus of [false, true]) await clearDuringSnapshot(kind, hasStatus);
    }

    // A normal snapshot still replaces old saved positions when no local write raced it.
    const normal = harness();
    const current = normal.context.refreshSnapshot();
    const newFixed = {...fixed, latitude: 27, longitude: 123};
    normal.pending.forEach(p => p.resolve(responseFor(p.url, [oldDevice], [newFixed])));
    await current;
    assert.equal(normal.state.fixedLocations.get('node_A01').latitude, 27);

    let activeReplay = true;
    let clearCalls = 0;
    let legacyClearCalls = 0;
    const replay = vm.createContext({
        window: {DashboardOperationsUI: {clear: () => {clearCalls++; activeReplay = false;}}},
        state: {selectedTrackId: 'track-1'},
        clearTrackReplayObjects: () => {legacyClearCalls++;},
        renderTracksView: () => {}, renderMap: () => {},
    });
    include(replay, 'closeTrackReplay');
    replay.closeTrackReplay();
    assert.equal(clearCalls, 1, 'Close must delegate to the new history player cleanup');
    assert.equal(activeReplay, false);
    assert.equal(legacyClearCalls, 1, 'Legacy map replay overlays still get cleaned up');
    assert.equal(replay.state.selectedTrackId, null);

    console.log('Location synchronization: null-device DELETE/WS, both snapshot races, fresh refresh and replay-close cleanup passed');
})().catch(error => {console.error(error); process.exitCode = 1;});
