const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const O=require('../../static/dashboard_operations');
const Geometry=require('../../static/dashboard_node_geometry');
const Visuals=require('../../static/dashboard_map_visuals');
const reference=[{device_id:'A',lat:20,lng:120},{device_id:'B',lat:21,lng:121}];
const point=(time,lat,lng,extra={})=>({measurement_time_ms:time,measured_lat:lat,measured_lng:lng,...extra});
const diagnostic={source:'event_group_region',reporting_device_ids:['A','B'],reporting_nodes:[{device_id:'A',lat:1,lng:2},{device_id:'B',lat:3,lng:4}],region_geojson:{type:'LineString',coordinates:[[2,1],[4,3]]}};
let c=O.replayContext({diagnostics_json:JSON.stringify(diagnostic)},reference);
assert.equal(c.kind,'region');assert.equal(c.label,'區域估測中心');
assert.deepEqual(c.nodes.map(n=>n.position),[{lat:1,lng:2},{lat:3,lng:4}]);
assert(c.nodes.every(n=>n.historical));assert(c.historicalRegion);
c=O.replayContext({diagnostics_json:{source:'active_alert_region',reporting_device_ids:['A','missing']}},reference);
assert.equal(c.kind,'region');assert.equal(c.nodes[0].historical,false);assert.equal(c.missingNodes,1);
assert.equal(c.historicalRegion,false,'Current references must never become historical geometry');
assert.equal(O.replayContext({diagnostics_json:'bad'}).kind,'observation');
assert.equal(O.replayContext({diagnostics_json:'null'}).kind,'observation');
assert.equal(O.replayContext({diagnostics_json:{source:'localization_result',localization_method:'gcc_phat'}}).kind,'location');
const path=O.points({points:[point(1000,1,179),point(3000,3,-179)]});
let f=O.frame(path,.5,true);assert.equal(f.index,0);assert.equal(f.displayPoint.lat,2);assert.equal(f.displayPoint.lng,-180);
assert.equal(f.point.lat,1,'Visual interpolation must not change recorded coordinates or context');
assert.equal(O.frame(path,.5).interpolated,false);assert.equal(O.frame(path,1,true).interpolated,false);
assert.equal(O.frame(O.points({points:[point(null,1,2),point(null,3,4)]}),.5,true).interpolated,false);

// Exercise production replay functions with a map recorder and deferred API replies.
const source=fs.readFileSync(require('node:path').join(__dirname,'../../static/dashboard_operations_ui.js'),'utf8');
function harness(withMap=true){
    const elements=new Map(),overlays=[],pending=[];
    const el=id=>{if(!elements.has(id))elements.set(id,{value:id==='historySpeed'?'8':'0',checked:true,textContent:'',innerHTML:'',disabled:false});return elements.get(id);};
    class Overlay{
        constructor(options){this.options=options;this.map=options.map;overlays.push(this);}
        setMap(map){this.map=map;}setPath(path){this.path=path;}setPosition(p){this.position=p;}setIcon(icon){this.icon=icon;}setTitle(title){this.title=title;}
    }
    const api={Marker:Overlay,Polyline:Overlay,Polygon:Overlay,Circle:Overlay,SymbolPath:{CIRCLE:'circle'},
        Map:class{fitBounds(){}},LatLngBounds:class{extend(){}},event:{trigger(){}}};
    const context=vm.createContext({O,DashboardNodeGeometry:Geometry,DashboardMapVisuals:Visuals,el,
        historyMap:null,historyLine:null,historyMarker:null,historyOverlays:[],historyFrameKey:null,replay:null,request:0,animation:null,
        config:{name:'Site',lat:2,lng:3,radius:100},window:{google:withMap?{maps:api}:null},google:{maps:api},mapsLoadFailed:!withMap,
        state:{},canonicalDevices:()=>reference,nodeLocation:n=>({lat:n.lat,lng:n.lng}),shortNodeId:x=>x,safe:x=>String(x),
        switchView(){},renderTracksView(){},cancelAnimationFrame(){},requestAnimationFrame:()=>1,performance:{now:()=>0},
        fetchJson:url=>new Promise(resolve=>pending.push({url,resolve}))});
    const begin=source.indexOf('    function pause()'),end=source.indexOf('    async function group(');
    vm.runInContext(source.slice(begin,end),context);
    const stepStart=source.indexOf('    function step('),stepEnd=source.indexOf("    el('historyPrevious').onclick",stepStart);
    vm.runInContext(source.slice(stepStart,stepEnd),context);
    return {context,el,overlays,pending};
}
(async()=>{
    for(const map of [true,false]){
        const h=harness(map),ctx=h.context;
        const loading=ctx.start('one');
        h.pending[0].resolve({points:[point(1000,1,2,{diagnostics_json:diagnostic}),point(3000,3,4,{diagnostics_json:{source:'active_alert_region',reporting_device_ids:['A']}})]});
        await loading;
        assert.match(h.el('historyContext').textContent,/區域估測中心/);
        if(map){assert(h.overlays.some(o=>o.options.title?.includes('當時參與節點')));assert(h.overlays.some(o=>o.options.radius===100));}
        else assert.match(h.el('historyFallback').innerHTML,/A<\/text>/);
        const firstOverlays=ctx.historyOverlays.slice();ctx.step(1);
        assert.match(h.el('historyContext').textContent,/缺少當時座標/);
        if(map)assert(firstOverlays.every(o=>o.map===null),'Previous frame overlays must be removed');
        ctx.step(-1);assert.match(h.el('historyContext').textContent,/A、B/);
        const all=h.overlays.slice();ctx.clear();assert(all.every(o=>o.map===null));assert.equal(h.el('historyContext').textContent,'');
        const single=ctx.start('single');h.pending[1].resolve({points:[point(1000,1,2,{diagnostics_json:diagnostic})]});await single;
        assert.match(h.el('historyReplayStatus').textContent,/僅一筆/);assert.equal(h.el('historyPlay').disabled,true);
        const stale=ctx.start('stale'),fresh=ctx.start('fresh');
        h.pending[3].resolve({points:[point(1000,4,5)]});await fresh;
        h.pending[2].resolve({points:[point(1000,9,10)]});await stale;
        assert.equal(ctx.replay.points[0].lat,4,'Late responses must not replace the selected replay');
    }
    console.log('History replay: provenance, context overlays, fallback, smooth display, steps, single point, cleanup and request races passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
