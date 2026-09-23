(function(root){
    'use strict';

    const DRONE_PATH='M -9 -6 L 9 6 M -9 6 L 9 -6 M -13 -6 A 4 4 0 1 0 -5 -6 A 4 4 0 1 0 -13 -6 M 5 -6 A 4 4 0 1 0 13 -6 A 4 4 0 1 0 5 -6 M -13 6 A 4 4 0 1 0 -5 6 A 4 4 0 1 0 -13 6 M 5 6 A 4 4 0 1 0 13 6 A 4 4 0 1 0 5 6';
    const NODE_PATH='M 0 -1 A 1 1 0 1 1 0 1 A 1 1 0 1 1 0 -1';
    const COLORS=Object.freeze({
        active:'#F97316',
        activeStroke:'#FFB86B',
        nodeOnline:'#F8FAFC',
        nodeOffline:'#475569',
        nodeStroke:'#111827',
        estimate:'#60A5FA',
        truth:'#FBBF24'
    });
    const MOTION_DURATION_MS=850;
    const PULSE_INTERVAL_MS=100;

    const clamp=(n,a,b)=>Math.max(a,Math.min(b,n));
    function pulseAt(timeMs){
        const value=Number(timeMs);
        return (Math.sin((Number.isFinite(value)?value:0)/180)+1)/2;
    }
    function nodeVisual(online=true,active=false,pulse=.5){
        const reporting=Boolean(active&&online),p=clamp(Number(pulse)||0,0,1);
        return {
            shape:'circle',
            path:NODE_PATH,
            fill:reporting?COLORS.active:online?COLORS.nodeOnline:COLORS.nodeOffline,
            stroke:reporting?COLORS.activeStroke:online?COLORS.nodeStroke:COLORS.nodeOnline,
            opacity:online?1:.95,
            strokeWidth:reporting?4:3,
            scale:reporting?14+p*6:14
        };
    }
    function pulseRingStyle(pulse=.5){
        const p=clamp(Number(pulse)||0,0,1);
        return {
            radius:24+p*28,
            strokeColor:COLORS.active,
            strokeWeight:3,
            strokeOpacity:.9-p*.75,
            fillColor:COLORS.active,
            fillOpacity:.1-p*.07,
            zIndex:28
        };
    }
    // One source of truth for the fixed-site marker and protected radius
    // across Simulation Lab and the live operational Google map.
    function siteMarkerStyle(maps){
        if(!maps?.SymbolPath?.CIRCLE)throw new Error('Google Maps SymbolPath.CIRCLE is required');
        return {
            label:{text:'據點',color:'#0B1220',fontWeight:'700'},
            icon:{path:maps.SymbolPath.CIRCLE,scale:16,fillColor:'#5EEAD4',fillOpacity:1,
                strokeColor:'#0B1220',strokeWeight:2},
            clickable:false,
            zIndex:35
        };
    }
    function siteZoneStyle(){
        return {
            strokeColor:'#FBBF24',strokeOpacity:.8,strokeWeight:2,
            fillColor:'#FBBF24',fillOpacity:.1,clickable:false
        };
    }
    function regionStyle(kind){
        if(kind==='line')return {
            strokeColor:COLORS.active,
            strokeWeight:5,
            strokeOpacity:.95,
            zIndex:18
        };
        if(kind==='polygon')return {
            strokeColor:COLORS.active,
            strokeWeight:3,
            strokeOpacity:.85,
            fillColor:COLORS.active,
            fillOpacity:.12,
            zIndex:18
        };
        return null;
    }
    function smoothStep(value){
        const t=clamp(Number(value)||0,0,1);
        return t*t*(3-2*t);
    }
    function headingDelta(from,to){
        const a=Number(from)||0,b=Number(to)||0;
        return ((b-a+540)%360)-180;
    }
    function sampleMotion(motion,nowMs){
        if(!motion)return null;
        const duration=Math.max(1,Number(motion.durationMs)||MOTION_DURATION_MS);
        const now=Number(nowMs);
        const raw=clamp(((Number.isFinite(now)?now:0)-(Number(motion.startedAt)||0))/duration,0,1);
        const t=smoothStep(raw),start=motion.start,target=motion.target;
        if(!start||!target)return null;
        return {
            position:{
                lat:start.lat+(target.lat-start.lat)*t,
                lng:start.lng+(target.lng-start.lng)*t
            },
            heading:((Number(motion.startHeading)||0)+headingDelta(motion.startHeading,motion.targetHeading)*t+360)%360,
            done:raw>=1,
            progress:raw
        };
    }

    const api=Object.freeze({
        DRONE_PATH,NODE_PATH,COLORS,MOTION_DURATION_MS,PULSE_INTERVAL_MS,
        pulseAt,nodeVisual,pulseRingStyle,regionStyle,siteMarkerStyle,siteZoneStyle,smoothStep,headingDelta,sampleMotion
    });
    if(typeof module==='object'&&module.exports)module.exports=api;
    else root.DashboardMapVisuals=api;
})(typeof globalThis==='object'?globalThis:this);
