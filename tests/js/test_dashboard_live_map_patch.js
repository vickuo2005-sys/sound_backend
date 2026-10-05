const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const patch = require('../../static/dashboard_live_map_patch.js');
assert.equal(patch.nearestRank([1,2,3,4,5], .95), 5);
assert.equal(patch.nearestRank([], .95), null);
const bounded = [];
for (let index = 0; index < 300; index++) patch.pushBounded(bounded, index, 256);
assert.equal(bounded.length, 256);
assert.equal(bounded[0], 44);

const source = fs.readFileSync(path.join(__dirname, '../../static/dashboard_live_map_patch.js'), 'utf8');
const now = Date.parse('2026-10-06T00:00:30Z');
const occurrence = now - 23000;
const expiry = now + 7000;
let perf = 100;
const group = {
    id:'g-late', status:'ACTIVE', label:'Drone',
    last_event_time:new Date(occurrence).toISOString(),
    region_updated_at:new Date(now - 1000).toISOString(),
    region_center_lat:25.0005, region_center_lng:121.0005,
    reporting_device_ids:['node_A01','node_A02'],
    alert_accepted_in_time:true,
    alert_expires_at:new Date(expiry).toISOString()
};
const lateEvent = {
    event_id:'event-late', device_id:'node_A01', timestamp:new Date(occurrence).toISOString(),
    classification:{model_label:'Drone'},
    alert_accepted_in_time:true,
    alert_expires_at:new Date(expiry).toISOString()
};
const state = {
    events:[lateEvent],
    groups:new Map([[group.id, group]]),
    selectedGroupId:null,
    runtime:{critical_path_diagnostics_enabled:true}
};
const devices = [
    {device_id:'node_A01',status:'online',lat:25,lng:121},
    {device_id:'node_A02',status:'online',lat:25.001,lng:121.001}
];
const timestamp = value => {
    const parsed = Date.parse(value || '');
    return Number.isFinite(parsed) ? parsed : null;
};
const context = vm.createContext({
    console,
    Date,
    Map,
    Set,
    Number,
    String,
    Math,
    Object,
    Array,
    performance:{now:()=>perf},
    requestAnimationFrame:callback=>{perf += 16; callback(perf); return 1;},
    setTimeout:(callback,delay)=>{perf += Number(delay)||0; callback(); return 1;},
    document:{getElementById:()=>null},
    DashboardMapVisuals:{MOTION_DURATION_MS:200},
    DashboardNodeGeometry:{
        alertFresh:(value,fallbackTime,current,duration)=>{
            const expires = timestamp(value?.alert_expires_at);
            if (expires !== null) return value?.alert_accepted_in_time !== false && current <= expires;
            return Number.isFinite(fallbackTime) && current - fallbackTime >= -2000 && current - fallbackTime <= duration;
        }
    },
    state,
    canonicalDevices:()=>devices,
    classLabel:event=>event?.classification?.model_label || event?.label,
    eventTime:event=>timestamp(event?.timestamp),
    nodeLocation:device=>device ? {lat:device.lat,lng:device.lng} : null,
    deviceOnline:device=>device?.status === 'online',
    groupDeviceIds:item=>item?.reporting_device_ids || [],
    groupLocation:item=>Number.isFinite(item?.region_center_lat) && Number.isFinite(item?.region_center_lng) ? {lat:item.region_center_lat,lng:item.region_center_lng} : null,
    groupTime:item=>timestamp(item?.region_updated_at || item?.last_event_time) || 0,
    isLiveTargetGroup:item=>String(item?.label || '').toLowerCase() === 'drone',
    liveDroneSensorEvidence:()=>[],
    freshBackendMultiNodeEvidence:()=>false,
    freshBackendLocatedGroup:()=>false,
    selectedOrLatestGroup:()=>null,
    handleWebSocketMessage:data=>data,
    renderLatencyDiagnostics:()=>undefined
});
vm.runInContext(source, context);

const evidence = context.liveDroneSensorEvidence(now);
assert.equal(evidence.length, 1, 'late but backend-accepted event remains live evidence');
assert.equal(context.freshBackendMultiNodeEvidence(now), true);
assert.equal(context.freshBackendLocatedGroup(now), true);
assert.equal(context.selectedOrLatestGroup().id, group.id);

context.handleWebSocketMessage({type:'event_group',group,critical_path:{event_id:'event-late'}});
assert.equal(state.browserGroupVisualSamples.length, 1);
const sample = state.browserGroupVisualSamples[0];
assert.equal(sample.event_id, 'event-late');
assert.equal(sample.next_paint_eligible_ms, 32);
assert.equal(sample.marker_settle_eligible_ms, 264);
assert.match(patch.percentileText([sample], 'marker_settle_eligible_ms'), /P95 264\.0/);

console.log('Dashboard live-map patch: backend freshness and browser visual milestones passed');
