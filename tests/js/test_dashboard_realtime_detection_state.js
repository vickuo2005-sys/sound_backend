const assert = require('node:assert/strict');
const patch = require('../../static/dashboard_live_map_patch.js');

const now = 1_800_000_000_000;
const freshTrue = {
    device_id:'node_A01',
    status:'online',
    websocket_connected:true,
    detection_state:{
        active:true,
        sequence:100,
        observed_at_ms:now-500,
        received_at_ms:now-100,
        label:'Drone',
        confidence:0.91
    }
};
const freshFalse = {
    device_id:'node_A02',
    status:'online',
    websocket_connected:true,
    detection_state:{
        active:false,
        sequence:101,
        observed_at_ms:now-450,
        received_at_ms:now-80,
        label:'Car',
        confidence:0.82
    }
};
const staleTrue = {
    device_id:'node_A03',
    status:'online',
    websocket_connected:true,
    detection_state:{
        active:true,
        sequence:99,
        observed_at_ms:now-6000,
        received_at_ms:now-patch.DETECTION_STATE_STALE_MS-1,
        label:'Drone',
        confidence:0.88
    }
};
const legacy = {
    device_id:'node_A04',
    status:'online',
    websocket_connected:true
};

let state = patch.realtimeDetectionState(freshTrue, now);
assert.equal(state.supported, true);
assert.equal(state.active, true, 'fresh positive inference lights immediately');
assert.equal(state.stale, false);
assert.equal(state.sequence, 100);
assert.equal(state.label, 'Drone');

state = patch.realtimeDetectionState(freshFalse, now);
assert.equal(state.supported, true);
assert.equal(state.active, false, 'negative inference dims immediately');
assert.equal(state.stale, false, 'negative is a valid current state, not stale');

state = patch.realtimeDetectionState(staleTrue, now);
assert.equal(state.supported, true);
assert.equal(state.active, false, 'missing future inference windows cannot leave a node lit forever');
assert.equal(state.stale, true);

state = patch.realtimeDetectionState(legacy, now);
assert.equal(state.supported, false, 'legacy nodes remain on the migration fallback path');

const group = {
    id:'g-realtime',
    reporting_device_ids:['node_A01','node_A02','node_A03','node_A04']
};
const activeIds = patch.liveGroupDeviceIdsFrom(group,[freshTrue,freshFalse,staleTrue,legacy],now);
assert.deepEqual(activeIds,['node_A01','node_A04'],
    'realtime-capable nodes obey current inference while legacy nodes retain runtime fallback');

const events = [
    {event_id:'old-positive-a01',device_id:'node_A01'},
    {event_id:'old-positive-a02',device_id:'node_A02'},
    {event_id:'old-positive-a03',device_id:'node_A03'},
    {event_id:'legacy-a04',device_id:'node_A04'}
];
const liveEvents = patch.sanitizeEventsForLive(events,[freshTrue,freshFalse,staleTrue,legacy],now);
assert.deepEqual(liveEvents.map(item=>item.event_id),['old-positive-a01','legacy-a04'],
    'historical events cannot revive a realtime-capable node after false or stale state');

const flat = {
    device_id:'node_A05',
    status:'online',
    detection_active:true,
    detection_sequence:55,
    detection_observed_at_ms:now-200,
    detection_state_received_at_ms:now-50,
    detection_label:'Airplane',
    detection_confidence:0.75
};
state = patch.realtimeDetectionState(flat,now);
assert.equal(state.supported,true);
assert.equal(state.active,true);
assert.equal(state.label,'Airplane');

const disconnected = {...freshTrue,websocket_connected:false};
assert.equal(patch.realtimeDetectionState(disconnected,now).active,false,
    'disconnect overrides the last positive inference state');

console.log('Dashboard realtime detection state: true/false, stale watchdog, legacy fallback and history suppression passed');
