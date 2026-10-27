const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
let time=0,frame,sent=[];
const context={location:{search:'?phase3d=1'},performance:{now:()=>++time},document:{visibilityState:'visible'},
    URLSearchParams,crypto:{randomUUID:()=> 'test'},requestAnimationFrame:fn=>{frame=fn;}};
vm.createContext(context);vm.runInContext(fs.readFileSync('static/dashboard_phase3d.js','utf8'),context);
const d=context.Phase3dDashboard,ws={readyState:1,send:x=>sent.push(JSON.parse(x))};
d.connected(ws);assert.equal(sent[0].type,'phase3d_subscribe');
d.control({type:'phase3d_ready',browserSessionId:d.status().browserSessionId});
const node={device_id:'node_A01',detection_state:{sequence:1,active:true,label:'Drone',confidence:.91,observed_at_ms:123}};
const message={type:'node_heartbeat',phase3d:{traceId:'p3d_test',sequence:1,nodeId:node.device_id},node};
d.begin(message,0,1);d.stored(node);d.marker(node,{__dashboardAlertKey:'1:1'});d.finish();frame();
assert.equal(d.rows.length,1);assert.equal(sent[1].type,'phase3d_receipt');
assert.equal(d.rows[0].active,true);assert.equal(d.rows[0].mapApplicable,true);
assert.ok(d.rows[0].D5>=d.rows[0].D4);
d.begin(message,0,1);d.stored(node);d.finish();frame();
assert.equal(d.rows[1].duplicate,true);assert.equal(d.rows[1].outOfOrder,true);
assert.equal(d.rows[1].alertIndicator,'NOT_AVAILABLE');
console.log('Phase3D actual milestone hooks / receipt / duplicate / missing indicator PASS');
