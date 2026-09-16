const assert=require('node:assert/strict');
const {summarize}=require('../../static/dashboard_overview');
const now=1000000;
const input={now,backendConnected:true,devicesAt:now,eventsAt:now,devices:[
    {id:'A',online:true,listening:true,located:true},
    {id:'B',online:false,listening:true,located:true},
    {id:'C',online:true,listening:false,located:false}
],events:[
    {id:'old',time:now-60001,drone:true},
    {id:'recent',time:now-1000,drone:true},
    {id:'car',time:now-500,drone:false},
    {id:'future',time:now+1000,drone:true}
]};
let result=summarize(input);
assert.equal(result.online,2);assert.equal(result.listening,1);assert.equal(result.offline,1);
assert.equal(result.missingLocation,1);assert.equal(result.recentDroneCount,1);
assert.equal(result.devices[0].id,'B');
assert.equal(input.devices[0].id,'A','sort never mutates dashboard state');
for(const change of [{backendConnected:false},{devicesFailed:true},{devicesAt:now-20001}]) {
    result=summarize({...input,...change});
    assert.equal(result.nodesFresh,false);assert.equal(result.online,null);
}
for(const change of [{backendConnected:false},{eventsFailed:true},{eventsAt:now-45001}]) {
    result=summarize({...input,...change});
    assert.equal(result.eventsFresh,false);assert.equal(result.recentDroneCount,null);
    assert.equal(result.recentEvents.length,4,'old records remain available with stale status');
}
assert.equal(summarize({...input,events:[]}).recentDroneCount,0);
assert.equal(summarize({now}).recentDroneCount,null,'unloaded data is not zero detections');
console.log('monitor overview: live/stale/failed/empty snapshots, node health and recent-event counts passed');

const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const template=fs.readFileSync(path.join(__dirname,'../../templates/dashboard_v2_4.html'),'utf8');
function extract(name) {
    const match=template.match(new RegExp(`        (?:async )?function ${name}\\([^]*?\\n        }`));
    assert(match,`Missing production function ${name}`);return match[0];
}
const icons=vm.createContext({google:{maps:{SymbolPath:{CIRCLE:'CIRCLE'}}}});
vm.runInContext(extract('nodeMarkerIcon')+extract('nodeShapeText'),icons);
for(const id of ['node_A01','node_A02','node_A03','node_A04','arbitrary']) {
    assert.equal(icons.nodeMarkerIcon({device_id:id},true).path,'CIRCLE');
    assert.equal(icons.nodeMarkerIcon({device_id:id},false,true).fillColor,'#475569');
    assert.equal(icons.nodeShapeText(id),'●');
}
async function verifyReads() {
    let body={status:'degraded',devices:[]};
    const reads=vm.createContext({AbortController,setTimeout,clearTimeout,fetch:async()=>({ok:true,json:async()=>body})});
    vm.runInContext(extract('fetchJson'),reads);
    await assert.rejects(()=>reads.fetchJson('/device-status'),/data unavailable/);
    body={status:'success',devices:[]};
    assert.equal((await reads.fetchJson('/device-status')).status,'success');
    console.log('overview API degradation and shared live-map node icons passed');
}
verifyReads().catch(error=>{console.error(error);process.exitCode=1;});
