const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const patch = require('../../static/dashboard_live_map_patch.js');

assert.equal(patch.liveNodeEligible({device_id:'A',status:'online',is_listening:true}), true);
assert.equal(patch.liveNodeEligible({device_id:'A',status:'event',is_listening:false}), false);
assert.equal(patch.liveNodeEligible({device_id:'A',status:'event',websocket_connected:false}), false);
assert.equal(patch.liveNodeEligible({device_id:'A',status:'online',recording:false,detection_enabled:false}), true,
    'phase telemetry may be idle while an accepted event is processing/uploading');
assert.equal(patch.liveNodeEligible({device_id:'A',status:'online',recording:false,detection_enabled:true}), true);
assert.equal(patch.liveNodeEligible({device_id:'A',status:'online',app_status:'stopped'}), false);

const group = {
    id:'g-stop', status:'ACTIVE', label:'Drone',
    reporting_device_ids:['node_A01','node_A02'],
    last_event_time:'2026-10-06T17:30:00Z',
    region_center_lat:25.0, region_center_lng:121.0,
    alert_accepted_in_time:true,
    alert_expires_at:'2026-10-06T17:31:00Z'
};
const devices = [
    {device_id:'node_A01',status:'online',is_listening:true,recording:true,detection_enabled:true,lat:25,lng:121},
    {device_id:'node_A02',status:'online',is_listening:false,recording:false,detection_enabled:false,lat:25.001,lng:121.001}
];
assert.deepEqual(patch.liveGroupDeviceIdsFrom(group,devices),['node_A01']);
assert.deepEqual(patch.sanitizeGroupForLive(group,devices).active_device_ids,['node_A01']);
assert.equal(patch.sanitizeEventsForLive([
    {event_id:'e1',device_id:'node_A01'},
    {event_id:'e2',device_id:'node_A02'}
],devices).length,1);

const source = fs.readFileSync(path.join(__dirname, '../../static/dashboard_live_map_patch.js'), 'utf8');
const now = Date.parse('2026-10-06T17:30:10Z');
const events = [
    {event_id:'e1',device_id:'node_A01',timestamp:'2026-10-06T17:30:09Z',classification:{model_label:'Drone'},alert_accepted_in_time:true,alert_expires_at:'2026-10-06T17:31:00Z'},
    {event_id:'e2',device_id:'node_A02',timestamp:'2026-10-06T17:30:09Z',classification:{model_label:'Drone'},alert_accepted_in_time:true,alert_expires_at:'2026-10-06T17:31:00Z'}
];
const state = {events,groups:new Map([[group.id,group]]),selectedGroupId:null,runtime:{critical_path_diagnostics_enabled:false}};
let renderSnapshot = null;
const timestamp = value => {
    const parsed = Date.parse(value || '');
    return Number.isFinite(parsed) ? parsed : null;
};
const context = vm.createContext({
    console, Date, Map, Set, Number, String, Math, Object, Array,
    document:{getElementById:()=>null},
    DashboardMapVisuals:{MOTION_DURATION_MS:850,LIVE_MOTION_DURATION_MS:200},
    DashboardNodeGeometry:{alertFresh:(value,fallback,current,duration)=>{
        const expires=timestamp(value?.alert_expires_at);
        if(expires!==null)return value?.alert_accepted_in_time!==false&&current<=expires;
        return Number.isFinite(fallback)&&current-fallback>=-2000&&current-fallback<=duration;
    }},
    state,
    canonicalDevices:()=>devices,
    classLabel:event=>event?.classification?.model_label || event?.label,
    eventTime:event=>timestamp(event?.timestamp),
    nodeLocation:device=>device?{lat:device.lat,lng:device.lng}:null,
    deviceOnline:device=>['online','event','connected','listening'].includes(String(device?.status||'').toLowerCase()),
    groupDeviceIds:item=>item?.active_device_ids ?? item?.reporting_device_ids ?? [],
    groupLocation:item=>Number.isFinite(item?.region_center_lat)&&Number.isFinite(item?.region_center_lng)?{lat:item.region_center_lat,lng:item.region_center_lng}:null,
    groupTime:item=>timestamp(item?.last_event_time)||0,
    isLiveTargetGroup:item=>String(item?.label||'').toLowerCase()==='drone',
    liveDroneSensorEvidence:()=>[],
    freshBackendMultiNodeEvidence:()=>true,
    freshBackendLocatedGroup:()=>true,
    selectedOrLatestGroup:()=>group,
    isFreshLiveTrack:()=>true,
    renderMap:()=>{
        renderSnapshot={
            group:[...state.groups.values()][0],
            events:[...state.events]
        };
    },
    handleWebSocketMessage:data=>data,
    renderLatencyDiagnostics:()=>undefined,
    performance:{now:()=>0},
    requestAnimationFrame:callback=>{callback(16);return 1;},
    setTimeout:callback=>{callback();return 1;}
});
vm.runInContext(source,context);

assert.equal(context.liveDroneSensorEvidence(now).length,1,'stopped node cannot remain live event evidence');
assert.equal(context.freshBackendMultiNodeEvidence(now),false,'one listening node is not multi-node evidence');
assert.equal(context.freshBackendLocatedGroup(now),false,'stopped member cannot keep a located multi-node warning alive');
context.renderMap();
assert.deepEqual(Array.from(renderSnapshot.group.active_device_ids),['node_A01'],'render path strips stopped group members');
assert.deepEqual(Array.from(renderSnapshot.events).map(item=>item.event_id),['e1'],'render path strips stopped-node events');
assert.equal(state.groups.get(group.id),group,'render filtering is presentation-only and does not mutate stored history');
assert.equal(state.events.length,2,'render filtering restores the canonical event cache');

devices[0].is_listening=false;
devices[0].recording=false;
devices[0].detection_enabled=false;
assert.equal(context.selectedOrLatestGroup(),null,'no live group remains once every node is explicitly stopped');
assert.equal(context.isFreshLiveTrack({id:'t1',group_id:'g-stop',status:'active',last_event_time:now},now),false,
    'track associated with an all-stopped group is no longer a live-map source');

console.log('Dashboard live node-stop handling passed');
