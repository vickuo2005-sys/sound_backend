(function(root) {
    'use strict';
    const number = x => typeof x === 'number' && Number.isFinite(x) ? x : null;
    const time = x => number(x) ?? (typeof x === 'string' && Number.isFinite(Date.parse(x)) ? Date.parse(x) : null);
    const coordinate = (lat,lng) => number(lat) !== null && number(lng) !== null && Math.abs(lat)<=90 && Math.abs(lng)<=180 ? {lat,lng} : null;
    function points(track) {
        return (track?.points || track?.recent_points || []).map((p,index) => ({...p,index,
            ...coordinate(p.measured_lat ?? p.filtered_lat ?? p.estimated_lat ?? p.latitude, p.measured_lng ?? p.filtered_lng ?? p.estimated_lng ?? p.longitude),
            time:time(p.measurement_time_ms ?? p.measurement_timestamp ?? p.event_time ?? p.timestamp)
        })).filter(p => coordinate(p.lat,p.lng) && !p.is_outlier && !p.is_rejected && !p.rejected_as_outlier && p.accepted !== false)
            .sort((a,b) => (a.time ?? Infinity)-(b.time ?? Infinity) || a.index-b.index);
    }
    function site(value) {
        return value && coordinate(value.lat,value.lng) && typeof value.name === 'string' && value.name.trim() &&
            number(value.radius) !== null && value.radius>0 && value.radius<=10000 && number(value.arrivalRadius)!==null &&
            value.arrivalRadius>0 && value.arrivalRadius<=value.radius ? value : null;
    }
    function entry(x,y,vx,vy,radius) {
        const c=x*x+y*y-radius*radius;
        if(c<=0) return 0;
        const a=vx*vx+vy*vy,b=2*(x*vx+y*vy),d=b*b-4*a*c;
        if(a<.25 || d<0) return null;
        const t=(-b-Math.sqrt(d))/(2*a);
        return t>=0 && t<=300 ? t : null;
    }
    function assess(track,config,now=Date.now(),enabled=false,motionEnabled=false) {
        const p=points(track).at(-1);
        const result={id:String(track?.id ?? track?.track_id ?? ''),status:'unlocated',position:null,zoneEta:null,arrivalEta:null,distance:null,time:p?.time};
        if(!enabled || ['closed','expired'].includes(String(track?.status).toLowerCase()) || !p || p.time===null || now-p.time>15000 || now-p.time< -2000) return result;
        let diagnostics=p.diagnostics_json || {};
        if(typeof diagnostics==='string') { try { diagnostics=JSON.parse(diagnostics); } catch { diagnostics={}; } }
        // Region centers and node coordinates do not establish a target position.
        if(diagnostics.source!=='localization_result' || !['tdoa','gcc_phat','timestamp_tdoa','hybrid_tdoa','gcc_phat_tdoa'].includes(diagnostics.localization_method) ||
            !(diagnostics.reporting_node_count>=2) || number(p.uncertainty_radius_m)===null || p.uncertainty_radius_m<0) return result;
        result.position={lat:p.lat,lng:p.lng};result.status='located';
        if(!site(config)) return result;
        const rad=Math.PI/180, earth=6371008.8;
        let delta=(p.lng-config.lng+540)%360-180;
        const x=delta*rad*earth*Math.cos(config.lat*rad),y=(p.lat-config.lat)*rad*earth;
        const distance=Math.hypot(x,y),u=p.uncertainty_radius_m;
        result.distance=distance;
        result.status=distance+u<=config.radius ? 'inside' : distance-u>config.radius ? 'outside' : 'boundary';
        result.uncertainty=u;
        const motion=track.approach_motion;
        const vx=number(motion?.vx_mps),vy=number(motion?.vy_mps);
        if(!motionEnabled || motion?.valid!==true || motion.quality!=='high' || motion.measurement_time_ms!==p.time || vx===null || vy===null || Math.hypot(vx,vy)>200 || distance>10000) return result;
        const closing=distance>0 ? -(x*vx+y*vy)/distance : 0;
        result.closing=closing;result.trend=closing>.1 ? 'approaching' : closing<-.1 ? 'departing' : 'stationary';
        if(result.status==='inside') result.zoneEta=0;
        if(distance+u<=config.arrivalRadius) result.arrivalEta=0;
        if(closing>.1 && result.status!=='boundary') {
            result.zoneEta=entry(x,y,vx,vy,config.radius);
            result.arrivalEta=entry(x,y,vx,vy,config.arrivalRadius);
        }
        return result;
    }
    class Entries {
        constructor(){this.states=new Map();}
        update(id,status,timestamp) {
            const old=this.states.get(id);
            if(!Number.isFinite(timestamp) || (old && timestamp<=old.time)) return false;
            if(!['inside','outside'].includes(status)) return false;
            this.states.set(id,{status,time:timestamp});
            return status==='inside' && old?.status!=='inside';
        }
    }
    function frame(path,fraction) {
        if(!path.length) return {index:0,path:[],point:null};
        const f=Math.max(0,Math.min(1,fraction)),first=path[0].time,last=path.at(-1).time;
        const timed=path.every(p=>p.time!==null) && last>first;
        const t=timed ? first+(last-first)*f : null;
        let i=timed ? path.findLastIndex(p=>p.time<=t) : Math.floor(f*(path.length-1));
        i=Math.max(0,i);
        return {index:i,path:path.slice(0,i+1),point:path[i],time:t,timed};
    }
    const api={points,site,coordinate,assess,entry,Entries,frame,time};
    if(typeof module==='object' && module.exports) module.exports=api;else root.DashboardOperations=api;
})(typeof globalThis==='object'?globalThis:this);
