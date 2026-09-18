(function(root){
    'use strict';
    // Simulation engineering defaults. None of these thresholds are field validated.
    const DEFAULT_CONFIG=Object.freeze({
        motionWindowSize:20,
        motionWindowMs:6000,
        minimumMotionSamples:4,
        minimumMotionSpanMs:600,
        maximumMotionGapMs:1600,
        maximumObservationAgeMs:1200,
        maximumSegmentSpeedMps:150,
        minimumSpeedMps:.1,
        entryTimeEmaAlpha:.25,
        etaHoldMs:2000,
        departingConfirmMs:1000,
        approachingClosingThreshold:.15,
        departingClosingThreshold:-.15,
        trajectoryUncertaintyMultiplier:2,
        minimumTrajectoryUncertaintyM:3,
        robustResidualFloorM:6,
        robustResidualMultiplier:4,
        predictionHorizonSeconds:3600
    });
    const finite=n=>typeof n==='number'&&Number.isFinite(n);
    const point=p=>p&&finite(p.x)&&finite(p.y);
    const clamp=(n,a,b)=>Math.max(a,Math.min(b,n));
    const median=values=>{const s=values.slice().sort((a,b)=>a-b);return s.length?s.length%2?s[(s.length-1)/2]:(s[s.length/2-1]+s[s.length/2])/2:null;};
    function measurementTimeMs(p){
        if(finite(p?.measurementTimeMs))return p.measurementTimeMs;
        if(finite(p?.timeMs))return p.timeMs;
        return finite(p?.time)?p.time*1000:null;
    }
    function normalizedHistory(history,referenceTimeMs,config={}){
        const c={...DEFAULT_CONFIG,...config},byTime=new Map();
        for(const p of Array.isArray(history)?history:[]){
            const timeMs=measurementTimeMs(p);
            if(!point(p)||!finite(timeMs)||timeMs>referenceTimeMs||p.rejected||p.invalid||p.accepted===false)continue;
            byTime.set(timeMs,{x:p.x,y:p.y,timeMs,source:p.source||'estimated_localization'});
        }
        const ordered=[...byTime.values()];
        ordered.sort((a,b)=>a.timeMs-b.timeMs);
        const cutoff=referenceTimeMs-c.motionWindowMs;
        const recent=ordered.filter(p=>p.timeMs>=cutoff).slice(-c.motionWindowSize);
        const clean=[];
        for(const p of recent){
            const previous=clean.at(-1),dt=previous?(p.timeMs-previous.timeMs)/1000:null;
            if(previous&&dt>0&&Math.hypot(p.x-previous.x,p.y-previous.y)/dt>c.maximumSegmentSpeedMps)continue;
            clean.push(p);
        }
        return clean;
    }
    function linearFit(points,key){
        const origin=points[0].timeMs,ts=points.map(p=>(p.timeMs-origin)/1000),values=points.map(p=>p[key]);
        const mt=ts.reduce((a,b)=>a+b,0)/ts.length,mv=values.reduce((a,b)=>a+b,0)/values.length;
        const denominator=ts.reduce((sum,t)=>sum+(t-mt)**2,0);
        const slope=denominator>0?ts.reduce((sum,t,i)=>sum+(t-mt)*(values[i]-mv),0)/denominator:0;
        return {origin,slope,intercept:mv-slope*mt,valueAt(timeMs){return this.intercept+this.slope*(timeMs-this.origin)/1000;}};
    }
    function fitOnce(points,referenceTimeMs){
        const fx=linearFit(points,'x'),fy=linearFit(points,'y');
        const residuals=points.map(p=>Math.hypot(p.x-fx.valueAt(p.timeMs),p.y-fy.valueAt(p.timeMs)));
        const residualRmse=Math.sqrt(residuals.reduce((sum,r)=>sum+r*r,0)/residuals.length);
        return {fx,fy,residuals,residualRmse,position:{x:fx.valueAt(referenceTimeMs),y:fy.valueAt(referenceTimeMs)},vx:fx.slope,vy:fy.slope};
    }
    function estimateMotion(history,referenceTimeMs,config={}){
        const c={...DEFAULT_CONFIG,...config};let points=normalizedHistory(history,referenceTimeMs,c);
        const insufficient=reason=>({valid:false,reason,sampleCount:points.length,timeSpanMs:points.length>1?points.at(-1).timeMs-points[0].timeMs:0,referenceTimeMs});
        if(points.length<c.minimumMotionSamples)return insufficient('TOO_FEW_POINTS');
        let timeSpanMs=points.at(-1).timeMs-points[0].timeMs;
        if(timeSpanMs<c.minimumMotionSpanMs)return insufficient('HISTORY_TOO_SHORT');
        let maximumGapMs=Math.max(...points.slice(1).map((p,i)=>p.timeMs-points[i].timeMs));
        if(maximumGapMs>c.maximumMotionGapMs)return insufficient('HISTORY_GAP');
        if(referenceTimeMs-points.at(-1).timeMs>c.maximumObservationAgeMs)return insufficient('OBSERVATION_STALE');
        let fit=fitOnce(points,referenceTimeMs);
        const residualMedian=median(fit.residuals),threshold=Math.max(c.robustResidualFloorM,(residualMedian||0)*c.robustResidualMultiplier);
        const filtered=points.filter((p,i)=>fit.residuals[i]<=threshold);
        if(filtered.length>=c.minimumMotionSamples&&filtered.length<points.length){points=filtered;fit=fitOnce(points,referenceTimeMs);timeSpanMs=points.at(-1).timeMs-points[0].timeMs;maximumGapMs=Math.max(...points.slice(1).map((p,i)=>p.timeMs-points[i].timeMs));}
        if(timeSpanMs<c.minimumMotionSpanMs||maximumGapMs>c.maximumMotionGapMs)return insufficient('ROBUST_HISTORY_INSUFFICIENT');
        const speed=Math.hypot(fit.vx,fit.vy),heading=speed>=c.minimumSpeedMps?(Math.atan2(fit.vx,fit.vy)*180/Math.PI+360)%360:null;
        return {valid:true,reason:'OK',position:fit.position,vx:fit.vx,vy:fit.vy,speed,heading,residualRmse:fit.residualRmse,sampleCount:points.length,timeSpanMs,maximumGapMs,referenceTimeMs,lastMeasurementTimeMs:points.at(-1).timeMs,source:'fitted_estimated_trajectory'};
    }
    function siteGeometry(position,vx,vy,site,config={}){
        const c={...DEFAULT_CONFIG,...config},radius=Number(site?.radius),x=position.x-site.x,y=position.y-site.y,distance=Math.hypot(x,y),speed=Math.hypot(vx,vy);
        const closingSpeed=distance>0?-(x*vx+y*vy)/distance:0;
        const cpaTime=speed>=c.minimumSpeedMps?clamp(-(x*vx+y*vy)/(speed*speed),0,c.predictionHorizonSeconds):0;
        const cpaDistance=Math.hypot(x+vx*cpaTime,y+vy*cpaTime);
        if(distance<=radius)return {etaSeconds:0,intersectionStatus:'ALREADY_INSIDE',distance,closingSpeed,cpaTime,cpaDistance,discriminant:null};
        if(speed<c.minimumSpeedMps)return {etaSeconds:null,intersectionStatus:'LOW_SPEED',distance,closingSpeed,cpaTime,cpaDistance,discriminant:null};
        const a=speed*speed,b=2*(x*vx+y*vy),cc=distance*distance-radius*radius,discriminant=b*b-4*a*cc;
        if(discriminant<0)return {etaSeconds:null,intersectionStatus:'NO_INTERSECTION',distance,closingSpeed,cpaTime,cpaDistance,discriminant};
        const roots=[(-b-Math.sqrt(discriminant))/(2*a),(-b+Math.sqrt(discriminant))/(2*a)].filter(t=>t>=0).sort((m,n)=>m-n);
        if(!roots.length)return {etaSeconds:null,intersectionStatus:'NO_FUTURE_INTERSECTION',distance,closingSpeed,cpaTime,cpaDistance,discriminant};
        if(roots[0]>c.predictionHorizonSeconds)return {etaSeconds:null,intersectionStatus:'BEYOND_HORIZON',distance,closingSpeed,cpaTime,cpaDistance,discriminant};
        return {etaSeconds:roots[0],intersectionStatus:'INTERSECTS',distance,closingSpeed,cpaTime,cpaDistance,discriminant};
    }
    function emptyRaw(referenceTimeMs,reason,motion=null){return {valid:false,referenceTimeMs,motion,rawEtaSeconds:null,rawEntryTimeMs:null,closingSpeed:null,cpaDistance:null,cpaTime:null,trajectoryUncertaintyM:null,rawIntersectionState:'UNAVAILABLE',reason,trend:'UNSTABLE'};}
    function createRawSitePrediction(input){
        const c={...DEFAULT_CONFIG,...input?.config},referenceTimeMs=input?.referenceTimeMs;
        if(!finite(referenceTimeMs)||!point(input?.site)||!finite(input.site.radius)||input.site.radius<=0)return emptyRaw(referenceTimeMs,'INVALID_SITE');
        const motion=estimateMotion(input.history,referenceTimeMs,c);
        if(!motion.valid)return emptyRaw(referenceTimeMs,motion.reason,motion);
        const geometry=siteGeometry(motion.position,motion.vx,motion.vy,input.site,c);
        const uncertainty=Math.max(c.minimumTrajectoryUncertaintyM,motion.residualRmse*c.trajectoryUncertaintyMultiplier);
        let state=geometry.cpaDistance+uncertainty<input.site.radius?'LIKELY_INTERSECTS':geometry.cpaDistance-uncertainty>input.site.radius?'LIKELY_MISSES':'INTERSECTION_UNCERTAIN';
        if(geometry.intersectionStatus==='ALREADY_INSIDE')state='ALREADY_INSIDE';
        const trend=motion.speed<c.minimumSpeedMps?'STATIONARY':geometry.closingSpeed>c.approachingClosingThreshold?'APPROACHING':geometry.closingSpeed<c.departingClosingThreshold?'DEPARTING':'UNCERTAIN';
        const rawEtaSeconds=geometry.etaSeconds,rawEntryTimeMs=rawEtaSeconds===null?null:referenceTimeMs+rawEtaSeconds*1000;
        let reason=geometry.intersectionStatus;
        if(trend==='DEPARTING')reason='DEPARTING';else if(state==='INTERSECTION_UNCERTAIN')reason='INTERSECTION_UNCERTAIN';else if(trend==='UNCERTAIN'&&rawEtaSeconds!==0)reason='TREND_UNCERTAIN';
        const valid=rawEtaSeconds!==null&&(state==='LIKELY_INTERSECTS'||state==='ALREADY_INSIDE')&&(trend==='APPROACHING'||rawEtaSeconds===0);
        return {valid,referenceTimeMs,motion,rawEtaSeconds,rawEntryTimeMs,closingSpeed:geometry.closingSpeed,cpaDistance:geometry.cpaDistance,cpaTime:geometry.cpaTime,protectedRadius:input.site.radius,trajectoryUncertaintyM:uncertainty,rawIntersectionState:state,mathematicalIntersection:geometry.intersectionStatus,reason,trend};
    }
    class EtaStabilizer{
        constructor(config={}){this.config={...DEFAULT_CONFIG,...config};this.reset();}
        reset(){this.smoothedEntryTimeMs=null;this.invalidSinceMs=null;this.departingSinceMs=null;this.lastTimeMs=null;this.lastSignature=null;this.lastOutput=null;this.everStable=false;}
        update(raw,currentTimeMs){
            const c=this.config;if(!finite(currentTimeMs))throw new Error('simulation time is required');
            if(this.lastTimeMs!==null&&currentTimeMs<this.lastTimeMs)this.reset();
            const signature=JSON.stringify([raw?.valid??false,raw?.rawEntryTimeMs??null,raw?.trend||null,raw?.reason||null]);
            if(this.lastTimeMs===currentTimeMs&&this.lastSignature===signature&&this.lastOutput)return {...this.lastOutput};
            this.lastTimeMs=currentTimeMs;
            this.lastSignature=signature;
            if(raw?.trend==='DEPARTING'){if(this.departingSinceMs===null)this.departingSinceMs=currentTimeMs;}else this.departingSinceMs=null;
            const departingConfirmed=this.departingSinceMs!==null&&currentTimeMs-this.departingSinceMs>=c.departingConfirmMs;
            if(raw?.valid&&!departingConfirmed){
                this.invalidSinceMs=null;this.departingSinceMs=null;
                this.smoothedEntryTimeMs=raw.rawEtaSeconds===0?currentTimeMs:this.smoothedEntryTimeMs===null?raw.rawEntryTimeMs:this.smoothedEntryTimeMs*(1-c.entryTimeEmaAlpha)+raw.rawEntryTimeMs*c.entryTimeEmaAlpha;
                this.everStable=true;
                return this.output('STABLE',raw,currentTimeMs,0);
            }
            if(this.invalidSinceMs===null)this.invalidSinceMs=currentTimeMs;
            const holdAgeMs=currentTimeMs-this.invalidSinceMs;
            if(this.smoothedEntryTimeMs!==null&&!departingConfirmed&&holdAgeMs<=c.etaHoldMs)return this.output('HOLDING',raw,currentTimeMs,holdAgeMs);
            const state=this.everStable?'CLEARED':'UNSTABLE';this.smoothedEntryTimeMs=null;
            return this.output(state,raw,currentTimeMs,holdAgeMs);
        }
        output(state,raw,currentTimeMs,holdAgeMs){
            const eta=this.smoothedEntryTimeMs===null?null:Math.max(0,(this.smoothedEntryTimeMs-currentTimeMs)/1000);
            const result={state,displayEtaSeconds:eta,smoothedEntryTimeMs:this.smoothedEntryTimeMs,holdAgeMs,trajectoryLabel:state==='STABLE'?'穩定':state==='HOLDING'?'暫時不穩定':'無可靠預測',reason:raw?.reason||'NO_PREDICTION'};
            this.lastOutput=result;return {...result};
        }
    }
    function groundTruthEta(target,site,config={}){
        const c={...DEFAULT_CONFIG,...config};if(!target||target.kind!=='drone'||target.lost||!point(target.position)||!point(site)||!finite(target.speed))return null;
        if(Math.hypot(target.position.x-site.x,target.position.y-site.y)<=site.radius)return 0;
        if(target.speed<c.minimumSpeedMps)return null;
        let position={...target.position},elapsed=0;
        const segments=(target.waypoints||[]).map(p=>({...p}));
        if(!segments.length){const angle=target.heading*Math.PI/180;const g=siteGeometry(position,Math.sin(angle)*target.speed,Math.cos(angle)*target.speed,site,c);return g.etaSeconds;}
        for(const end of segments){const dx=end.x-position.x,dy=end.y-position.y,length=Math.hypot(dx,dy);if(!length)continue;const vx=dx/length*target.speed,vy=dy/length*target.speed,g=siteGeometry(position,vx,vy,site,c),duration=length/target.speed;if(g.etaSeconds!==null&&g.etaSeconds<=duration)return elapsed+g.etaSeconds;elapsed+=duration;position=end;}
        return null;
    }
    const api={DEFAULT_CONFIG,normalizedHistory,estimateMotion,siteGeometry,createRawSitePrediction,EtaStabilizer,groundTruthEta};
    if(typeof module==='object'&&module.exports)module.exports=api;else root.DashboardSimulationEta=api;
})(typeof globalThis==='object'?globalThis:this);
