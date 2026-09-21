const assert = require('node:assert/strict');
const geometry = require('../../static/dashboard_node_geometry.js');
const now = Date.parse('2026-09-13T12:00:00Z');
const iso = time => new Date(time).toISOString();
const nodes = [
    {device_id:'node_A01',status:'offline',marker_latitude:25,marker_longitude:121},
    {device_id:'node_A02',status:'online',marker_latitude:25,marker_longitude:121.01},
    {device_id:'node_A03',status:'online',marker_latitude:25.01,marker_longitude:121.005},
    {device_id:'node_A04',status:'online',marker_latitude:25.003,marker_longitude:121.005}
];
const drone = (device_id,extra={}) => ({event_id:`event-${device_id}`,device_id,timestamp:iso(now-1000),classification:{model_label:'Drone',is_target:true},...extra});
const group = extra => ({id:'g1',status:'ACTIVE',label:'aircraft',first_event_time:iso(now-3000),last_event_time:iso(now),reporting_device_ids:nodes.map(n=>n.device_id),...extra});
const input = {nodes,groups:[group()],events:nodes.map(n=>drone(n.device_id)),now};

for (const bad of [null,undefined,'','  ',true,false,[],{},Infinity,'NaN']) {
    assert.equal(geometry.coordinate(bad,121),null);
    assert.equal(geometry.coordinate(25,bad),null);
}
for (const pair of [[91,121],[25,181],[-91,121],[25,-181]]) assert.equal(geometry.coordinate(...pair),null);
assert.deepEqual(geometry.coordinate('25.1','121.2'),{lat:25.1,lng:121.2});
assert.deepEqual(geometry.coordinate(0,0),{lat:0,lng:0});

const telemetry = Object.freeze([{device_id:'node_A01',status:'offline',reported:true,is_listening:false,latitude:24,longitude:120}].map(Object.freeze));
const fixed = Object.freeze([{device_id:'node_A01',latitude:25,longitude:121,location_source:'manual_map'},
    {device_id:'node_A05',latitude:25.02,longitude:121.02}].map(Object.freeze));
const persistent = geometry.mergeFixedNodes(telemetry,fixed,['node_A01','node_A02']);
assert.equal(persistent.length,3);
assert.equal(persistent[0].status,'offline');
assert.equal(persistent[0].reported,true);
assert.equal(persistent[0].latitude,24,'raw telemetry is retained');
assert.equal(persistent[0].fixed_latitude,25);
assert.deepEqual(geometry.nodePosition(persistent[0]),{lat:25,lng:121});
assert.deepEqual(geometry.nodePosition(persistent[2]),{lat:25.02,lng:121.02});
assert.equal(persistent[2].status,'offline');
assert.equal(persistent[2].reported,false);
assert.equal(persistent[1].device_id,'node_A02');
assert.equal(telemetry[0].fixed_latitude,undefined,'merging does not modify telemetry objects');
assert.deepEqual(geometry.mergeFixedLocations([], [{device_id:'bad',latitude:true,longitude:121}]),[]);
assert.equal(geometry.mergeFixedLocations([{...telemetry[0],status:'online'}],fixed)[0].status,'online');
assert.equal(geometry.mergeFixedLocations([], {device_locations:fixed}).length,2);

assert.deepEqual(geometry.memberIds({active_device_ids:[],devices:['node_A01']}),[]);
assert.deepEqual(geometry.memberIds({reporting_device_ids:'["node_A01","node_A02","node_A01"]'}),['node_A01','node_A02']);
assert.deepEqual(geometry.memberIds({devices:[{device_id:'node_A01'},{invalid:'value'},' node_A02 ']}),['node_A01','node_A02']);
assert.equal(geometry.isDrone({classification:{model_label:'Airplane',is_target:true},label:'Drone'}),false);
assert.equal(geometry.isDrone({label:'aircraft'}),false,'legacy aircraft alone does not establish Drone');

const normal = geometry.buildGeometries(input);
assert.equal(normal.length,1);
assert.equal(normal[0].kind,'polygon');
assert.equal(normal[0].path.length,3,'an interior participant is excluded from convex hull');
assert.equal(normal[0].participants.length,4);
assert.ok(normal[0].deviceIds.includes('node_A01'),'a recent report may pulse an offline node without changing its status');
assert.equal(nodes[0].status,'offline');
assert.equal(normal[0].position,undefined,'participation must never manufacture a target position');
assert.ok(normal[0].label.includes('非無人機定位'));
assert.deepEqual(geometry.buildGeometries({...input,enabled:false}),[]);

