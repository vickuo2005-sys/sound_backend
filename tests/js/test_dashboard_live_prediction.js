const assert=require('node:assert/strict');
const O=require('../../static/dashboard_operations'),E=require('../../static/dashboard_simulation_eta'),T=require('../../static/dashboard_simulation_tracker');
const L=require('../../static/dashboard_live_prediction');
const site={name:'site',lat:25,lng:121,radius:150,arrivalRadius:20};
const origin={lat:25,lng:121},base=100000;
const diagnostics={source:'localization_result',localization_method:'tdoa',reporting_node_count:3};
const near=(a,b)=>assert(Math.abs(a-b)<1e-5,`${a} != ${b}`);
const make=(i,x=400-i*12)=>{const p=L.latLng({x,y:0},origin);return {measured_lat:p.lat,measured_lng:p.lng,measurement_time_ms:base+i*1000,uncertainty_radius_m:4,diagnostics_json:diagnostics};};
const estimator=new L.LiveEstimator(),tracker=new T.AlphaBetaTracker(),stabilizers={zone:new E.EtaStabilizer(),arrival:new E.EtaStabilizer()};
const track={id:'A',status:'ACTIVE',label:'drone',recent_points:[]};
for(let i=0;i<12;i++){
    const p=make(i);track.recent_points.push(p);const now=base+i*1000;
    tracker.update({x:400-i*12,y:0},now,{uncertaintyM:4});
    const state=tracker.predict(now),motion={position:{x:state.x,y:state.y},vx:state.vx,vy:state.vy,speed:state.speed};
    const expected=E.predictSite(motion,{x:0,y:0,radius:150,arrivalRadius:20},now,stabilizers,state.uncertaintyM);
    const actual=estimator.assess(track,site,now);
    assert.equal(actual.prediction.display.state,expected.display.state);
    assert.equal(actual.prediction.raw.reason,expected.raw.reason);
    if(expected.display.displayEtaSeconds!==null)near(actual.zoneEta,expected.display.displayEtaSeconds);
    else assert.equal(actual.zoneEta,null);
    near(actual.motion.vx,state.vx);near(actual.uncertainty,state.uncertaintyM);
    const duplicate=estimator.assess(track,site,now);
    assert.deepEqual(duplicate,actual,'Repeated snapshots must not advance the filter or smooth ETA twice at the same time');
}
let result=estimator.assess(track,site,base+12000);assert(result.position,'Brief gaps use the same bounded tracker prediction');
result=estimator.assess(track,site,base+15001);assert.equal(result.position,null);assert.equal(result.zoneEta,null);
assert.equal(estimator.assess(track,site,base+11000,false).reason,'LOCALIZATION_DISABLED');
assert.equal(estimator.assess(track,site,base+11000,true,false).zoneEta,null);
assert.equal(estimator.assess({...track,status:'CLOSED'},site,base+11000).position,null);
assert.equal(estimator.assess({...track,recent_points:[make(20)]},site,base+11000).position,null,'Future measurements cannot enter the tracker');
const region={...track,recent_points:[{...make(11),diagnostics_json:{...diagnostics,source:'event_group_region'}}]};
assert.equal(estimator.assess(region,site,base+11000).position,null,'Node/region centers cannot masquerade as located targets');
const missingQuality={...track,recent_points:[{...make(11),uncertainty_radius_m:null}]};
assert.equal(estimator.assess(missingQuality,site,base+11000).position,null);
const entries=new O.Entries();let previous=false;
for(const [i,status] of ['outside','inside','inside','boundary','inside','outside','inside'].entries()){
    const transition=E.zoneTransition(previous,status);
    assert.equal(entries.update('A',status,i+1),transition.entered,'Lab and live share alert episode semantics');previous=transition.inside;
}
assert.equal(E.zoneState(140,150,20),'boundary','Real uncertainty must be considered before a confirmed entry');
const newSite={...site,radius:100};estimator.assess(track,newSite,base+11000);assert.equal(estimator.siteKey,JSON.stringify(newSite));
estimator.prune(new Set());assert.equal(estimator.targets.size,0);
console.log('Live/lab parity: same tracker + raw ETA + stabilized ETA, duplicate snapshots, uncertainty, stale/future data, provenance and alert episodes passed');
