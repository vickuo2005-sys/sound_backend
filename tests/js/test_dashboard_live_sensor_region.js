const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const geometry=require('../../static/dashboard_node_geometry');
const patch=require('../../static/dashboard_live_map_patch');
const html=fs.readFileSync(path.join(__dirname,'../../templates/dashboard_v2_4.html'),'utf8');
const now=Date.now();
const nodes=[0,1,2,3].map(i=>({device_id:`node_A0${i+1}`,status:'online',is_listening:true,
    marker_latitude:25+(i>=2?.01:0),marker_longitude:121+(i%2?.01:0),
    detection_state:{active:true,sequence:10,received_at_ms:now,observed_at_ms:now+3600000,label:'Drone'}}));
const storedGroup={id:'old-four',status:'ACTIVE',label:'Drone',reporting_device_ids:nodes.map(n=>n.device_id),
    region_center_lat:25.005,region_center_lng:121.005,last_event_time:new Date(now).toISOString()};
const storedTrack={id:'old-track',label:'Drone',status:'ACTIVE',recent_points:[{lat:25.005,lng:121.005}]};
const state={runtime:{localization_enabled:false},groups:new Map([[storedGroup.id,storedGroup]]),
    tracks:new Map([[storedTrack.id,storedTrack]]),events:[],selectedGroupId:null};
let renderedGroups;
class Marker{
    constructor(options){this.setOptions(options);}
    setOptions(options){Object.assign(this,options);}
    setMap(map){this.map=map;}
    getMap(){return this.map;}
    setPosition(position){this.position=position;}
    setIcon(icon){this.icon=icon;}
    setTitle(title){this.title=title;}
    setOpacity(opacity){this.opacity=opacity;}
    addListener(){}
}
const context=vm.createContext({console,Date,Map,Set,Number,String,Math,Object,Array,
    document:{getElementById:()=>({classList:{contains:()=>true}})},
    google:{maps:{Marker,Polyline:Marker,Circle:Marker}},map:{},state,DashboardNodeGeometry:geometry,
    nodeMarkers:new Map(),trackMarkers:new Map(),trackLines:new Map(),trackDirectionLines:new Map(),
    estimateMarker:null,estimateCircle:null,detectionMarker:null,uncertaintyCircle:null,
    canonicalDevices:()=>nodes,deviceOnline:device=>device.status==='online',
    nodeLocation:geometry.nodePosition,nodeState:()=>({text:'online'}),shortNodeId:id=>id,
    nodeMarkerIcon:()=>({}),v22DroneTargetIcon:()=>({}),simulationIsVisible:()=>false,
    groupLocation:g=>g?{lat:g.region_center_lat,lng:g.region_center_lng}:null,
    groupTime:g=>Date.parse(g.last_event_time),groupLabel:g=>g.label,
    isLiveTargetGroup:()=>true,isLiveTargetLabel:()=>true,trackPath:t=>t?.recent_points||[],
    liveDroneSensorEvidence:()=>[],liveSensorFallbackEstimate:()=>null,
    freshBackendLocatedGroup:()=>true,freshBackendMultiNodeEvidence:()=>true,
    selectedOrLatestGroup:()=>storedGroup,isFreshLiveTrack:()=>true,
    finite:v=>v==null?null:Number(v),setLiveMarkerTarget:(_key,marker,target)=>marker.setPosition(target),
    clearLiveMarkerMotion:()=>{},trackHeading:()=>null,
    nodeAlertRenderer:{update:input=>{renderedGroups=input.groups;return geometry.buildGeometries(input);}}
});
context.window=context;
function include(name){
    const start=html.search(new RegExp(`^ {8}(?:async )?function ${name}\\(`,'m'));
    assert(start>=0,`actual template function ${name} exists`);
    const tail=html.slice(start+1),next=tail.search(/^ {8}(?:async )?function |^ {8}window\./m);
    vm.runInContext(html.slice(start,start+1+next),context);
}
include('renderMap');
vm.runInContext(fs.readFileSync(path.join(__dirname,'../../static/dashboard_live_map_patch.js'),'utf8'),context);
const groups=state.groups,tracks=state.tracks,events=state.events;
for(const count of [4,3,2,1,0,2,4]){
    nodes.forEach((node,i)=>node.detection_state={...node.detection_state,active:i<count,sequence:node.detection_state.sequence+1});
    context.renderMap();
    assert.equal(state.groups,groups,'display must preserve backend history');
    assert.equal(state.tracks,tracks);
    assert.equal(state.events,events);
    assert.equal(context.trackMarkers.size,0,'old track cannot pin the current region center');
    if(!count){assert.equal(context.estimateMarker,null);assert.equal(renderedGroups.length,0);continue;}
    const center=geometry.nodePosition(nodes[0]);
    center.lat=nodes.slice(0,count).reduce((sum,n)=>sum+n.marker_latitude/count,0);
    center.lng=nodes.slice(0,count).reduce((sum,n)=>sum+n.marker_longitude/count,0);
    assert.deepEqual(JSON.parse(JSON.stringify(context.estimateMarker.position)),center,`${count} current sensors determine the display center`);
    assert.match(context.estimateMarker.title,/非無人機定位/);
    assert.deepEqual(Array.from(renderedGroups[0].active_device_ids),nodes.slice(0,count).map(n=>n.device_id));
    assert(!Number.isNaN(Date.parse(renderedGroups[0].last_event_time)));
    assert(Date.parse(renderedGroups[0].last_event_time)<=Date.now(),'phone clock skew must not set region freshness');
}
// Localization mode must retain the existing backend group/track arbitration.
state.runtime.localization_enabled=true;
assert.equal(context.selectedOrLatestGroup().id,storedGroup.id);
assert.equal(context.isFreshLiveTrack(storedTrack),true);
nodes.forEach(n=>n.detection_state.received_at_ms=now-5000);
state.runtime.localization_enabled=false;
assert.equal(context.selectedOrLatestGroup(),null,'stale true states cannot freeze a target');
assert.equal(patch.sensorRegionFromEvidence([{device:{device_id:'bad'},position:{lat:Infinity,lng:121}}]),null);
console.log('Live region map: 4→3→2→1→0→2→4, stored track precedence, history, clock skew and localization isolation passed');
