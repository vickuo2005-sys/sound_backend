(function(root){
    'use strict';
    const requireModule=name=>typeof module==='object'&&module.exports?require(name):null;
    const O=root.DashboardOperations || requireModule('./dashboard_operations');
    const Eta=root.DashboardSimulationEta || requireModule('./dashboard_simulation_eta');
    const Tracking=root.DashboardSimulationTracker || requireModule('./dashboard_simulation_tracker');
    const finite=Number.isFinite,metres=111195;
    function diagnostics(p){try{return typeof p.diagnostics_json==='string'?JSON.parse(p.diagnostics_json):p.diagnostics_json||{};}catch(_){return {};}}
    function usable(p){const d=diagnostics(p);return d?.source==='localization_result'&&['tdoa','gcc_phat','timestamp_tdoa','hybrid_tdoa','gcc_phat_tdoa'].includes(d.localization_method)&&d.reporting_node_count>=2&&finite(p.uncertainty_radius_m)&&p.uncertainty_radius_m>=0;}
    const offset=(p,origin)=>({x:((p.lng-origin.lng+540)%360-180)*metres*Math.cos(origin.lat*Math.PI/180),y:(p.lat-origin.lat)*metres});
    const latLng=(p,origin)=>({lat:origin.lat+p.y/metres,lng:((origin.lng+p.x/(metres*Math.cos(origin.lat*Math.PI/180))+540)%360)-180});
    class LiveEstimator{
        constructor(){this.targets=new Map();this.siteKey=null;}
        reset(){this.targets.clear();this.siteKey=null;}
        prune(ids){for(const id of this.targets.keys())if(!ids.has(id))this.targets.delete(id);}
        assess(track,site,now,enabled=true,motionEnabled=true){
            const key=JSON.stringify(site||null);if(this.siteKey!==key){this.targets.clear();this.siteKey=key;}
            const id=String(track?.id??track?.track_id??'');
            const result={id,status:'unlocated',position:null,time:null,distance:null,zoneEta:null,arrivalEta:null,reason:'NO_LOCALIZATION'};
            const path=O.points(track),last=path.at(-1);
            if(!enabled){this.targets.delete(id);return {...result,reason:'LOCALIZATION_DISABLED'};}
            if(!last||!usable(last)||['closed','expired','ended','inactive'].includes(String(track.status).toLowerCase())){this.targets.delete(id);return result;}
            if(last.time===null||last.time>now||now-last.time>Tracking.DEFAULT_CONFIG.maxPredictionAgeMs){this.targets.delete(id);return {...result,reason:'OBSERVATION_STALE'};}
            let target=this.targets.get(id);
            // Only consume a contiguous run of genuine localization measurements.
            const start=path.findLastIndex(p=>!usable(p));
            const measurements=path.slice(start+1).filter(p=>p.time!==null&&p.time<=now);
            const signature=JSON.stringify(measurements.map(p=>[p.time,p.lat,p.lng,p.uncertainty_radius_m]));
            if(!target){target={origin:last,tracker:new Tracking.AlphaBetaTracker(),zone:new Eta.EtaStabilizer(),arrival:new Eta.EtaStabilizer(),lastTime:-Infinity};this.targets.set(id,target);}
            if(target.signature!==signature){
                for(const p of measurements){
                    if(p.time<=target.lastTime)continue;
                    if(p.time-target.lastTime>Tracking.DEFAULT_CONFIG.maxPredictionAgeMs){target.tracker.reset();target.zone.reset();target.arrival.reset();}
                    const update=target.tracker.update(offset(p,target.origin),p.time,{uncertaintyM:p.uncertainty_radius_m});
                    target.lastTime=p.time;
                    if(update.accepted)target.acceptedTime=p.time;
                }
                target.signature=signature;
            }
            const state=target.tracker.predict(now);
            if(!state){this.targets.delete(id);return {...result,reason:'OBSERVATION_STALE'};}
            const motion={position:{x:state.x,y:state.y},vx:state.vx,vy:state.vy,speed:state.speed,heading:state.heading,
                uncertaintyM:state.uncertaintyM,qualityScore:state.qualityScore,alphaUsed:state.alphaUsed,betaUsed:state.betaUsed,
                lastMeasurementTimeMs:state.sourceTimeMs,source:'live_alpha_beta_track'};
            Object.assign(result,{status:'located',position:latLng(motion.position,target.origin),time:target.acceptedTime,motion,uncertainty:state.uncertaintyM,reason:'SITE_NOT_CONFIGURED'});
            if(!O.site(site))return result;
            const localSite={...offset(site,target.origin),radius:site.radius,arrivalRadius:site.arrivalRadius};
            const distance=Math.hypot(state.x-localSite.x,state.y-localSite.y);
            result.distance=distance;result.status=Eta.zoneState(distance,site.radius,state.uncertaintyM);
            if(!motionEnabled){target.zone.reset();target.arrival.reset();return {...result,reason:'MOTION_DISABLED'};}
            // Exactly the same prediction and stabilization implementation used by the lab.
            const prediction=Eta.predictSite(motion,localSite,now,target,state.uncertaintyM);
            Object.assign(result,{prediction,zoneEta:prediction.display.displayEtaSeconds,arrivalEta:prediction.arrivalDisplay.displayEtaSeconds,
                trend:{APPROACHING:'approaching',DEPARTING:'departing',STATIONARY:'stationary'}[prediction.raw.trend]||'stationary',reason:prediction.raw.reason});
            return result;
        }
    }
    const api={LiveEstimator,offset,latLng,usable};
    if(typeof module==='object'&&module.exports)module.exports=api;else root.DashboardLivePrediction=api;
})(typeof globalThis==='object'?globalThis:this);