assert.equal(geometry.buildGeometries({...input,events:input.events.slice(0,2)})[0].kind,'line');
assert.equal(geometry.buildGeometries({...input,events:input.events.slice(0,1)})[0].kind,'point');
assert.equal(geometry.buildGeometries({...input,groups:[]}).length,4,'unassociated events stay separate; no implied shared target');
assert.ok(geometry.buildGeometries({...input,groups:[group({last_event_time:iso(now-16000)})]}).every(g=>g.kind==='point'),'stale groups do not keep a polygon');
assert.ok(geometry.buildGeometries({...input,groups:[group({status:'CLOSED'})]}).every(g=>g.kind==='point'));
assert.ok(geometry.buildGeometries({...input,groups:[group({active_device_ids:[]})]}).every(g=>g.kind==='point'));
assert.ok(geometry.buildGeometries({...input,events:input.events.map(e=>({...e,group_id:'other'}))}).every(g=>g.kind==='point'),'explicitly different groups cannot be mixed');
assert.ok(geometry.buildGeometries({...input,groups:[group({first_event_time:iso(now-4000),last_event_time:iso(now-2000)})]}).every(g=>g.kind==='point'),'later events cannot light up an older group');
assert.ok(geometry.buildGeometries({...input,groups:[group({first_event_time:null,created_at:null})]}).every(g=>g.kind==='point'),'unlinked events without temporal association stay separate');
assert.equal(geometry.buildGeometries({...input,events:input.events.map(e=>({...e,group_id:'g1'})),groups:[group({first_event_time:null})]})[0].kind,'polygon');
assert.equal(geometry.buildGeometries({...input,events:[],groups:[group({events:input.events})]})[0].kind,'polygon','typed events nested in an explicit group are supported');
assert.deepEqual(geometry.buildGeometries({...input,events:input.events.map(e=>({...e,timestamp:iso(now-16000),created_at:iso(now)}))}),[],'server update time cannot refresh an old capture');
assert.deepEqual(geometry.buildGeometries({...input,events:input.events.map(e=>({...e,timestamp:iso(now+3000)}))}),[]);
assert.deepEqual(geometry.buildGeometries({...input,events:input.events.map(e=>({...e,classification:{model_label:'Airplane',is_target:true}}))}),[]);
assert.deepEqual(geometry.buildGeometries({...input,nodes:nodes.map(n=>({...n,marker_latitude:999}))}),[]);

const line = geometry.convexHull([{lat:25,lng:121},{lat:25.001,lng:121.001},{lat:25.002,lng:121.002},{lat:25,lng:121}]);
assert.equal(line.length,2,'collinear participants degrade to an endpoint line');
assert.deepEqual(geometry.convexHull([{lat:25,lng:121},{lat:25,lng:121}]),[{lat:25,lng:121}]);
assert.equal(geometry.convexHull([{lat:1,lng:179.999},{lat:1,lng:-179.999},{lat:1.001,lng:180}]).length,3);

// Realistic map doubles assert ownership and cleanup without loading Google Maps.
const made = [];
class Overlay {
    constructor(options) { this.options={...options};this.map=options.map;made.push(this); }
    setOptions(options) { Object.assign(this.options,options); }
    setMap(map) { this.map=map; }
}
class Circle extends Overlay {}
class Polygon extends Overlay {}
class Polyline extends Overlay {}
const maps={Circle,Polygon,Polyline};
let wall=now, timerId=0, rafId=0;
const timers=new Map(), frames=new Map();
let pulseNodeIds=[];
const renderer=geometry.createRenderer({clock:()=>wall,
    setTimeout:(callback,delay)=>{timers.set(++timerId,{callback,delay});return timerId;},clearTimeout:id=>timers.delete(id),
    requestAnimationFrame:callback=>{frames.set(++rafId,callback);return rafId;},cancelAnimationFrame:id=>frames.delete(id)});
const map={};
renderer.update({...input,map,google:{maps},onPulse:ids=>{pulseNodeIds=[...ids].sort();}});
assert.equal(made.filter(o=>o instanceof Polygon && o.map===map).length,1);
assert.equal(made.filter(o=>o instanceof Circle && o.map===map).length,4);
const livePolygon=made.find(o=>o instanceof Polygon && o.map===map);
assert.equal(livePolygon.options.strokeColor,'#f97316');
assert.equal(livePolygon.options.strokeWeight,3);
assert.equal(livePolygon.options.strokeOpacity,.85);
assert.equal(livePolygon.options.fillOpacity,.12,'live polygon mirrors Simulation Lab styling');
const liveRing=made.find(o=>o instanceof Circle && o.map===map);
assert.equal(liveRing.options.strokeWeight,3);
assert.equal(liveRing.options.radius,24);
assert.deepEqual(pulseNodeIds,nodes.map(n=>n.device_id).sort(),'the V2.2 marker pulse receives the participating node set');
assert.equal(frames.size,1);
assert.equal(timers.size,1);
renderer.update({...input,map,google:{maps},reducedMotion:true});
assert.equal(frames.size,0,'reduced motion shows static overlays');
assert.equal(timers.size,1,'reduced motion still expires old evidence');
wall=now+16000;
[...timers.values()][0].callback();
assert.equal(made.filter(o=>o.map===map).length,0,'stale evidence clears without another network refresh');

wall=now;
renderer.update({...input,map,google:{maps},events:input.events.slice(0,2)});
assert.equal(made.filter(o=>o instanceof Polyline && o.map===map).length,1);
const liveLine=made.find(o=>o instanceof Polyline && o.map===map);
assert.equal(liveLine.options.strokeColor,'#f97316');
assert.equal(liveLine.options.strokeWeight,5);
assert.equal(liveLine.options.strokeOpacity,.95,'two-node source line mirrors Simulation Lab styling');
renderer.update({...input,map,google:{maps},enabled:false});
assert.equal(made.filter(o=>o.map===map).length,0,'disabled workspace removes its owned overlays');
assert.equal(frames.size,0);
assert.equal(timers.size,0);
renderer.update({...input,map,google:{maps},reducedMotion:true});
renderer.clear();
assert.equal(made.filter(o=>o.map===map).length,0);
assert.equal(timers.size,0);
console.log('Dashboard node geometry: fixed-node persistence, explicit participation, freshness, hull, and renderer lifecycle passed');
