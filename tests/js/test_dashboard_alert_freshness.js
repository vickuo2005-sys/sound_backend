const assert = require('node:assert/strict');
const visuals = require('../../static/dashboard_map_visuals.js');
const geometry = require('../../static/dashboard_node_geometry.js');

const now = Date.parse('2026-10-06T00:00:30Z');
const iso = value => new Date(value).toISOString();
const nodes = [
    {device_id:'node_A01',status:'online',marker_latitude:25.0,marker_longitude:121.0},
    {device_id:'node_A02',status:'online',marker_latitude:25.001,marker_longitude:121.001}
];
const lateOccurrence = now - 23000;
const expiresAt = now + 7000;

// Live-map smoothing must not add almost another second after the backend has
// already delivered a new target position.
assert(visuals.MOTION_DURATION_MS > 0 && visuals.MOTION_DURATION_MS <= 250,
    `live marker motion is too slow: ${visuals.MOTION_DURATION_MS} ms`);

const acceptedLateEvent = {
    event_id:'late-event',
    device_id:'node_A01',
    timestamp:iso(lateOccurrence),
    classification:{model_label:'Drone',is_target:true},
    alert_accepted_in_time:true,
    alert_expires_at:iso(expiresAt)
};
assert.equal(geometry.buildGeometries({nodes,groups:[],events:[acceptedLateEvent],now}).length,1,
    'backend-accepted late events stay visible through alert_expires_at');

assert.equal(geometry.buildGeometries({nodes,groups:[],events:[{
    ...acceptedLateEvent,
    event_id:'rejected-event',
    alert_accepted_in_time:false
}],now}).length,0,'backend-rejected events must not be revived by the frontend');

assert.equal(geometry.buildGeometries({nodes,groups:[],events:[{
    ...acceptedLateEvent,
    event_id:'expired-event',
    alert_expires_at:iso(now-1)
}],now}).length,0,'accepted alerts disappear after backend alert_expires_at');

const acceptedLateGroup = {
    id:'late-group',
    status:'ACTIVE',
    label:'Drone',
    first_event_time:iso(lateOccurrence-1000),
    last_event_time:iso(lateOccurrence),
    region_updated_at:iso(now-1000),
    reporting_device_ids:['node_A01','node_A02'],
    active_device_ids:['node_A01','node_A02'],
    alert_accepted_in_time:true,
    alert_expires_at:iso(expiresAt)
};
const lateGroupGeometry = geometry.buildGeometries({nodes,groups:[acceptedLateGroup],events:[],now});
assert.equal(lateGroupGeometry.length,1);
assert.equal(lateGroupGeometry[0].kind,'line');
assert.equal(lateGroupGeometry[0].expiresAt,expiresAt,
    'renderer expiry follows the backend alert contract, not sound occurrence + 15s');

assert.equal(geometry.buildGeometries({nodes,groups:[{...acceptedLateGroup,status:'CLOSED'}],events:[],now}).length,0,
    'closed groups are never revived even with a future alert expiry');

// Backward compatibility: payloads without the new timing fields retain the
// previous 15-second occurrence-time fallback.
assert.equal(geometry.buildGeometries({nodes,groups:[],events:[{
    event_id:'legacy-late',device_id:'node_A01',timestamp:iso(lateOccurrence),
    classification:{model_label:'Drone',is_target:true}
}],now}).length,0,'old payloads keep the legacy freshness fallback');

console.log('Dashboard alert contract and live-map latency guards passed');
