const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const html = fs.readFileSync(path.join(__dirname, '../../templates/dashboard_v2_4.html'), 'utf8');
function include(context, name) {
    const match = html.match(new RegExp(`        (?:async )?function ${name}\\([^]*?\\n        }`));
    assert(match, `Missing production function ${name}`);
    vm.runInContext(match[0], context, {filename: `template:${name}`});
}
const event = (id, seconds, extra = {}) => ({
    event_id: id, device_id: 'node_A01', timestamp: new Date(seconds * 1000).toISOString(), ...extra,
});
function harness(initial = []) {
    const pending = [];
    const state = {
        events: initial, devices: new Map(), fixedLocations: new Map(), tracks: new Map(), groups: new Map(),
        locationsVersion: 0, latestDetectionOrder: -Infinity, snapshotInFlight: false,
    };
    const context = vm.createContext({
        state, Date, deviceSnapshotPollInFlight: false,
        eventTime: e => Date.parse(e.timestamp), trackId: t => String(t.id), groupId: g => String(g.id),
        fetchJson: url => new Promise((resolve, reject) => pending.push({url, resolve, reject})),
        renderAll() {}, showToast() {},
    });
    ['normalizeEvent', 'upsertEvent', 'upsertDevice', 'refreshSnapshot', 'handleWebSocketMessage']
        .forEach(name => include(context, name));
    return {state, context, pending};
}
function respond(p, events) {
    const payload = p.url.startsWith('/events?') ? {events}
        : p.url === '/device-status' ? {devices: []}
        : p.url === '/device-locations' ? {status: 'success', device_locations: []}
        : p.url.startsWith('/tracks?') ? {tracks: []}
        : p.url.startsWith('/event-groups?') ? {event_groups: []} : {status: 'ok'};
    p.resolve(payload);
}
function receive(h, e) { h.context.handleWebSocketMessage({type: 'event_trigger', event: e}); }
const ids = h => Array.from(h.state.events, e => e.event_id);

(async () => {
    const h = harness([event('old', 1)]);
    const request = h.context.refreshSnapshot('periodic');
    // /events has already replied, while a slower track request still holds the snapshot open.
    respond(h.pending.find(p => p.url.startsWith('/events?')), [event('old', 1)]);
    await Promise.resolve();
    receive(h, event('live', 3));
    assert.deepEqual(ids(h), ['live', 'old']);
    h.pending.filter(p => !p.url.startsWith('/events?')).forEach(p => respond(p, []));
    await request;
    assert.deepEqual(ids(h), ['live', 'old'], 'A slow snapshot must not remove a new WebSocket event');
    assert.equal(h.state.latestDetectionOrder, 3000, 'Latest detection ordering must not move backwards');

    // A later snapshot is authoritative again: the race protection must not pin events forever.
    const count = h.pending.length;
    const next = h.context.refreshSnapshot('periodic');
    h.pending.slice(count).forEach(p => respond(p, [event('server', 4)]));
    await next;
    assert.deepEqual(ids(h), ['server']);

    const update = harness([event('same', 1, {audio_path: 'old.mp3'})]);
    const updating = update.context.refreshSnapshot();
    receive(update, event('same', 2, {label: 'Drone', note: 'first'}));
    receive(update, event('same', 3, {note: 'latest'}));
    update.pending.forEach(p => respond(p, [event('same', 1, {label: 'Car', audio_path: 'ready.mp3'})]));
    await updating;
    assert.equal(update.state.events.length, 1, 'Duplicate IDs must merge');
    assert.equal(update.state.events[0].label, 'Drone');
    assert.equal(update.state.events[0].note, 'latest');
    assert.equal(update.state.events[0].audio_path, 'ready.mp3', 'Snapshot enrichment must survive partial live updates');
    assert.equal(update.state.events[0].timestamp, event('same', 3).timestamp);

    const failed = harness([event('old', 1)]);
    const failing = failed.context.refreshSnapshot();
    receive(failed, event('live', 2));
    failed.pending.forEach(p => p.url.startsWith('/events?') ? p.reject(new Error('offline')) : respond(p, []));
    await failing;
    assert.deepEqual(ids(failed), ['live', 'old'], 'Failed reads must leave live events intact');
    assert.equal(failed.state.eventsFailed, true);
    const retryCount = failed.pending.length;
    const retry = failed.context.refreshSnapshot();
    failed.pending.slice(retryCount).forEach(p => respond(p, [event('recovered', 3)]));
    await retry;
    assert.deepEqual(ids(failed), ['recovered'], 'Failed-request updates must not leak into subsequent snapshots');
    assert.equal(failed.state.eventsFailed, false);

    const burst = harness();
    const bursting = burst.context.refreshSnapshot();
    for (let i = 0; i < 220; i++) receive(burst, event(`live-${i}`, i + 1));
    burst.pending.forEach(p => respond(p, [event('old', 0)]));
    await bursting;
    assert.equal(burst.state.events.length, 200, 'Merged events must retain the existing cache limit');
    assert.equal(burst.state.events[0].event_id, 'live-219');
    assert.equal(burst.state.events.at(-1).event_id, 'live-20');
    console.log('Event synchronization: delayed snapshot, live updates, deduplication, enrichment, failure recovery and bounded ordering passed');
})().catch(error => {console.error(error); process.exitCode = 1;});
