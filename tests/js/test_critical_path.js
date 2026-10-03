const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const html=fs.readFileSync(require('node:path').join(__dirname,'../../templates/dashboard_v2_4.html'),'utf8');
let maps=0,now=10;
const state={runtime:{critical_path_diagnostics_enabled:true},groups:new Map()};
const context=vm.createContext({state,performance:{now:()=>++now},groupId:g=>g.id,
 renderOverview(){},renderTracksView(){},renderMap(){maps++},renderCommandBar(){},Date});
vm.runInContext(html.slice(html.indexOf('        // Measures synchronous map API/update work'),html.indexOf('        async function bootstrap()')),context);
const msg={type:'event_group',critical_path:{event_id:'event-1'},group:{id:'g',region_center_lat:25,region_center_lng:121,device_relative_times:[]}};
context.handleWebSocketMessage(msg);
assert.equal(maps,1); assert.equal(state.groups.get('g'),msg.group);
assert.equal(state.browserGroupMapSamples[0].event_id,'event-1');
assert.equal(state.browserGroupMapSamples[0].synchronous_map_update_ms,1);
for(let i=0;i<300;i++)context.handleWebSocketMessage(msg);
assert.equal(state.browserGroupMapSamples.length,256);
state.runtime.critical_path_diagnostics_enabled=false;
context.handleWebSocketMessage(msg); assert.equal(state.browserGroupMapSamples.length,256);
context.recordGroupMapTiming(msg,NaN,Infinity);assert.equal(state.browserGroupMapSamples.length,256);
console.log('Critical path browser: event correlation, unchanged payload/render, bounded timing and production-off passed');
