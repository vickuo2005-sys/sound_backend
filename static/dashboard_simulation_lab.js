(function (root) {
    'use strict';
    const Eta = root.DashboardSimulationEta || (typeof module==='object'&&module.exports ? require('./dashboard_simulation_eta.js') : null);
    const Tracking = root.DashboardSimulationTracker || (typeof module==='object'&&module.exports ? require('./dashboard_simulation_tracker.js') : null);
    if(!Eta)throw new Error('DashboardSimulationEta must load before DashboardSimulationLab');
    if(!Tracking)throw new Error('DashboardSimulationTracker must load before DashboardSimulationLab');
    // This workspace owns all of its state. It must never import live dashboard state,
    // call application APIs, or publish simulated events onto the real event bus.
    const ORIGIN = Object.freeze({ lat: 25.039, lng: 121.5752 });
    const LIMITS = Object.freeze({ nodes: 100, targets: 20, events: 80, points: 600 });
    const finite = n => typeof n === 'number' && Number.isFinite(n);
    const clamp = (n, a, b) => Math.max(a, Math.min(b, n));
    const copy = value => JSON.parse(JSON.stringify(value));
    const point = p => p && finite(p.x) && finite(p.y) && Math.abs(p.x) <= 100000 && Math.abs(p.y) <= 100000;
    const escape = value => String(value ?? '').replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[ch]);
    function latLng(p) { return { lat: ORIGIN.lat + p.y / 111195, lng: ORIGIN.lng + p.x / (111195 * Math.cos(ORIGIN.lat * Math.PI / 180)) }; }
    function offset(p) { return { x: (p.lng - ORIGIN.lng) * 111195 * Math.cos(ORIGIN.lat * Math.PI / 180), y: (p.lat - ORIGIN.lat) * 111195 }; }
    function circleEntry(x, y, vx, vy, radius) {
        const c = x*x+y*y-radius*radius;
        if (c <= 0) return 0;
        const a = vx*vx+vy*vy, b = 2*(x*vx+y*vy), d = b*b-4*a*c;
        if (a < .01 || d < 0) return null;
        const t = (-b-Math.sqrt(d))/(2*a);
        return t >= 0 && t <= 3600 ? t : null;
    }
    function hull(nodes) {
        const sorted = nodes.filter(point).map(n => ({ x:n.x, y:n.y })).sort((a,b) => a.x-b.x || a.y-b.y);
        const unique = sorted.filter((p,i) => !i || p.x!==sorted[i-1].x || p.y!==sorted[i-1].y);
        if (unique.length <= 2) return unique;
        const cross = (a,b,c) => (b.x-a.x)*(c.y-a.y)-(b.y-a.y)*(c.x-a.x);
        const lower=[], upper=[];
        for (const p of unique) { while (lower.length>=2 && cross(lower.at(-2),lower.at(-1),p)<=0) lower.pop(); lower.push(p); }
        for (const p of unique.slice().reverse()) { while (upper.length>=2 && cross(upper.at(-2),upper.at(-1),p)<=0) upper.pop(); upper.push(p); }
        return lower.slice(0,-1).concat(upper.slice(0,-1));
    }
    function distance(a,b) { return point(a)&&point(b)?Math.hypot(a.x-b.x,a.y-b.y):Infinity; }
    function possibleSource(nodes) {
        const shape=hull(nodes);
        if(!shape.length)return {kind:'none',path:[],estimate:null};
        if(shape.length===1)return {kind:'circle',path:shape,estimate:{x:shape[0].x,y:shape[0].y}};
        const estimate=shape.reduce((sum,p)=>({x:sum.x+p.x/shape.length,y:sum.y+p.y/shape.length}),{x:0,y:0});
        return {kind:shape.length===2?'line':'polygon',path:shape,estimate};
    }
    function estimateFromDetections(nodes,target) {
        // Simulation-only oracle localization: truth synthesizes noisy/partial sensor estimates.
        // ETA prediction below only consumes the resulting estimatedTrail observations.
        if(!point(target?.position)||nodes.length<2)return null;
        const weighted=nodes.map(node=>{
            const range=Math.max(20,Number(node.detectionRadius)||300),d=distance(node,target.position);
            return {node,weight:Math.max(.04,1-d/range)};
        });
        const total=weighted.reduce((sum,item)=>sum+item.weight,0);
        return weighted.reduce((p,item)=>({x:p.x+item.node.x*item.weight/total,y:p.y+item.node.y*item.weight/total}),{x:0,y:0});
    }
    function localizationQuality(nodes) {
        const usable=(nodes||[]).filter(point),count=usable.length;
        if(count<2)return {uncertaintyM:120,qualityScore:.08,geometryQuality:'insufficient',nodeCount:count,spreadM:0,hullAreaM2:0};
        let spreadM=0;
        for(let i=0;i<usable.length;i++)for(let j=i+1;j<usable.length;j++)spreadM=Math.max(spreadM,distance(usable[i],usable[j]));
        const shape=hull(usable);
        let hullAreaM2=0;
        if(shape.length>=3){
            for(let i=0;i<shape.length;i++){
                const a=shape[i],b=shape[(i+1)%shape.length];
                hullAreaM2+=a.x*b.y-b.x*a.y;
            }
            hullAreaM2=Math.abs(hullAreaM2)/2;
        }
        const shapeScore=count>=3&&spreadM>0?clamp(4*hullAreaM2/(spreadM*spreadM),0,1):0;
        let uncertaintyM=count===2?65:count===3?38:Math.max(14,34-(count-3)*4);
        if(count>=3)uncertaintyM*=1.35-.55*shapeScore;
        uncertaintyM=clamp(uncertaintyM,10,120);
        const qualityScore=clamp(1-uncertaintyM/110,.08,.95);
        const geometryQuality=count<3?'limited':shapeScore>.55?'good':shapeScore>.2?'fair':'poor';
        return {uncertaintyM,qualityScore,geometryQuality,nodeCount:count,spreadM,hullAreaM2};
    }
    function velocity(target) {
        if (target.lost || !point(target.position) || target.speed<=0) return { x:0, y:0 };
        const next = target.waypoints[target.waypointIndex??0];
        if (next) { const dx=next.x-target.position.x,dy=next.y-target.position.y,d=Math.hypot(dx,dy); return d ? { x:dx/d*target.speed,y:dy/d*target.speed } : { x:0,y:0 }; }
        const angle=target.heading*Math.PI/180;
        return { x:Math.sin(angle)*target.speed,y:Math.cos(angle)*target.speed };
    }
    function assess(target, site) {
        const result={ status:target.lost?'lost':!point(target.position)?'unlocated':'located',distance:null,zoneEta:null,arrivalEta:null,trend:null };
        if (target.lost || !point(target.position) || !point(site) || target.kind!=='drone') return result;
        const x=target.position.x-site.x,y=target.position.y-site.y,d=Math.hypot(x,y),v=velocity(target);
        const closing=d ? -(x*v.x+y*v.y)/d : 0;
        Object.assign(result,{ distance:d,status:d<=site.radius?'inside':'outside',trend:closing>.1?'approaching':closing<-.1?'departing':'stationary' });
        result.zoneEta=circleEntry(x,y,v.x,v.y,site.radius);
        result.arrivalEta=circleEntry(x,y,v.x,v.y,site.arrivalRadius);
        return result;
    }
    function estimatedVelocity(target) {
        const path=target?.estimatedTrail||[];
        if(target?.lost||path.length<2)return {x:0,y:0};
        for(let i=path.length-1;i>0;i--){
            const dt=path[i].time-path[i-1].time;
            if(dt>.001)return {x:(path[i].x-path[i-1].x)/dt,y:(path[i].y-path[i-1].y)/dt};
        }
        return {x:0,y:0};
    }
    function assessSystem(target, site) {
        const result={ status:target.lost?'lost':!point(target.estimatedPosition)?'unlocated':'located',distance:null,zoneEta:null,arrivalEta:null,trend:null };
        if(target.lost||!point(target.estimatedPosition)||!point(site)||target.kind!=='drone')return result;
        const prediction=target.sitePrediction,raw=prediction?.raw,motion=raw?.motion;
        const current=motion?.valid&&point(motion.position)?motion.position:target.estimatedPosition;
        const x=current.x-site.x,y=current.y-site.y,d=Math.hypot(x,y),v=motion?.valid?{x:motion.vx,y:motion.vy}:estimatedVelocity(target);
        const closing=d?-(x*v.x+y*v.y)/d:0;
        Object.assign(result,{distance:d,status:d<=site.radius?'inside':'outside',trend:closing>.1?'approaching':closing<-.1?'departing':'stationary'});
        if(prediction){
            result.zoneEta=prediction.display?.displayEtaSeconds??null;
            result.arrivalEta=prediction.arrivalDisplay?.displayEtaSeconds??null;
            if(raw?.motion?.valid)result.trend={APPROACHING:'approaching',DEPARTING:'departing',STATIONARY:'stationary',UNCERTAIN:'stationary'}[raw.trend]||result.trend;
        }
        return result;
    }
    class LabModel {
        constructor() { this.sequence=0; this.reset(); }
        reset() {
            this.time=0; this.playing=false; this.rate=1; this.nodes=[]; this.targets=[]; this.events=[]; this.alerts=[]; this.selectedId=null;this.nodeSequence=0;this.nodeDetectionRadius=450;
            this.site={ x:0,y:0,name:'模擬據點',radius:150,arrivalRadius:20 }; this.replay=null;this.etaStabilizers=new Map();this.trackers=new Map();
        }
        id(prefix) { return `SIM-${prefix}-${++this.sequence}`; }
        addNode(position) {
            if (!point(position) || this.nodes.length>=LIMITS.nodes) return null;
            const ordinal=++this.nodeSequence;
            const node={ id:this.id('NODE'), ordinal, name:`節點 ${ordinal}`,x:position.x,y:position.y,online:true,reporting:true,detectionRadius:this.nodeDetectionRadius };
            this.nodes.push(node); return node;
        }
        moveNode(id,position) { const n=this.nodes.find(n=>n.id===id); if(n&&point(position)) { n.x=position.x;n.y=position.y;this.refreshEstimates(true);return true; } return false; }
        setAllNodeDetectionRadius(radius) { radius=Number(radius);if(!Number.isFinite(radius)||radius<20||radius>5000)return false;this.nodeDetectionRadius=radius;this.nodes.forEach(n=>{n.detectionRadius=radius;});this.refreshEstimates(true);return true; }
        refreshEstimates(force=false) { this.targets.forEach(t=>this.updateEstimate(t,force));this.inspect(); }
        setSite(position,radius=this.site?.radius??150) {
            if (!point(position)||!finite(radius)||radius<20||radius>5000) return false;
            this.site={ x:position.x,y:position.y,name:'模擬據點',radius,arrivalRadius:Math.min(20,radius) };
            this.targets.forEach(t=>{t.inside=false;t.sitePrediction=null;});this.etaStabilizers.clear();this.inspect(); return true;
        }
        createEvent(options={}) {
            if(this.targets.length>=LIMITS.targets) return null;
            const kind=['drone','car','airplane','rainfall','electric_saw'].includes(options.kind)?options.kind:'drone';
            const reporters=(options.reporters || this.nodes.filter(n=>n.reporting&&n.online).map(n=>n.id)).filter(id=>this.nodes.some(n=>n.id===id&&n.online));
            const target={ id:this.id('TARGET'),kind,position:point(options.position)?{x:options.position.x,y:options.position.y}:null,
                speed:clamp(finite(options.speed)?options.speed:15,0,100),heading:((finite(options.heading)?options.heading:90)%360+360)%360,
                waypoints:[],waypointIndex:0,startPosition:point(options.position)?{x:options.position.x,y:options.position.y}:null,routeRunCount:0,routeReady:false,reporters,lost:false,inside:false,trail:[],estimatedTrail:[],estimatedPosition:null,detectedNodeIds:[],score:clamp(finite(options.score)?options.score:.95,0,1),
                motionSegment:0,sitePrediction:null,etaEvaluation:[],replayFrames:[],rawEstimatedPosition:null,trackState:null,trackingDiagnostics:null };
            if(target.position) target.trail.push({...target.position,time:this.time});
            this.targets.push(target);this.selectedId=target.id;
            const event={ id:this.id('EVENT'),targetId:target.id,kind,time:this.time,reporters:reporters.slice(),simulation:true };
            this.events.unshift(event);this.events=this.events.slice(0,LIMITS.events);this.replay=null;this.updateEstimate(target,true);this.inspect();
            if(this.alerts.length)this.selectedId=this.alerts[0].targetId;
            return target;
        }
        selected() { return this.targets.find(t=>t.id===this.selectedId)||null; }
        eligibleNodes() { return this.nodes.filter(n=>n.online&&n.reporting); }
        reportingNodes(target=this.selected()) {
            if(!target||target.lost||!point(target.position))return [];
            return this.eligibleNodes(target).filter(n=>distance(n,target.position)<=n.detectionRadius);
        }
        geometry(target=this.selected()) { return hull(this.reportingNodes(target)); }
        sourceRegion(target=this.selected()) { return possibleSource(this.reportingNodes(target)); }
        predictionHistory(target) { return (target?.estimatedTrail||[]).filter(p=>(p.motionSegment??0)===(target.motionSegment??0)); }
        tracker(target) {
            if(!this.trackers.has(target.id))this.trackers.set(target.id,new Tracking.AlphaBetaTracker());
            return this.trackers.get(target.id);
        }
        stabilizers(target) {
            if(!this.etaStabilizers.has(target.id))this.etaStabilizers.set(target.id,{zone:new Eta.EtaStabilizer(),arrival:new Eta.EtaStabilizer()});
            return this.etaStabilizers.get(target.id);
        }
        resetTracking(target) {
            if(!target)return;
            this.trackers.delete(target.id);
            target.rawEstimatedPosition=null;
            target.trackState=null;
            target.trackingDiagnostics=null;
            target.estimatedPosition=null;
            target.estimatedTrail=[];
        }
        resetPrediction(target,incrementSegment=false) {
            if(!target)return;
            if(incrementSegment)target.motionSegment=(target.motionSegment??0)+1;
            target.sitePrediction=null;this.etaStabilizers.delete(target.id);
        }
        updatePrediction(target) {
            const referenceTimeMs=this.time*1000;
            if(!target||target.kind!=='drone'||target.lost){this.resetPrediction(target);return null;}
            const state=target.trackState;
            const motion=state&&point(state)?{
                position:{x:state.x,y:state.y},
                vx:state.vx,vy:state.vy,speed:state.speed,heading:state.heading,
                uncertaintyM:state.uncertaintyM,
                qualityScore:state.qualityScore,
                alphaUsed:state.alphaUsed,betaUsed:state.betaUsed,
                lastMeasurementTimeMs:state.sourceTimeMs,
                source:'simulation_alpha_beta_track'
            }:null;
            const innovation=Number(target.trackingDiagnostics?.innovationM)||0;
            const trackUncertaintyM=clamp(
                Number(state?.uncertaintyM) || Number(target.trackingDiagnostics?.uncertaintyM) || Math.max(3,innovation*.15),
                3,
                120
            );
            const raw=Eta.createRawSitePredictionFromMotion({motion,referenceTimeMs,site:this.site,uncertaintyM:trackUncertaintyM});
            const stabilizers=this.stabilizers(target);
            const display=stabilizers.zone.update(raw,referenceTimeMs);
            const arrivalRaw=Eta.createRawSitePredictionFromMotion({motion,referenceTimeMs,site:{...this.site,radius:this.site.arrivalRadius},uncertaintyM:trackUncertaintyM});
            const arrivalDisplay=stabilizers.arrival.update(arrivalRaw,referenceTimeMs);
            const truthTarget={...target,waypoints:(target.waypoints||[]).slice(target.waypointIndex??0)};
            const truthEtaSeconds=Eta.groundTruthEta(truthTarget,this.site);
            const rawErrorSeconds=raw.rawEtaSeconds===null||truthEtaSeconds===null?null:raw.rawEtaSeconds-truthEtaSeconds;
            const displayErrorSeconds=display.displayEtaSeconds===null||truthEtaSeconds===null?null:display.displayEtaSeconds-truthEtaSeconds;
            target.sitePrediction={raw,display,arrivalRaw,arrivalDisplay,truthEtaSeconds,rawErrorSeconds,displayErrorSeconds};
            const frame={timeMs:referenceTimeMs,truthEtaSeconds,rawEtaSeconds:raw.rawEtaSeconds,displayEtaSeconds:display.displayEtaSeconds,rawErrorSeconds,displayErrorSeconds,state:display.state,reason:raw.reason};
            const previous=target.etaEvaluation.at(-1);
            if(previous?.timeMs===referenceTimeMs)target.etaEvaluation[target.etaEvaluation.length-1]=frame;else target.etaEvaluation.push(frame);
            target.etaEvaluation=target.etaEvaluation.slice(-LIMITS.points);
            return target.sitePrediction;
        }
        updateEstimate(target,force=false) {
            if(!target)return null;
            const detected=this.reportingNodes(target);target.detectedNodeIds=detected.map(n=>n.id);
            const measurement=target.kind==='drone'&&!target.lost?estimateFromDetections(detected,target):null;
            target.rawEstimatedPosition=measurement;
            const localization=localizationQuality(detected);
            const timeMs=this.time*1000,tracker=this.tracker(target);
            let trackingResult=null;
            if(measurement&&(!tracker.hasState()||tracker.shouldAcceptMeasurement(timeMs))){
                trackingResult=tracker.update(measurement,timeMs,{
                    uncertaintyM:localization.uncertaintyM,
                    qualityScore:localization.qualityScore
                });
                target.trackingDiagnostics={
                    accepted:trackingResult.accepted,
                    reason:trackingResult.reason,
                    innovationM:trackingResult.innovationM??0,
                    gateM:trackingResult.gateM??null,
                    nodeCount:detected.length,
                    uncertaintyM:trackingResult.uncertaintyM??localization.uncertaintyM,
                    localizationUncertaintyM:localization.uncertaintyM,
                    localizationQualityScore:localization.qualityScore,
                    geometryQuality:localization.geometryQuality,
                    spreadM:localization.spreadM,
                    hullAreaM2:localization.hullAreaM2,
                    alphaUsed:trackingResult.alphaUsed??null,
                    betaUsed:trackingResult.betaUsed??null,
                    measurement:{...measurement}
                };
            }
            const state=tracker.predict(timeMs);
            target.trackState=state;
            target.estimatedPosition=state?{x:state.x,y:state.y}:null;
            if(target.estimatedPosition&&(force||!target.estimatedTrail.length||this.time-target.estimatedTrail.at(-1).time>=.18)){
                target.estimatedTrail.push({
                    ...target.estimatedPosition,
                    time:this.time,
                    measurementTimeMs:timeMs,
                    nodeCount:detected.length,
                    motionSegment:target.motionSegment??0,
                    source:'simulation_alpha_beta_track',
                    vx:state.vx,vy:state.vy,
                    innovationM:target.trackingDiagnostics?.innovationM??0,
                    uncertaintyM:state.uncertaintyM??null,
                    qualityScore:state.qualityScore??null
                });
                target.estimatedTrail=target.estimatedTrail.slice(-LIMITS.points);
            }
            return target.estimatedPosition;
        }
        positionTarget(id,p) {
            const t=this.targets.find(t=>t.id===id);if(!t||!point(p)) return false;
            this.resetPrediction(t,true);this.resetTracking(t);t.position={x:p.x,y:p.y};t.startPosition={x:p.x,y:p.y};t.waypointIndex=0;t.routeRunCount=0;t.routeReady=false;t.lost=false;t.waypoints=[];t.trail=[{...t.position,time:this.time}];t.estimatedTrail=[];t.etaEvaluation=[];t.replayFrames=[];this.updateEstimate(t,true);this.inspect();return true;
        }
        resetTargetToStart(target,{preserveRoute=true}={}) {
            if(!target||!point(target.startPosition))return false;
            target.position={...target.startPosition};
            target.waypointIndex=0;
            if(!preserveRoute)target.waypoints=[];
            target.routeReady=false;
            target.inside=false;
            target.lost=false;
            target.trail=[{...target.position,time:this.time}];
            target.estimatedTrail=[];
            target.etaEvaluation=[];
            target.replayFrames=[];
            this.resetPrediction(target,true);
            this.resetTracking(target);
            this.updateEstimate(target,true);
            return true;
        }
        completeTargetRoute(target) {
            if(!target||!target.waypoints.length)return false;
            this.preserveTargetHistory(target);
            target.routeRunCount=(target.routeRunCount??0)+1;
            target.routeReady=true;
            return true;
        }
        restartSimulation() {
            const routed=this.targets.filter(target=>target.waypoints.length&&point(target.startPosition)&&!target.lost);
            if(!routed.length)return false;
            this.playing=false;
            this.replay=null;
            this.alerts=[];
            this.preserveHistory();
            this.time=0;
            for(const target of routed)this.resetTargetToStart(target,{preserveRoute:true});
            this.inspect();
            this.playing=routed.some(target=>target.speed>0);
            return true;
        }
        clearRoute(id) {
            const target=this.targets.find(t=>t.id===id);
            if(!target)return false;
            this.preserveTargetHistory(target);
            if(point(target.startPosition))target.position={...target.startPosition};
            target.waypoints=[];
            target.waypointIndex=0;
            target.routeReady=false;
            target.trail=point(target.position)?[{...target.position,time:this.time}]:[];
            target.estimatedTrail=[];
            target.etaEvaluation=[];
            target.replayFrames=[];
            target.inside=false;
            this.resetPrediction(target,true);
            this.resetTracking(target);
            if(point(target.position))this.updateEstimate(target,true);
            this.inspect();
            return true;
        }
        loseTarget(id) { const t=this.targets.find(t=>t.id===id);if(t){t.lost=true;this.resetTracking(t);this.resetPrediction(t);this.alerts=this.alerts.filter(a=>a.targetId!==id);} }
        replayFrame(target,state=null) {
            if(!target)return null;
            const detected=this.reportingNodes(target),region=this.sourceRegion(target);
            return {
                time:this.time,
                targetId:target.id,
                kind:target.kind,
                site:copy(this.site),
                nodes:this.nodes.map(node=>({
                    id:node.id,ordinal:node.ordinal,name:node.name,x:node.x,y:node.y,
                    online:node.online,reporting:node.reporting,detectionRadius:node.detectionRadius,
                    active:detected.some(item=>item.id===node.id)
                })),
                detectedNodeIds:detected.map(node=>node.id),
                sourceRegion:{kind:region.kind,path:copy(region.path||[])},
                truePosition:point(target.position)?{x:target.position.x,y:target.position.y}:null,
                rawEstimatedPosition:point(target.rawEstimatedPosition)?copy(target.rawEstimatedPosition):null,
                estimatedPosition:point(target.estimatedPosition)?copy(target.estimatedPosition):null,
                trackState:target.trackState?copy(target.trackState):null,
                trackingDiagnostics:target.trackingDiagnostics?copy(target.trackingDiagnostics):null,
                system:copy(state||assessSystem(target,this.site)),
                prediction:target.sitePrediction?copy(target.sitePrediction):null
            };
        }
        recordReplayFrame(target,state=null) {
            if(!target)return;
            const frame=this.replayFrame(target,state);
            const previous=target.replayFrames.at(-1);
            if(previous?.time===frame.time)target.replayFrames[target.replayFrames.length-1]=frame;
            else target.replayFrames.push(frame);
            target.replayFrames=target.replayFrames.slice(-LIMITS.points);
        }
        inspect() {
            for(const target of this.targets) {
                this.updatePrediction(target);
                const state=assessSystem(target,this.site);
                if(state.status==='inside'&&!target.inside) {
                    this.alerts.push({id:this.id('ALERT'),targetId:target.id,time:this.time,simulation:true});
                    this.selectedId=target.id;
                }
                target.inside=state.status==='inside';
                this.recordReplayFrame(target,state);
            }
            this.alerts=this.alerts.slice(-LIMITS.targets);
        }
        acknowledge(id) { this.alerts=this.alerts.filter(a=>a.id!==id); }
        step(seconds) {
            if(!finite(seconds)||seconds<=0||seconds>60) return;
            this.time+=seconds;
            const completed=[];
            for(const target of this.targets) {
                if(!point(target.position)||target.lost||target.speed<=0||target.routeReady) continue;
                let remaining=seconds*target.speed;
                if(target.waypoints.length) {
                    while(remaining>0&&(target.waypointIndex??0)<target.waypoints.length) {
                        const p=target.waypoints[target.waypointIndex??0],dx=p.x-target.position.x,dy=p.y-target.position.y,d=Math.hypot(dx,dy);
                        if(d<=remaining) {
                            target.position={...p};remaining-=d;target.waypointIndex=(target.waypointIndex??0)+1;
                            if(target.waypointIndex>=target.waypoints.length){remaining=0;completed.push(target);}
                        } else {
                            target.position.x+=dx/d*remaining;target.position.y+=dy/d*remaining;
                            target.heading=(Math.atan2(dx,dy)*180/Math.PI+360)%360;remaining=0;
                        }
                    }
                } else {
                    const v=velocity(target);target.position.x+=v.x*seconds;target.position.y+=v.y*seconds;
                }
                target.trail.push({...target.position,time:this.time});target.trail=target.trail.slice(-LIMITS.points);this.updateEstimate(target);
            }
            this.inspect();
            for(const target of completed)this.completeTargetRoute(target);
            if(completed.length&&this.targets.every(target=>target.lost||target.speed<=0||(target.waypoints.length?target.routeReady:false)))this.playing=false;
        }
        replayEvent(eventId) {
            const event=this.events.find(e=>e.id===eventId),target=this.targets.find(t=>t.id===event?.targetId);
            if(!event) return false;
            this.playing=false;this.alerts=[];
            const points=copy(event.points?.length?event.points:target?.trail||[]),
                estimatedPoints=copy(event.estimatedPoints?.length?event.estimatedPoints:target?.estimatedTrail||[]),
                frames=copy(event.frames?.length?event.frames:target?.replayFrames||[]);
            const sampleCount=Math.max(points.length,estimatedPoints.length,frames.length);
            this.replay={eventId,targetId:event.targetId,kind:event.kind,points,estimatedPoints,frames,fraction:0,playing:sampleCount>1};
            return true;
        }
        preserveTargetHistory(target) {
            if(!target)return;
            const event=this.events.find(item=>item.targetId===target.id);
            if(!event)return;
            event.points=copy(target.trail);
            event.estimatedPoints=copy(target.estimatedTrail);
            event.frames=copy(target.replayFrames||[]);
        }
        preserveHistory() {
            for(const target of this.targets)this.preserveTargetHistory(target);
        }
        clearTargets(){this.preserveHistory();this.targets=[];this.alerts=[];this.selectedId=null;this.playing=false;this.etaStabilizers.clear();this.trackers.clear();}
        clearNodes(){this.preserveHistory();this.nodes=[];for(const target of this.targets){target.detectedNodeIds=[];target.etaEvaluation=[];this.resetTracking(target);this.resetPrediction(target);}}
        clearHistory(){this.events=[];this.replay=null;this.targets.forEach(t=>{t.etaEvaluation=[];t.replayFrames=[];});}
        leave() { this.playing=false;this.alerts=[];if(this.replay)this.replay.playing=false; }
        preset(name) {
            this.reset();
            const count=name==='one'?1:name==='two'?2:3;
            [{x:-220,y:-120},{x:220,y:-120},{x:0,y:240}].slice(0,count).forEach(p=>this.addNode(p));
            if(name==='idle') return;
            const options={position:{x:-500,y:0},speed:25,heading:90,kind:name==='non_drone'?'car':'drone'};
            if(name==='one') Object.assign(options,{position:{x:-220,y:-120},speed:0});
            if(name==='two') Object.assign(options,{position:{x:0,y:-120},speed:0});
            if(name==='three') Object.assign(options,{position:{x:0,y:0},speed:0});
            if(name==='depart') Object.assign(options,{position:{x:220,y:0},heading:90});
            if(name==='passby') Object.assign(options,{position:{x:-450,y:260},heading:90});
            if(name==='inside') Object.assign(options,{position:{x:60,y:20},speed:0});
            if(name==='missing') Object.assign(options,{position:null,speed:0});
            this.createEvent(options);
            if(name==='multiple') this.createEvent({position:{x:90,y:50},speed:0,heading:270});
            if(name==='lost') this.loseTarget(this.selectedId);
            if(name==='offline') {this.nodes[1].online=false;this.refreshEstimates(true);}
            this.playing=!['inside','missing','lost','non_drone','one','two','three'].includes(name);
        }
    }
    function replayTimeline(replay) {
        const candidates=[...(replay?.frames||[]).map(frame=>frame.time),...(replay?.points||[]).map(p=>p.time),...(replay?.estimatedPoints||[]).map(p=>p.time)].filter(finite);
        if(!candidates.length)return null;
        return {first:Math.min(...candidates),last:Math.max(...candidates)};
    }
    function replayTime(replay) {
        const timeline=replayTimeline(replay);
        return timeline?timeline.first+(timeline.last-timeline.first)*clamp(replay?.fraction??0,0,1):null;
    }
    function replayFrameAtTime(frames,time) {
        if(!Array.isArray(frames)||!frames.length||!finite(time))return null;
        let index=frames.findLastIndex(frame=>finite(frame.time)&&frame.time<=time);
        if(index<0)index=0;
        return frames[index]||null;
    }
    function replayPoint(replay) {
        const path=replay?.points||[],time=replayTime(replay);if(!path.length||!finite(time))return null;
        return replayPointAtTime(path,time);
    }
    function replayPointAtTime(path,time) {
        if(!path?.length||!finite(time)||time<path[0].time)return null;
        let index=path.findLastIndex(p=>p.time<=time);index=Math.max(0,index);
        const a=path[index],b=path[index+1];
        const f=b&&b.time>a.time?(time-a.time)/(b.time-a.time):0;
        return {x:a.x+(b?b.x-a.x:0)*clamp(f,0,1),y:a.y+(b?b.y-a.y:0)*clamp(f,0,1),time,index};
    }
    const names={drone:'無人機',car:'汽車',airplane:'飛機',rainfall:'雨聲',electric_saw:'電鋸'};
    const statuses={inside:'已進入警戒區',outside:'警戒區外',located:'已放置模擬位置',lost:'目標失聯',unlocated:'位置未知'};
    const trends={approaching:'往據點靠近',departing:'正在遠離據點',stationary:'停止或橫向移動'};
    const duration=seconds=>seconds===null?'—':seconds===0?'已到達':`${Math.ceil(seconds)} 秒`;
    const metric=(value,digits=1)=>finite(value)?Number(value).toFixed(digits):'—';
    const simTimestamp=value=>finite(value)?`T+${(value/1000).toFixed(2)}s`:'—';
    const predictionStates={STABLE:'穩定',HOLDING:'暫時保留',CLEARED:'已清除',UNSTABLE:'資料不足'};
    function predictionDebug(target){
        const prediction=target?.sitePrediction,raw=prediction?.raw||{},display=prediction?.display||{},motion=raw.motion||{};
        return `<details class="slab-prediction-debug"><summary>ETA 工程資訊 <small>${escape(predictionStates[display.state]||'無預測')}</small></summary><dl>
            <dt>Raw ETA</dt><dd>${duration(raw.rawEtaSeconds??null)}</dd><dt>Display ETA</dt><dd>${duration(display.displayEtaSeconds??null)}</dd>
            <dt>Raw 進入時間</dt><dd>${simTimestamp(raw.rawEntryTimeMs)}</dd><dt>平滑進入時間</dt><dd>${simTimestamp(display.smoothedEntryTimeMs)}</dd>
            <dt>回歸位置 x / y</dt><dd>${metric(motion.position?.x)} / ${metric(motion.position?.y)} m</dd><dt>速度 vx / vy</dt><dd>${metric(motion.vx,2)} / ${metric(motion.vy,2)} m/s</dd>
            <dt>速率 / 航向</dt><dd>${metric(motion.speed,2)} m/s / ${metric(motion.heading)}°</dd><dt>Track 不確定度</dt><dd>±${metric(motion.uncertaintyM??raw.trajectoryUncertaintyM)} m</dd>
            <dt>Tracker α / β</dt><dd>${metric(motion.alphaUsed,2)} / ${metric(motion.betaUsed,2)}</dd><dt>品質分數</dt><dd>${metric((motion.qualityScore??0)*100,0)}%</dd>
            <dt>樣本 / 時窗</dt><dd>${motion.sampleCount??0} / ${metric((motion.timeSpanMs??0)/1000,2)} s</dd>
            <dt>最大間隔 / RMSE</dt><dd>${metric(finite(motion.maximumGapMs)?motion.maximumGapMs/1000:null,2)} s / ${metric(motion.residualRmse)} m</dd><dt>Closing speed</dt><dd>${metric(raw.closingSpeed,2)} m/s</dd>
            <dt>CPA 距離 / 時間</dt><dd>${metric(raw.cpaDistance)} m / ${metric(raw.cpaTime)} s</dd><dt>軌跡不確定度</dt><dd>±${metric(raw.trajectoryUncertaintyM)} m</dd>
            <dt>交會判定</dt><dd>${escape(raw.rawIntersectionState||'UNAVAILABLE')} / ${escape(raw.mathematicalIntersection||'—')}</dd><dt>穩定器</dt><dd>${escape(display.state||'UNSTABLE')} · hold ${metric(display.holdAgeMs??0,0)} ms</dd>
            <dt>Reason</dt><dd>${escape(raw.reason||'NO_PREDICTION')}</dd><dt>真值 ETA（只供評估）</dt><dd>${duration(prediction?.truthEtaSeconds??null)}</dd>
            <dt>Raw / Display 誤差</dt><dd>${metric(prediction?.rawErrorSeconds)} / ${metric(prediction?.displayErrorSeconds)} s</dd><dt>資料來源</dt><dd>${escape(motion.source||'estimated trajectory only')}</dd>
        </dl><p>以上為模擬工程參數與評估資料，尚未經實地校正；真值不會送入 ETA 估算器。</p></details>`;
    }
    const clock=seconds=>`${Math.floor(seconds/60).toString().padStart(2,'0')}:${Math.floor(seconds%60).toString().padStart(2,'0')}`;
    const DRONE_PATH='M -9 -6 L 9 6 M -9 6 L 9 -6 M -13 -6 A 4 4 0 1 0 -5 -6 A 4 4 0 1 0 -13 -6 M 5 -6 A 4 4 0 1 0 13 -6 A 4 4 0 1 0 5 -6 M -13 6 A 4 4 0 1 0 -5 6 A 4 4 0 1 0 -13 6 M 5 6 A 4 4 0 1 0 13 6 A 4 4 0 1 0 5 6';
    const NODE_PATH='M 0 -1 A 1 1 0 1 1 0 1 A 1 1 0 1 1 0 -1';
    function nodeVisual(ordinal,online=true,active=false,pulse=.5) {
        return {
            shape:'circle',path:NODE_PATH,
            fill:active&&online?'#F97316':online?'#F8FAFC':'#475569',
            stroke:active&&online?'#FFB86B':online?'#111827':'#F8FAFC',
            opacity:online?1:.95,strokeWidth:active&&online?4:3,
            scale:active&&online?14+clamp(pulse,0,1)*6:14
        };
    }
    class Workspace {
        constructor(container) {
            this.container=container;this.model=new LabModel();this.model.preset('idle');this.active=false;this.timer=null;this.mode='inspect';this.editNode=null;this.editTarget=null;
            this.googleMap=null;this.googleOverlays=new Map();this.googleListener=null;this.fitted=false;this.lastTime=0;this.lastDetailAt=0;this.lastEffectAt=0;
            this.mount();
        }
        $(selector) { return this.container.querySelector(selector); }
        mount() {
            this.container.innerHTML=`<section class="slab" aria-label="獨立模擬工作區">
                <header class="slab-header"><div><span class="slab-eyebrow">SIMULATION LAB</span><h2>模擬工作區</h2><p>親手佈置節點、建立事件與演示警戒，所有操作都留在這個工作區。</p></div><strong class="slab-isolation">模擬資料 · 不影響即時系統</strong></header>
                <div class="slab-steps" aria-label="操作順序"><span><b>1</b> 放置節點並設定偵測半徑</span><span><b>2</b> 畫出無人機真實飛行路線</span><span><b>3</b> 比較真值與節點推估路徑</span></div>
                <div class="slab-presets"><label>快速展示 <select data-field="preset"><option value="approach">無人機接近 → 進入警戒</option><option value="idle">一般監控／沒有事件</option><option value="one">單節點偵測脈動</option><option value="two">兩節點連線</option><option value="three">三節點偵測範圍</option><option value="passby">旁側飛越、不會抵達</option><option value="depart">遠離據點</option><option value="inside">直接出現在警戒區內</option><option value="multiple">多目標、警戒優先</option><option value="missing">只有聲音回報、定位未完成</option><option value="lost">目標失聯</option><option value="offline">節點離線</option><option value="non_drone">非無人機聲音</option></select></label><button type="button" data-action="preset" class="slab-primary">載入展示</button><span>載入會取代目前的模擬內容。</span><div class="slab-clear-actions" aria-label="清除模擬資料"><button type="button" data-action="clear-targets">清空無人機／目標</button><button type="button" data-action="clear-nodes">清空節點</button><button type="button" data-action="clear-history">清空動畫回顧</button><button type="button" data-action="clear-all">全部清空</button></div></div>
                <div class="slab-layout"><aside class="slab-tools"><section class="slab-card"><h3><span>01</span> 佈置場景</h3><button type="button" data-action="place-site" class="slab-wide">◎ 點圖設定據點</button><label>警戒半徑（公尺）<input data-field="radius" type="number" min="20" max="5000" value="150"></label><button type="button" data-action="radius">更新模擬警戒區</button><div data-slot="site" class="slab-hint"></div><details class="slab-node-config" open><summary><span>節點設定</span><small data-slot="node-summary"></small></summary><div class="slab-node-config-body"><button type="button" data-action="place-node" class="slab-wide">＋ 點圖新增節點</button><label>全部節點偵測半徑（公尺）<input data-field="node-radius" type="number" min="20" max="5000" value="450"></label><button type="button" data-action="node-radius" class="slab-wide">更新全部節點偵測範圍</button><p class="slab-hint">最多可放置 ${LIMITS.nodes} 個節點，並共用同一個偵測半徑。只有線上、已勾選且無人機位於範圍內的節點才參與系統估測。</p><details class="slab-node-list"><summary><span>已放置節點</span><small data-slot="node-list-summary"></small></summary><div data-slot="nodes" class="slab-node-list-body"></div></details></div></details></section>
                <section class="slab-card"><h3><span>02</span> 逐台加入無人機</h3><label>聲音類型<select data-field="kind"><option value="drone">無人機 Drone</option><option value="car">汽車 Car</option><option value="airplane">飛機 Airplane</option><option value="rainfall">雨聲 Rainfall</option><option value="electric_saw">電鋸 Electric_saw</option></select></label><div class="slab-two"><label>速度（m/s）<input data-field="speed" type="number" min="0" max="100" value="25"></label><label>航向（度）<input data-field="heading" type="number" min="0" max="359" value="90"></label></div><p class="slab-hint">按下新增後直接在地圖點選這一架的起點，再從下方清單設定路徑。可逐架加入，單架也能直接模擬。</p><button type="button" data-action="create" class="slab-primary slab-wide">＋ 新增一架並點圖設起點</button><p data-slot="create-message" class="slab-create-message" role="status" aria-live="polite"></p><div data-slot="fleet" class="slab-fleet"></div></section></aside>
                <main class="slab-main"><section class="slab-card slab-map-card"><div class="slab-map-top"><h3>模擬現場</h3><span data-slot="clock">00:00</span><button type="button" data-action="fit">顯示全部位置</button></div><div data-slot="mode" class="slab-mode" role="status"></div><div class="slab-map-frame"><div data-slot="google" class="slab-google" hidden></div><svg data-slot="map" class="slab-map" viewBox="0 0 800 520" role="img" aria-label="可點擊的模擬位置圖"></svg><span class="slab-map-watermark">SIMULATION · 全部位置均為人為設定</span></div><div class="slab-legend"><span>● 白色：在線／灰色×：離線／淡圈：偵測範圍</span><span>◎ 據點／警戒圈</span><span class="slab-true-key">━ 真實飛行路線（觀察用）</span><span class="slab-estimate-key">┄ 系統估測路徑</span><span>橘色脈動／連線／區塊：正在參與系統估測</span></div><div class="slab-playbar"><button type="button" data-action="play" class="slab-primary">▶ 開始模擬</button><button type="button" data-action="restart-simulation" disabled>↺ 重新模擬</button><button type="button" data-action="step">前進 1 秒</button><label>播放速度<select data-field="rate"><option value="1">1×</option><option value="2">2×</option><option value="5">5×</option><option value="10">10×</option></select></label><button type="button" data-action="place-waypoint">點圖加入真實飛行路線</button><button type="button" data-action="stop-target">停止選取目標</button></div><p class="slab-hint">紫色路徑只供觀察模擬真值；警示、接近狀態、距離與 ETA 全部依藍色系統估測結果。至少兩個節點同時偵測才會產生估測位置。</p></section>
                <section class="slab-card slab-history"><h3>動畫回顧 <small>只包含本工作區建立的事件</small></h3><div data-slot="replay"></div><div data-slot="events"></div></section></main>
                <aside class="slab-detail"><section class="slab-card slab-important"><h3>重要資訊 <span class="slab-badge">主動更新</span></h3><div data-slot="targets"></div><div data-slot="detail"></div><div class="slab-two"><button type="button" data-action="lost">模擬目標失聯</button><button type="button" data-action="reconnect-target">恢復目標回報</button></div><button type="button" data-action="apply-motion" class="slab-wide">套用左側速度 / 航向至選取目標</button></section><section class="slab-card slab-notes"><h3>展示操作提示</h3><ul><li>節點設定可折疊，全部節點共用一個偵測半徑。</li><li>兩節點偵測時，可能聲源在線段中間；三個以上顯示包圍區域。</li><li>紫色真實路線只供比較；藍色系統估測路徑負責警示、接近判斷與 ETA。</li><li>節點離線或超出範圍後不參與推估，但位置仍保留。</li><li>有設定路徑的目標跑完後會停在終點；按「重新模擬」會回到起點並直接再跑一次。</li><li>離開工作區會暫停模擬並關閉警告。</li></ul></section></aside></div>
                <div data-slot="message" class="slab-message" role="status"></div><div data-slot="alert" class="slab-alert-host" aria-live="assertive"></div>
            </section>`;
            this.boundClick=e=>this.handleClick(e);this.boundChange=e=>this.handleChange(e);
            this.container.addEventListener('click',this.boundClick);this.container.addEventListener('change',this.boundChange);
            this.render();
        }
        enter() {
            if(this.active)return;this.active=true;this.lastTime=Date.now();this.tryGoogle();this.render();
            this.timer=root.setInterval(()=>{const now=Date.now(),elapsed=Math.min(1,(now-this.lastTime)/1000);this.lastTime=now;
                if(this.model.replay?.playing) {this.model.replay.fraction=Math.min(1,this.model.replay.fraction+elapsed/12*this.model.rate);if(this.model.replay.fraction>=1)this.model.replay.playing=false;this.renderMap();if(now-this.lastDetailAt>=500){this.lastDetailAt=now;this.renderReplay();this.renderDetail();}}
                else if(this.model.playing){this.model.step(elapsed*this.model.rate);this.$('[data-slot="clock"]').textContent=`模擬 ${clock(this.model.time)}`;if(now-this.lastDetailAt>=500){this.lastDetailAt=now;this.renderDetail();}this.renderAlert();this.renderMap();}
                else if(this.googleMap&&now-this.lastEffectAt>=250){this.lastEffectAt=now;this.renderGoogle();}
            },100);
        }
        leave() {this.active=false;if(this.timer)root.clearInterval(this.timer);this.timer=null;this.model.leave();this.render();}
        destroy() {this.leave();this.container.removeEventListener('click',this.boundClick);this.container.removeEventListener('change',this.boundChange);this.clearGoogle();if(this.googleListener?.remove)this.googleListener.remove();this.container.innerHTML='';}
        message(text) {this.$('[data-slot="message"]').textContent=text;}
        creatorMessage(text,error=false) {
            const slot=this.$('[data-slot="create-message"]');slot.textContent=text;slot.classList.toggle('is-error',error);
        }
        field(name) {return this.$(`[data-field="${name}"]`);}
        resetEditing() {this.mode='inspect';this.editNode=null;this.editTarget=null;this.model.replay=null;}
        resetCreator() {
            this.field('kind').value='drone';this.field('speed').value='25';this.field('heading').value='90';
            ['speed','heading'].forEach(name=>this.field(name).removeAttribute('aria-invalid'));this.creatorMessage('');this.renderCreateButton();
        }
        renderCreateButton() {
            const kind=this.field('kind').value;
            this.$('[data-action="create"]').textContent=kind==='drone'?'＋ 新增一架並點圖設起點':`＋ 新增${names[kind]||'目標'}並點圖設起點`;
        }
        readMotion() {
            const values={};
            for(const [name,min,max,label] of [['speed',0,100,'速度'],['heading',0,359,'航向']]) {
                const field=this.field(name),value=Number(field.value);
                field.removeAttribute('aria-invalid');
                if(!field.value.trim()||!finite(value)||value<min||value>max){
                    this.creatorMessage(`${label}需為 ${min}–${max}${name==='speed'?' m/s':'°'}，請修正後再新增。`,true);
                    field.setAttribute('aria-invalid','true');field.focus();return null;
                }
                values[name]=value;
            }
            return values;
        }
        setMode(mode,nodeId=null) {
            this.model.playing=false;this.model.replay=null;this.mode=mode;this.editNode=nodeId;
            this.editTarget=['move-target','waypoint'].includes(mode)?this.model.selectedId:null;
            this.renderMode();
        }
        handleClick(event) {
            const button=event.target.closest('[data-action]');
            if(button&&this.container.contains(button)) {
                const action=button.dataset.action,id=button.dataset.id,m=this.model;
                if(action==='preset'){m.preset(this.field('preset').value);this.resetEditing();this.resetCreator();this.field('radius').value=m.site.radius;this.field('node-radius').value=m.nodeDetectionRadius;this.fit();this.message('已載入模擬展示；所有內容僅存在於此工作區。');}
                else if(action==='clear-targets'){m.clearTargets();this.resetEditing();this.resetCreator();this.creatorMessage('已清空目標，可以重新新增無人機。');this.message('已清空目前無人機與其他目標；節點及動畫回顧保留。');}
                else if(action==='clear-nodes'){m.clearNodes();this.resetEditing();this.message('已清空節點；目標及動畫回顧保留。');}
                else if(action==='clear-history'){m.clearHistory();this.resetEditing();this.message('已清空動畫回顧；目前節點與目標保留。');}
                else if(action==='clear-all'){m.reset();this.resetEditing();this.resetCreator();this.field('radius').value=150;this.field('node-radius').value=m.nodeDetectionRadius;this.creatorMessage('已全部清空，可以重新新增無人機。');this.message('全部模擬內容已清空，即時系統未變更。');}
                else if(action==='place-node')this.setMode('node');
                else if(action==='place-site')this.setMode('site');
                else if(action==='move-node')this.setMode('move-node',id);
                else if(action==='edit-target-start'){m.selectedId=id;this.editTarget=id;this.setMode('move-target');}
                else if(action==='edit-target-route'){m.selectedId=id;m.replay=null;this.editTarget=id;const t=m.selected();if(!point(t?.position)||t?.lost)this.message('這台目標需要先設定有效起點。');else{if(t.routeReady){m.resetTargetToStart(t,{preserveRoute:true});m.inspect();}this.setMode('waypoint');}}
                else if(action==='clear-target-route'){m.playing=false;if(m.clearRoute(id))this.message('已清空這台目標的飛行路徑並回到起點；歷史回顧保留。');}
                else if(action==='toggle-node'){const n=m.nodes.find(n=>n.id===id);if(n){n.online=!n.online;m.refreshEstimates(true);}}
                else if(action==='remove-node'){m.nodes=m.nodes.filter(n=>n.id!==id);m.refreshEstimates(true);}
                else if(action==='node-radius'){if(!m.setAllNodeDetectionRadius(this.field('node-radius').value))this.message('節點偵測半徑需為 20 到 5000 公尺。');else this.message(`已將全部節點偵測半徑更新為 ${m.nodeDetectionRadius} 公尺。`);}
                else if(action==='radius'){const radius=Number(this.field('radius').value);if(!m.setSite(m.site,radius))this.message('請輸入 20 到 5000 公尺的警戒半徑。');else this.message('已更新模擬警戒區。');}
                else if(action==='place-waypoint'){if(!point(m.selected()?.position)||m.selected()?.lost)this.message('請先建立或選取一個有位置且正在回報的目標。');else this.setMode('waypoint');}
                else if(action==='create'){
                    const motion=this.readMotion();if(!motion)return;
                    const target=m.createEvent({kind:this.field('kind').value,position:null,...motion});
                    if(!target)this.creatorMessage(`最多展示 ${LIMITS.targets} 個目標，請先清空目前目標。`,true);
                    else {
                        m.selectedId=target.id;this.setMode('move-target');
                        // Update the creation result before rendering map/history panels.
                        this.renderFleet();this.creatorMessage(`已新增${names[target.kind]} ${target.id.replace('SIM-TARGET-','#')}。請在地圖點選起點；場景已暫停，可先逐台設定。`);
                    }
                }
                else if(action==='play'){this.resetEditing();if(m.playing)m.playing=false;else{const runnable=m.targets.some(t=>point(t.position)&&!t.lost&&t.speed>0&&(!t.waypoints.length||!t.routeReady));if(runnable)m.playing=true;else this.message('本輪已完成；按「重新模擬」即可回到起點並再次播放同一路徑。');}}
                else if(action==='restart-simulation'){this.resetEditing();if(m.restartSimulation())this.message('已回到起點，開始重新模擬同一路徑。');else this.message('目前沒有可重新模擬的已設定路徑。');}
                else if(action==='step'){m.replay=null;m.playing=false;m.step(1);}
                else if(action==='select-target'){this.resetEditing();m.selectedId=id;}
                else if(action==='stop-target'){const t=m.selected();if(t){t.speed=0;}else this.message('請先選擇目標。');}
                else if(action==='lost')m.loseTarget(m.selectedId);
                else if(action==='reconnect-target'){const t=m.selected();if(t){t.lost=false;m.updateEstimate(t,true);m.inspect();}}
                else if(action==='apply-motion'){const t=m.selected(),speed=Number(this.field('speed').value),heading=Number(this.field('heading').value);if(!t)this.message('請先建立或選取目標。');else if(!finite(speed)||speed<0||speed>100||!finite(heading)||heading<0||heading>=360)this.message('請確認速度與航向範圍。');else{t.speed=speed;t.heading=heading;t.waypoints=[];t.waypointIndex=0;t.routeReady=false;this.message('已套用指定運動值，原飛行路徑已清除。');}}
                else if(action==='replay'){m.replayEvent(id);this.mode='inspect';}
                else if(action==='replay-play'){if(m.replay){if(m.replay.fraction>=1)m.replay.fraction=0;m.replay.playing=!m.replay.playing;}}
                else if(action==='replay-restart'){if(m.replay){m.replay.fraction=0;m.replay.playing=Math.max(m.replay.points.length,m.replay.estimatedPoints.length,m.replay.frames?.length||0)>1;}}
                else if(action==='replay-close')m.replay=null;
                else if(action==='ack')m.acknowledge(id);
                else if(action==='cancel-mode')this.resetEditing();
                else if(action==='fit')this.fit();
                this.render();return;
            }
            const svg=event.target.closest('[data-slot="map"]');
            if(svg&&this.mode!=='inspect'){
                const matrix=svg.getScreenCTM();if(!matrix)return;
                const p=svg.createSVGPoint();p.x=event.clientX;p.y=event.clientY;
                const local=p.matrixTransform(matrix.inverse());this.mapClick(this.unproject(local));
            }
        }
        handleChange(event) {
            const el=event.target;
            if(el.dataset.nodeCheck){const n=this.model.nodes.find(n=>n.id===el.dataset.nodeCheck);if(n){n.reporting=el.checked;this.model.refreshEstimates(true);this.render();}}
            else if(el.dataset.field==='kind'){this.renderCreateButton();this.creatorMessage('');}
            else if(el.dataset.field==='rate'){this.model.rate=clamp(Number(el.value)||1,1,10);}
            else if(el.dataset.field==='replay-range'&&this.model.replay){this.model.replay.fraction=clamp(Number(el.value)/100,0,1);this.model.replay.playing=false;this.renderMap();this.renderReplay();this.renderDetail();}
        }
        mapClick(p) {
            if(!point(p)){this.message('請在模擬地圖範圍內放置位置。');return;}
            if(this.mode==='node'){if(!this.model.addNode(p))this.message(`最多放置 ${LIMITS.nodes} 個模擬節點。`);else {this.model.refreshEstimates(true);this.message('已新增模擬節點，可設定偵測半徑或繼續點擊新增。');}}
            else if(this.mode==='move-node'){const moved=this.model.moveNode(this.editNode,p);this.resetEditing();this.message(moved?'已移動模擬節點。':'此節點已不存在，請重新選擇或新增節點。');}
            else if(this.mode==='move-target'){
                const id=this.editTarget,moved=this.model.positionTarget(id,p);this.resetEditing();
                if(moved){this.model.selectedId=id;this.creatorMessage('已設定起點。可從清單設定路徑，或繼續新增下一架。');}
                else this.creatorMessage('此目標已不存在，請按「新增一架」重新建立。',true);
            }
            else if(this.mode==='site'){this.model.setSite(p);this.mode='inspect';this.message('已設定模擬據點與警戒區。');}
            else if(this.mode==='waypoint'){const t=this.model.targets.find(t=>t.id===this.editTarget);if(t&&point(t.startPosition||t.position)){if(!t.startPosition)t.startPosition={...t.position};t.waypoints.push({...p});t.waypointIndex=0;t.routeReady=false;if(!t.speed)t.speed=clamp(Number(this.field('speed').value)||25,1,100);this.message(`已加入第 ${t.waypoints.length} 個路徑點；路徑會保留，跑完後會停在終點。`);}else{this.resetEditing();this.creatorMessage('此目標已不存在或尚未設定起點，請重新選擇。',true);}}
            this.render();
        }
        renderMode(){
            const labels={inspect:'可先選擇快速展示，或用左側工具親手佈置場景。',node:'正在新增節點：點擊地圖，可連續放置。','move-node':'正在移動節點：點擊新位置。','move-target':'正在設定選取無人機的起點：點擊地圖。',site:'正在設定據點：點擊地圖，警戒圈會一起移動。',waypoint:'正在設定選取無人機的飛行路徑：依序點擊加入路徑點。'};
            this.$('[data-slot="mode"]').innerHTML=`<span>${labels[this.mode]}</span>${this.mode!=='inspect'?'<button type="button" data-action="cancel-mode">完成選點</button>':''}`;
            this.$('[data-slot="map"]').classList.toggle('slab-picking',this.mode!=='inspect');
            if(this.googleMap)this.googleMap.setOptions({draggableCursor:this.mode==='inspect'?null:'crosshair'});
        }
        render() {
            const m=this.model;
            this.renderMode();this.$('[data-slot="clock"]').textContent=`模擬 ${clock(m.time)}`;
            this.$('[data-action="play"]').textContent=m.playing?'Ⅱ 暫停模擬':'▶ 開始／繼續模擬';
            const restart=this.$('[data-action="restart-simulation"]');
            if(restart)restart.disabled=m.playing||!m.targets.some(t=>t.routeReady);
            this.field('rate').value=m.rate;
            this.field('node-radius').value=m.nodeDetectionRadius;
            this.$('[data-slot="node-summary"]').textContent=`${m.nodes.length} 個 · ${m.nodeDetectionRadius} m`;
            this.$('[data-slot="node-list-summary"]').textContent=m.nodes.length?`${m.nodes.length} / ${LIMITS.nodes} 個`:'0 個';
            this.$('[data-slot="nodes"]').innerHTML=m.nodes.length?m.nodes.map(n=>`<div class="slab-node-row"><label class="slab-check"><input type="checkbox" data-node-check="${n.id}" ${n.reporting?'checked':''} aria-label="${escape(n.name)} 啟用偵測"><b>${escape(n.name)}</b></label><span class="${n.online?'slab-online':'slab-offline'}">${n.online?'線上':'離線'}</span><div class="slab-node-actions"><button type="button" data-action="move-node" data-id="${n.id}">移動</button><button type="button" data-action="toggle-node" data-id="${n.id}">${n.online?'離線':'上線'}</button><button type="button" data-action="remove-node" data-id="${n.id}" aria-label="刪除 ${escape(n.name)}">×</button></div></div>`).join(''):'<p class="slab-empty">尚未放置節點。按「點圖新增節點」後點擊地圖。</p>';
            const site=latLng(m.site);this.$('[data-slot="site"]').textContent=`據點：${site.lat.toFixed(5)}, ${site.lng.toFixed(5)} · 警戒 ${m.site.radius} m · 抵達 ${m.site.arrivalRadius} m`;
            this.renderFleet();
            this.renderDetail();this.renderReplay();this.renderAlert();this.renderMap(true);
        }
        renderFleet(){
            const targets=this.model.targets,slot=this.$('[data-slot="fleet"]');if(!slot)return;
            slot.innerHTML=targets.length?`<h4>目標路徑設定 <small>${targets.length} 個 · 跑完停在終點</small></h4>${targets.map(t=>`<div class="slab-fleet-row ${t.id===this.model.selectedId?'is-selected':''}"><button type="button" data-action="select-target" data-id="${t.id}" class="slab-fleet-name">${escape(names[t.kind])} ${t.id.replace('SIM-TARGET-','#')}</button><span>起點 ${point(t.startPosition||t.position)?'已設定':'未設定'} · 路徑 ${t.waypoints.length} 點${t.routeRunCount? ` · 已完成 ${t.routeRunCount} 次${t.routeReady?' · 停在終點':''}`:''}</span><button type="button" data-action="edit-target-start" data-id="${t.id}">設起點</button><button type="button" data-action="edit-target-route" data-id="${t.id}">設路徑</button><button type="button" data-action="clear-target-route" data-id="${t.id}" ${t.waypoints.length?'':'disabled'}>清空路徑</button></div>`).join('')}`:'<p class="slab-hint">新增一架無人機後，這裡會顯示它的起點與路徑；可繼續逐架加入。</p>';
        }
        renderDetail() {
            const m=this.model,t=m.selected(),slot=this.$('[data-slot="detail"]');
            if(m.replay){
                const time=replayTime(m.replay),frame=replayFrameAtTime(m.replay.frames,time);
                this.$('[data-slot="targets"]').innerHTML='<span class="slab-system-label">歷史系統快照</span>';
                if(!frame){slot.innerHTML='<p class="slab-hint">此歷史事件沒有系統快照資料。</p>';return;}
                const system=frame.system||{},prediction=frame.prediction||{},detected=frame.nodes?.filter(n=>n.active)||[],
                    estimated=point(frame.estimatedPosition)?latLng(frame.estimatedPosition):null,
                    raw=point(frame.rawEstimatedPosition)?latLng(frame.rawEstimatedPosition):null,
                    online=(frame.nodes||[]).filter(n=>n.online).length;
                slot.innerHTML=`<div class="slab-target-heading"><span class="slab-target-icon">${frame.kind==='drone'?'✣':'◉'}</span><div><h4>歷史回顧 · ${escape(names[frame.kind]||frame.kind)}</h4><small>${escape(frame.targetId||m.replay.targetId||'')}</small></div></div>
                    <span class="slab-system-label">T+${Number(frame.time).toFixed(1)}s 當時系統狀態</span>
                    <strong class="slab-target-status ${system.status==='inside'?'slab-danger':''}">${escape(statuses[system.status]||system.status||'—')}${system.trend?` · ${escape(trends[system.trend]||system.trend)}`:''}</strong>
                    <div class="slab-metrics">
                        <div><span>在線節點</span><b>${online} / ${frame.nodes?.length||0}</b></div>
                        <div><span>參與偵測節點</span><b>${detected.length}</b></div>
                        <div><span>系統估測距據點</span><b>${finite(system.distance)?Math.round(system.distance)+' m':'—'}</b></div>
                        <div><span>預估進入警戒</span><b>${duration(prediction.display?.displayEtaSeconds??system.zoneEta??null)}</b></div>
                        <div><span>預估抵達據點</span><b>${duration(prediction.arrivalDisplay?.displayEtaSeconds??system.arrivalEta??null)}</b></div>
                        <div><span>預測狀態</span><b class="slab-metric-small">${escape(predictionStates[prediction.display?.state]||prediction.raw?.reason||'資料不足')}</b></div>
                    </div>
                    <p class="slab-hint">當時參與：${detected.map(n=>escape(n.name)).join('、')||'無'}${raw?`<br>Raw 定位：${raw.lat.toFixed(5)}, ${raw.lng.toFixed(5)}`:''}${estimated?`<br>Track 定位：${estimated.lat.toFixed(5)}, ${estimated.lng.toFixed(5)}`:''}</p>
                    ${frame.kind==='drone'&&prediction?predictionDebug({sitePrediction:prediction}):''}
                    <p class="slab-disclaimer">此區顯示的是當時已保存的節點、定位與預測快照，不會用目前節點狀態重新計算。</p>`;
                return;
            }
            const targetMenuKey=JSON.stringify([m.selectedId,m.targets.map(item=>[item.id,item.kind,assessSystem(item,m.site).status])]);
            if(this.targetMenuKey!==targetMenuKey){
            this.targetMenuKey=targetMenuKey;
            this.$('[data-slot="targets"]').innerHTML=m.targets.length?`<label>目前目標<select data-field="target-select">${m.targets.map(item=>`<option value="${item.id}" ${item.id===m.selectedId?'selected':''}>${escape(names[item.kind])} · ${item.id.replace('SIM-TARGET-','#')}${assessSystem(item,m.site).status==='inside'?' · 系統警戒中':''}</option>`).join('')}</select></label>`:'';
            const select=this.field('target-select');if(select)select.onchange=()=>{this.resetEditing();m.selectedId=select.value;this.render();};
            }
            if(!t){slot.innerHTML=`<div class="slab-idle-icon">◎</div><h4>一般節點監控</h4><p>尚無模擬事件</p><div class="slab-metrics"><div><span>線上節點</span><b>${m.nodes.filter(n=>n.online).length} / ${m.nodes.length}</b></div><div><span>模擬警戒半徑</span><b>${m.site.radius} m</b></div></div><p class="slab-hint">建立事件後，這裡會自動顯示目標資訊。</p>`;return;}
            const a=assessSystem(t,m.site),position=point(t.position)?latLng(t.position):null,detected=m.reportingNodes(t),region=m.sourceRegion(t),estimated=point(t.estimatedPosition)?latLng(t.estimatedPosition):null,prediction=t.sitePrediction;
            const regionLabel={none:'無',circle:'單節點偵測圈',line:'兩節點之間',polygon:`${detected.length} 節點包圍區域`}[region.kind];
            const error=point(t.estimatedPosition)&&point(t.position)?Math.round(distance(t.estimatedPosition,t.position)):null;
            slot.innerHTML=`<div class="slab-target-heading"><span class="slab-target-icon">${t.kind==='drone'?'✣':'◉'}</span><div><h4>${escape(names[t.kind])}</h4><small>${t.id}</small></div></div><span class="slab-system-label">系統判斷（依藍色估測）</span><strong class="slab-target-status ${a.status==='inside'?'slab-danger':''}">${statuses[a.status]}${a.trend?` · ${trends[a.trend]}`:''}</strong><div class="slab-metrics"><div><span>系統估測距據點</span><b>${a.distance===null?'—':Math.round(a.distance)+' m'}</b></div><div><span>同時偵測節點</span><b>${detected.length}</b></div><div><span>可能聲源區域</span><b class="slab-metric-small">${regionLabel}</b></div><div><span>推估誤差</span><b>${error===null?'—':error+' m'}</b></div><div><span>系統預估進入警戒</span><b>${t.kind==='drone'?duration(a.zoneEta):'不適用'}</b><small>${t.kind==='drone'?escape(predictionStates[prediction?.display?.state]||'資料不足'):''}${prediction?.display?.displayEtaLowerSeconds!=null&&prediction?.display?.displayEtaUpperSeconds!=null?` · 約 ${Math.ceil(prediction.display.displayEtaLowerSeconds)}–${Math.ceil(prediction.display.displayEtaUpperSeconds)} 秒`:''}</small></div><div><span>系統預估抵達據點</span><b>${t.kind==='drone'?duration(a.arrivalEta):'不適用'}</b><small>${prediction?.arrivalDisplay?.displayEtaLowerSeconds!=null&&prediction?.arrivalDisplay?.displayEtaUpperSeconds!=null?`約 ${Math.ceil(prediction.arrivalDisplay.displayEtaLowerSeconds)}–${Math.ceil(prediction.arrivalDisplay.displayEtaUpperSeconds)} 秒`:''}</small></div></div><p class="slab-hint">${position?`${t.lost?'最後模擬真實位置':'模擬真實位置（僅供比較）'}：${position.lat.toFixed(5)}, ${position.lng.toFixed(5)}`:'尚未設定模擬起點。'}${estimated?`<br>系統估測位置：${estimated.lat.toFixed(5)}, ${estimated.lng.toFixed(5)}`:'<br>系統估測位置：至少需兩個節點同時偵測'}</p><p class="slab-hint">偵測節點：${detected.map(n=>escape(n.name)).join('、')||'目前沒有'}<br>真實軌跡 ${t.trail.length} 點 · 系統估測軌跡 ${t.estimatedTrail.length} 點</p>${t.kind==='drone'?predictionDebug(t):''}<p class="slab-disclaimer">警示、接近狀態、距離與 ETA 只採用系統估測。紫色真實路徑只供模擬比較；實際定位仍需 TDOA／時間同步資料與實地驗證。</p>`;
        }
        renderAlert() {
            const alerts=this.active&&!this.model.replay?this.model.alerts:[],alert=alerts[0];
            const key=JSON.stringify([alerts.map(a=>a.id),this.model.site.radius]);
            if(this.alertKey===key)return;
            this.alertKey=key;
            this.$('[data-slot="alert"]').innerHTML=alert?`<section class="slab-alert" role="alertdialog" aria-modal="false" aria-label="系統估測進入警戒區警告"><div class="slab-alert-icon">!</div><div><span class="slab-badge">SIMULATION · 系統估測警告</span><h3>系統推估無人機進入警戒區</h3><p>${alert.targetId} · 模擬據點 · ${clock(alert.time)}</p><p>藍色估測路徑已進入 ${this.model.site.radius} 公尺警戒範圍${alerts.length>1?` · 另有 ${alerts.length-1} 則模擬警告`:''}</p></div><button type="button" data-action="ack" data-id="${alert.id}" class="slab-primary">確認模擬警告</button></section>`:'';
        }
        renderReplay() {
            const replay=this.model.replay,slot=this.$('[data-slot="replay"]');
            if(replay){
                const time=replayTime(replay),frame=replayFrameAtTime(replay.frames,time),sampleCount=Math.max(replay.points.length,replay.estimatedPoints.length,replay.frames?.length||0),canPlay=sampleCount>1;
                if(finite(time))this.$('[data-slot="clock"]').textContent=`回顧 T+${time.toFixed(1)}s`;
                const snapshot=frame?`<p class="slab-hint">目前回顧 T+${frame.time.toFixed(1)}s · 在線 ${frame.nodes.filter(n=>n.online).length}/${frame.nodes.length} · 參與 ${frame.nodes.filter(n=>n.active).length} 節點 · 警戒 ETA ${duration(frame.prediction?.display?.displayEtaSeconds??null)} · 抵達 ETA ${duration(frame.prediction?.arrivalDisplay?.displayEtaSeconds??null)}</p>`:'';
                slot.innerHTML=`<div class="slab-replay"><b>回顧 ${replay.eventId}</b><p>同步回放真實路徑、Track 路徑、當時節點狀態與 ETA/CPA 預測快照。</p>${snapshot}<div class="slab-playbar"><button type="button" data-action="replay-play" ${canPlay?'':'disabled'}>${replay.playing?'Ⅱ 暫停回顧':'▶ 播放回顧'}</button><button type="button" data-action="replay-restart" ${canPlay?'':'disabled'}>重播</button><input data-field="replay-range" aria-label="模擬歷史回顧時間軸" type="range" min="0" max="100" value="${Math.round(replay.fraction*100)}" ${canPlay?'':'disabled'}><span>${Math.round(replay.fraction*100)}%</span><button type="button" data-action="replay-close">返回模擬現場</button></div></div>`;
            }else slot.innerHTML='<p class="slab-hint">點選下方事件，可回放當時節點狀態、定位、Track 與 ETA/CPA 預測。</p>';
            this.$('[data-slot="events"]').innerHTML=this.model.events.length?this.model.events.slice(0,20).map(e=>`<button class="slab-event ${replay?.eventId===e.id?'is-selected':''}" data-action="replay" data-id="${e.id}"><span>${clock(e.time)} · ${names[e.kind]}</span><small>${e.id}</small><b>系統回顧 →</b></button>`).join(''):'<p class="slab-empty">尚無模擬事件</p>';
        }
        bounds() {
            const replayFrames=this.model.replay?.frames||[];
            const historicalNodes=replayFrames.flatMap(frame=>frame.nodes||[]),historicalSites=replayFrames.map(frame=>frame.site).filter(point);
            const points=[this.model.site,...this.model.nodes,...historicalSites,...historicalNodes,...this.model.targets.filter(t=>point(t.position)).map(t=>t.position),...this.model.targets.flatMap(t=>t.waypoints),...this.model.targets.flatMap(t=>t.estimatedTrail),...(this.model.replay?.points||[]),...(this.model.replay?.estimatedPoints||[])];
            let minX=-600,maxX=600,minY=-390,maxY=390;
            for(const p of points){minX=Math.min(minX,p.x-100);maxX=Math.max(maxX,p.x+100);minY=Math.min(minY,p.y-100);maxY=Math.max(maxY,p.y+100);}
            const site=this.model.site;minX=Math.min(minX,site.x-site.radius-80);maxX=Math.max(maxX,site.x+site.radius+80);minY=Math.min(minY,site.y-site.radius-80);maxY=Math.max(maxY,site.y+site.radius+80);
            for(const node of this.model.nodes){const radius=Math.max(20,node.detectionRadius||0);minX=Math.min(minX,node.x-radius-30);maxX=Math.max(maxX,node.x+radius+30);minY=Math.min(minY,node.y-radius-30);maxY=Math.max(maxY,node.y+radius+30);}
            const scale=Math.min(760/(maxX-minX),480/(maxY-minY));return {cx:(minX+maxX)/2,cy:(minY+maxY)/2,scale};
        }
        project(p) {const b=this.mapBounds;return {x:400+(p.x-b.cx)*b.scale,y:260-(p.y-b.cy)*b.scale};}
        unproject(p) {const b=this.mapBounds;return {x:(p.x-400)/b.scale+b.cx,y:(260-p.y)/b.scale+b.cy};}
        renderMap(refit=false) {
            if(refit||!this.mapBounds)this.mapBounds=this.bounds();
            const m=this.model,p=this.project.bind(this),replay=m.replay,replayT=replay?replayTime(replay):null,replayFrame=replay?replayFrameAtTime(replay.frames,replayT):null,
                siteModel=replayFrame?.site||m.site,site=p(siteModel),nodeModels=replayFrame?.nodes||m.nodes,
                detectedIds=new Set(replayFrame?.detectedNodeIds||(!replay?m.reportingNodes().map(n=>n.id):[])),
                geometry=replayFrame?.sourceRegion?.path||(!replay?m.geometry():[]);
            const nodes=nodeModels.map(n=>{const xy=p(n),active=replayFrame?Boolean(n.active):detectedIds.has(n.id)&&m.selected()?.kind==='drone'&&!m.selected()?.lost,range=n.detectionRadius*this.mapBounds.scale,visual=nodeVisual(n.ordinal,n.online,active);return `<circle class="slab-detection-range ${active?'is-active':''}" cx="${xy.x}" cy="${xy.y}" r="${range}"/>${active?`<circle class="slab-pulse" cx="${xy.x}" cy="${xy.y}" r="20"/>`:''}<g class="slab-node shape-${visual.shape} ${active?'is-active':''} ${n.online?'':'is-offline'}" transform="translate(${xy.x},${xy.y})"><g transform="scale(8)"><path class="slab-node-symbol" d="${visual.path}"/></g><text y="27">${escape(n.name)} · ${n.detectionRadius}m${n.online?'':' · 離線'}</text></g>`;}).join('');
            const region=geometry.length>=2?`<${geometry.length===2?'polyline':'polygon'} class="slab-reporting-region" points="${geometry.map(n=>{const q=p(n);return `${q.x},${q.y}`;}).join(' ')}"/>`:'';
            let targets='';
            if(replay){const current=replayPoint(replay),estimated=current?replayPointAtTime(replay.estimatedPoints,current.time):null;if(current){const q=p(current),path=replay.points.slice(0,current.index+1).concat(current);targets=`<polyline class="slab-true-trail" points="${path.map(n=>{const r=p(n);return `${r.x},${r.y}`;}).join(' ')}"/>${this.targetSvg(q,replay.kind,'真實路徑',false,true)}`;}if(estimated){const q=p(estimated),path=replay.estimatedPoints.slice(0,estimated.index+1).concat(estimated);targets+=`<polyline class="slab-estimated-trail" points="${path.map(n=>{const r=p(n);return `${r.x},${r.y}`;}).join(' ')}"/>${this.estimateSvg(q)}`;}}
            else for(const target of m.targets){if(!point(target.position))continue;const q=p(target.position);const path=target.trail.map(n=>{const r=p(n);return `${r.x},${r.y}`;}).join(' '),estimated=target.estimatedTrail.map(n=>{const r=p(n);return `${r.x},${r.y}`;}).join(' ');targets+=`<polyline class="slab-true-trail ${target.id===m.selectedId?'':'is-muted'}" points="${path}"/>`;if(estimated)targets+=`<polyline class="slab-estimated-trail ${target.id===m.selectedId?'':'is-muted'}" points="${estimated}"/>`;if(target.waypoints.length&&point(target.startPosition))targets+=`<polyline class="slab-waypoints" points="${[target.startPosition,...target.waypoints].map(n=>{const r=p(n);return `${r.x},${r.y}`;}).join(' ')}"/>`;targets+=this.targetSvg(q,target.kind,target.id.replace('SIM-TARGET-','#'),target.lost,target.id===m.selectedId);if(point(target.estimatedPosition)&&target.id===m.selectedId)targets+=this.estimateSvg(p(target.estimatedPosition));}
            this.$('[data-slot="map"]').innerHTML=`<defs><pattern id="slab-grid" width="40" height="40" patternUnits="userSpaceOnUse"><path d="M40 0H0V40" fill="none" stroke="currentColor" stroke-opacity=".1"/></pattern></defs><rect width="800" height="520" fill="url(#slab-grid)"/><text class="slab-north" x="770" y="30">N ↑</text><circle class="slab-zone" cx="${site.x}" cy="${site.y}" r="${siteModel.radius*this.mapBounds.scale}"/>${region}<g class="slab-site" transform="translate(${site.x},${site.y})"><circle r="8"/><path d="M-13 0H13M0-13V13"/><text y="28">模擬據點</text></g>${nodes}${targets}<text class="slab-scale" x="20" y="495">${Math.round(100/this.mapBounds.scale)} m / 圖上 100 單位 · 相對位置圖</text>`;
            if(this.googleMap)this.renderGoogle();
        }
        targetSvg(p,kind,label,lost,selected){return `<g class="slab-aircraft ${lost?'is-lost':''} ${selected?'is-selected':''}" transform="translate(${p.x},${p.y})"><circle class="slab-target-halo" r="24"/>${kind==='drone'?`<path d="${DRONE_PATH}"/>`:'<circle r="7"/>'}<text y="39">${escape(label)}${lost?' · 失聯':''}</text></g>`;}
        estimateSvg(p){return `<g class="slab-estimate-marker" transform="translate(${p.x},${p.y})"><circle class="slab-estimate-halo" r="24"/><path d="${DRONE_PATH}"/><text y="39">節點推估</text></g>`;}
        tryGoogle(){
            if(this.googleMap||!root.google?.maps?.Map)return;
            try{this.googleMap=new root.google.maps.Map(this.$('[data-slot="google"]'),{center:ORIGIN,zoom:16,mapTypeControl:false,streetViewControl:false,fullscreenControl:false,gestureHandling:'cooperative',clickableIcons:false});
                this.googleListener=this.googleMap.addListener('click',event=>{if(this.mode!=='inspect'&&event.latLng)this.mapClick(offset({lat:event.latLng.lat(),lng:event.latLng.lng()}));});
                this.$('[data-slot="google"]').hidden=false;this.$('[data-slot="map"]').setAttribute('hidden','');this.renderGoogle();this.fit();
            }catch{this.googleMap=null;this.$('[data-slot="google"]').hidden=true;this.$('[data-slot="map"]').removeAttribute('hidden');}
        }
        clearGoogle(){this.googleOverlays.forEach(o=>o.setMap(null));this.googleOverlays.clear();}
        googleOverlay(key,Type,options,used){let overlay=this.googleOverlays.get(key);if(!overlay){overlay=new Type({...options,map:this.googleMap});this.googleOverlays.set(key,overlay);}else overlay.setOptions({...options,map:this.googleMap});used.add(key);return overlay;}
        renderGoogle(){
            const g=root.google.maps,m=this.model,used=new Set(),put=(key,Type,options)=>this.googleOverlay(key,Type,options,used),
                replay=m.replay,replayT=replay?replayTime(replay):null,replayFrame=replay?replayFrameAtTime(replay.frames,replayT):null,
                siteModel=replayFrame?.site||m.site,nodeModels=replayFrame?.nodes||m.nodes;
            put('site-zone',g.Circle,{center:latLng(siteModel),radius:siteModel.radius,strokeColor:'#FBBF24',strokeOpacity:.8,strokeWeight:2,fillColor:'#FBBF24',fillOpacity:.1,clickable:false});
            put('site-marker',g.Marker,{position:latLng(siteModel),label:{text:'據點',color:'#0B1220',fontWeight:'700'},icon:{path:g.SymbolPath.CIRCLE,scale:16,fillColor:'#5EEAD4',fillOpacity:1,strokeColor:'#0B1220',strokeWeight:2},clickable:false});
            const target=m.selected(),liveDetected=!replay&&target?.kind==='drone'&&!target.lost?m.reportingNodes(target):[],
                detectedIds=new Set(replayFrame?.detectedNodeIds||liveDetected.map(n=>n.id));
            const pulse=(Math.sin(Date.now()/180)+1)/2,activeNodes=[];
            for(const n of nodeModels){
                const active=replayFrame?Boolean(n.active):detectedIds.has(n.id),visual=nodeVisual(n.ordinal,n.online,active,pulse);
                if(active)activeNodes.push(n);
                put(`node-range:${n.id}`,g.Circle,{center:latLng(n),radius:n.detectionRadius,strokeColor:active?'#F97316':'#5EEAD4',strokeOpacity:active?.85:.42,strokeWeight:active?2.5:1.5,fillColor:active?'#F97316':'#5EEAD4',fillOpacity:active?.1:.045,clickable:false});
                put(`node:${n.id}`,g.Marker,{position:latLng(n),title:`${n.name} · 偵測 ${n.detectionRadius}m${n.online?'':' · 離線'}`,label:{text:`N${String(n.ordinal).padStart(2,'0')}${n.online?'':'×'}`,color:n.online?'#111827':'#F8FAFC',fontSize:'12px',fontWeight:'800'},icon:{path:visual.path,scale:visual.scale,fillColor:visual.fill,fillOpacity:visual.opacity,strokeColor:visual.stroke,strokeWeight:visual.strokeWidth},zIndex:active&&n.online?30:10,clickable:false});
            }
            if(activeNodes.length)for(const n of activeNodes)put(`pulse:${n.id}`,g.Circle,{center:latLng(n),radius:24+pulse*28,strokeColor:'#F97316',strokeWeight:3,strokeOpacity:.9-pulse*.75,fillColor:'#F97316',fillOpacity:.1-pulse*.07,clickable:false});
            const geometry=replayFrame?.sourceRegion?.path||(!replay?m.geometry(target):[]);
            if(geometry.length===2)put('source-line',g.Polyline,{path:geometry.map(latLng),strokeColor:'#F97316',strokeWeight:5,strokeOpacity:.95,clickable:false});
            else if(geometry.length>=3)put('source-polygon',g.Polygon,{paths:geometry.map(latLng),strokeColor:'#F97316',strokeWeight:3,strokeOpacity:.85,fillColor:'#F97316',fillOpacity:.12,clickable:false});
            const trueLine=(key,trail,muted=false)=>{if(trail.length>1)put(key,g.Polyline,{path:trail.map(latLng),strokeColor:'#C4B5FD',strokeOpacity:muted?.3:.9,strokeWeight:4,clickable:false});};
            const estimateLine=(key,trail)=>{if(trail.length>1)put(key,g.Polyline,{path:trail.map(latLng),strokeColor:'#60A5FA',strokeOpacity:0,strokeWeight:2,icons:[{icon:{path:'M 0,-1 0,1',strokeColor:'#60A5FA',strokeOpacity:1,strokeWeight:3,scale:3},offset:'0',repeat:'14px'}],clickable:false});};
            const trueMarker=(key,position,kind,label,lost=false)=>put(key,g.Marker,{position:latLng(position),title:label,icon:{path:kind==='drone'?DRONE_PATH:g.SymbolPath.CIRCLE,scale:kind==='drone'?1.1:8,strokeColor:lost?'#9EACC0':'#FBBF24',strokeWeight:2,fillColor:'#142033',fillOpacity:1},clickable:false});
            const estimateMarker=(key,position)=>put(key,g.Marker,{position:latLng(position),title:'節點推估位置',icon:{path:DRONE_PATH,scale:1.1,strokeColor:'#60A5FA',strokeWeight:2.4,fillColor:'#142033',fillOpacity:1},clickable:false});
            if(m.replay){
                const current=replayPoint(m.replay),estimated=current?replayPointAtTime(m.replay.estimatedPoints,current.time):null;
                if(current){const trail=m.replay.points.slice(0,current.index+1).concat(current);trueLine('replay-true',trail);trueMarker('replay-target',current,m.replay.kind,'模擬真實路徑回顧');}
                if(estimated){const trail=m.replay.estimatedPoints.slice(0,estimated.index+1).concat(estimated);estimateLine('replay-estimate',trail);estimateMarker('replay-estimate-marker',estimated);}
            } else for(const t of m.targets){
                if(point(t.position)){trueLine(`true:${t.id}`,t.trail,t.id!==m.selectedId);trueMarker(`target:${t.id}`,t.position,t.kind,t.id,t.lost);}
                estimateLine(`estimate:${t.id}`,t.estimatedTrail);if(point(t.estimatedPosition)&&t.id===m.selectedId)estimateMarker(`estimate-marker:${t.id}`,t.estimatedPosition);
                if(t.waypoints.length&&point(t.startPosition))put(`waypoints:${t.id}`,g.Polyline,{path:[t.startPosition,...t.waypoints].map(latLng),strokeColor:'#FBBF24',strokeWeight:2,strokeOpacity:.65,clickable:false});
            }
            for(const [key,overlay] of this.googleOverlays)if(!used.has(key)){overlay.setMap(null);this.googleOverlays.delete(key);}
        }
        fit(){this.fitted=true;if(!this.googleMap)return;const g=root.google.maps,b=new g.LatLngBounds(),extent=this.bounds();[{x:extent.cx-400/extent.scale,y:extent.cy-260/extent.scale},{x:extent.cx+400/extent.scale,y:extent.cy+260/extent.scale}].forEach(p=>b.extend(latLng(p)));this.googleMap.fitBounds(b,30);}
    }
    let workspace=null;
    const api={LabModel,assess,assessSystem,circleEntry,hull,latLng,offset,replayPoint,replayPointAtTime,replayTime,replayFrameAtTime,nodeVisual,LIMITS,
        mount(container){if(!container)throw new Error('A simulation workspace container is required');if(workspace)workspace.destroy();workspace=new Workspace(container);return workspace;},
        enter(){workspace?.enter();},leave(){workspace?.leave();},destroy(){workspace?.destroy();workspace=null;}};
    if(typeof module==='object'&&module.exports)module.exports=api;
    else root.DashboardSimulationLab=api;
})(typeof globalThis==='object'?globalThis:this);
