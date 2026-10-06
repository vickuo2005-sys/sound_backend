(function(root){
    'use strict';

    const FALLBACK_FRESH_MS=15000;
    const MAX_SAMPLES=256;

    function nearestRank(values,percentile){
        const sorted=(Array.isArray(values)?values:[]).filter(Number.isFinite).slice().sort((a,b)=>a-b);
        if(!sorted.length)return null;
        const p=Math.max(0,Math.min(1,Number(percentile)||0));
        const index=Math.min(sorted.length-1,Math.max(0,Math.ceil(sorted.length*p)-1));
        return sorted[index];
    }
    function pushBounded(list,value,max=MAX_SAMPLES){
        list.push(value);
        if(list.length>max)list.splice(0,list.length-max);
        return list;
    }
    function timeMs(value){
        if(value===null||value===undefined||value==='')return null;
        if(typeof value==='number')return Number.isFinite(value)?value:null;
        const parsed=Date.parse(String(value));
        return Number.isFinite(parsed)?parsed:null;
    }
    function backendAlertFresh(value,fallbackTime,now=Date.now(),duration=FALLBACK_FRESH_MS){
        const helper=root.DashboardNodeGeometry?.alertFresh;
        if(typeof helper==='function')return helper(value,fallbackTime,now,duration);
        return Number.isFinite(fallbackTime)&&Number.isFinite(now)&&now-fallbackTime>=-2000&&now-fallbackTime<=duration;
    }
    function terminalGroup(group){
        return ['closed','expired','ended','inactive'].includes(String(group?.status||'').toLowerCase());
    }
    function liveNodeEligible(node){
        if(!node)return false;
        const status=String(node?.status||'').trim().toLowerCase();
        const availability=String(node?.availability_status||'').trim().toLowerCase();
        const appStatus=String(node?.app_status||'').trim().toLowerCase();
        if(node?.websocket_connected===false)return false;
        if(node?.is_listening===false)return false;
        if(['offline','disconnected'].includes(status))return false;
        if(availability==='offline')return false;
        if(['stopped','disabled','off'].includes(appStatus))return false;
        // `recording` and `detection_enabled` are phase-level telemetry, not an
        // authoritative operator stop signal. They can legitimately be false while
        // the app is processing inference or uploading an accepted event. Only the
        // explicit stop/disconnect signals above may remove a node from live warning.
        return true;
    }
    function rawGroupDeviceIds(group){
        const candidates=[group?.active_device_ids,group?.reporting_device_ids,group?.device_ids,group?.devices,group?.member_device_ids];
        for(let candidate of candidates){
            if(typeof candidate==='string'&&candidate.trim()){
                try{candidate=JSON.parse(candidate);}catch(_){candidate=candidate.split(',');}
            }
            if(Array.isArray(candidate)){
                return [...new Set(candidate.map(value=>typeof value==='object'?value?.device_id:value).filter(Boolean).map(value=>String(value).trim()).filter(Boolean))];
            }
        }
        return [];
    }
    function liveGroupDeviceIdsFrom(group,devices=[]){
        const byId=new Map((Array.isArray(devices)?devices:[]).filter(device=>device?.device_id).map(device=>[String(device.device_id),device]));
        if(!byId.size)return rawGroupDeviceIds(group);
        return rawGroupDeviceIds(group).filter(id=>{
            const device=byId.get(String(id));
            return Boolean(device&&liveNodeEligible(device));
        });
    }
    function sanitizeGroupForLive(group,devices=[]){
        if(!group||typeof group!=='object')return group;
        return {...group,active_device_ids:liveGroupDeviceIdsFrom(group,devices)};
    }
    function sanitizeEventsForLive(events,devices=[]){
        if(!Array.isArray(events))return events;
        const byId=new Map((Array.isArray(devices)?devices:[]).filter(device=>device?.device_id).map(device=>[String(device.device_id),device]));
        if(!byId.size)return events;
        return events.filter(event=>{
            const id=String(event?.device_id||'');
            if(!id)return true;
            const device=byId.get(id);
            return Boolean(device&&liveNodeEligible(device));
        });
    }
    function percentileText(samples,key){
        const values=(samples||[]).map(sample=>sample?.[key]).filter(Number.isFinite);
        const p50=nearestRank(values,.50),p95=nearestRank(values,.95),p99=nearestRank(values,.99);
        return p95===null?'尚無樣本':`P50 ${p50.toFixed(1)} · P95 ${p95.toFixed(1)} · P99 ${p99.toFixed(1)} ms · n=${values.length}`;
    }
    function metricRow(id,label,text){
        if(typeof document==='undefined')return;
        const target=document.getElementById('latencyDiagnosticsList');
        if(!target)return;
        let row=document.getElementById(id);
        if(!row){
            row=document.createElement('div');
            row.id=id;
            row.className='health-row';
            const name=document.createElement('span');
            const value=document.createElement('span');
            value.className='health-state';
            row.append(name,value);
            target.append(row);
        }
        row.firstElementChild.textContent=label;
        row.lastElementChild.textContent=text;
    }
    function afterTwoFrames(callback){
        const raf=typeof root.requestAnimationFrame==='function'
            ? root.requestAnimationFrame.bind(root)
            : fn=>setTimeout(()=>fn((root.performance?.now?.()||Date.now())),16);
        raf(()=>raf(timestamp=>callback(Number.isFinite(timestamp)?timestamp:(root.performance?.now?.()||Date.now()))));
    }
    function groupHasLocation(group){
        const lat=Number(group?.region_center_lat??group?.estimated_lat);
        const lng=Number(group?.region_center_lng??group?.estimated_lng);
        return Number.isFinite(lat)&&Number.isFinite(lng);
    }
    function trackHasLocation(track){
        const directLat=Number(track?.last_lat??track?.filtered_lat??track?.estimated_lat??track?.latitude);
        const directLng=Number(track?.last_lng??track?.filtered_lng??track?.estimated_lng??track?.longitude);
        if(Number.isFinite(directLat)&&Number.isFinite(directLng))return true;
        const points=Array.isArray(track?.points)?track.points:Array.isArray(track?.recent_points)?track.recent_points:[];
        return points.some(point=>{
            if(!point||point.rejected_as_outlier||point.is_outlier||point.is_rejected||point.accepted===false)return false;
            const lat=Number(point.measured_lat??point.filtered_lat??point.estimated_lat??point.latitude);
            const lng=Number(point.measured_lng??point.filtered_lng??point.estimated_lng??point.longitude);
            return Number.isFinite(lat)&&Number.isFinite(lng);
        });
    }
    function associatedGroupId(track){
        const direct=track?.group_id??track?.last_group_id??track?.event_group_id;
        if(direct!==null&&direct!==undefined&&String(direct))return String(direct);
        const points=Array.isArray(track?.points)?track.points:Array.isArray(track?.recent_points)?track.recent_points:[];
        let winner=null,winnerTime=-Infinity;
        for(let index=0;index<points.length;index++){
            const point=points[index];
            if(!point||point.rejected_as_outlier||point.is_outlier||point.is_rejected||point.accepted===false||point.group_id===null||point.group_id===undefined)continue;
            const measured=timeMs(point.measurement_time_ms)??timeMs(point.measurement_timestamp??point.event_time??point.timestamp??point.created_at)??index;
            if(measured>=winnerTime){winnerTime=measured;winner=String(point.group_id);}
        }
        return winner;
    }
    function groupObservationTime(group){
        return timeMs(group?.last_event_time??group?.end_time??group?.first_event_time??group?.start_time);
    }
    function trackObservationTime(track){
        const direct=timeMs(track?.last_event_time_ms)??timeMs(track?.last_event_time);
        const points=Array.isArray(track?.points)?track.points:Array.isArray(track?.recent_points)?track.recent_points:[];
        let latest=direct;
        for(const point of points){
            if(!point||point.rejected_as_outlier||point.is_outlier||point.is_rejected||point.accepted===false)continue;
            const measured=timeMs(point.measurement_time_ms)??timeMs(point.measurement_timestamp??point.event_time??point.timestamp??point.created_at);
            if(measured!==null&&(latest===null||measured>latest))latest=measured;
        }
        return latest;
    }
    function groupIsNewerThanAssociatedTrack(track,group){
        if(!track||!group)return false;
        const id=associatedGroupId(track);
        if(!id||id!==String(group?.id??group?.group_id??''))return false;
        const groupTime=groupObservationTime(group),trackTime=trackObservationTime(track);
        return groupTime!==null&&trackTime!==null&&groupTime>trackTime;
    }

    function install(){
        if(typeof root.document==='undefined')return false;
        if(root.__dashboardLiveMapPatchInstalled)return true;
        if(typeof DashboardNodeGeometry!=='object')return false;
        root.__dashboardLiveMapPatchInstalled=true;

        const currentDevices=()=>{
            try{return typeof canonicalDevices==='function'?canonicalDevices():[];}
            catch(_){return [];}
        };
        const liveGroupIds=group=>liveGroupDeviceIdsFrom(group,currentDevices());

        // Keep shared/simulation motion timing untouched while shortening only the
        // live operator marker interpolation. This avoids breaking Simulation Lab
        // visual parity while removing the extra ~850 ms apparent live-map lag.
        if(typeof setLiveMarkerTarget==='function'&&root.DashboardMapVisuals){
            setLiveMarkerTarget=function(key,marker,target,heading=0){
                if(!marker||!target)return;
                const now=performance.now(),existing=liveMarkerMotion.get(key),normalizedHeading=((Number(heading)||0)%360+360)%360;
                if(!existing){
                    marker.setPosition(target);marker.setIcon(v22DroneTargetIcon(normalizedHeading));
                    liveMarkerMotion.set(key,{marker,start:{...target},target:{...target},current:{...target},startHeading:normalizedHeading,targetHeading:normalizedHeading,currentHeading:normalizedHeading,startedAt:now,durationMs:1,lastIconAt:now});
                    return;
                }
                const sample=liveMotionSample(existing,now)||{position:existing.current||existing.target,heading:existing.currentHeading||existing.targetHeading||0};
                const dLat=target.lat-existing.target.lat,dLng=target.lng-existing.target.lng,headingChange=Math.abs(liveHeadingDelta(existing.targetHeading,normalizedHeading));
                if(Math.hypot(dLat,dLng)<1e-9&&headingChange<.5)return;
                existing.marker=marker;
                existing.start={...sample.position};
                existing.target={...target};
                existing.current={...sample.position};
                existing.startHeading=sample.heading;
                existing.targetHeading=normalizedHeading;
                existing.currentHeading=sample.heading;
                existing.startedAt=now;
                existing.durationMs=Math.max(1,Number(root.DashboardMapVisuals.LIVE_MOTION_DURATION_MS)||200);
                ensureLiveMarkerAnimation();
            };
        }

        // A backend group is historical evidence; a live warning must also respect
        // the node's current runtime state. When a node stops listening or disconnects,
        // it must leave the live line/polygon immediately instead of waiting for the
        // group's alert hold timer to expire.
        if(typeof renderMap==='function'){
            const baseRenderMap=renderMap;
            renderMap=function(){
                const devices=currentDevices();
                const originalGroups=state.groups,originalEvents=state.events;
                if(originalGroups instanceof Map){
                    state.groups=new Map([...originalGroups.entries()].map(([id,group])=>[id,sanitizeGroupForLive(group,devices)]));
                }
                state.events=sanitizeEventsForLive(originalEvents,devices);
                try{return baseRenderMap.apply(this,arguments);}
                finally{
                    state.groups=originalGroups;
                    state.events=originalEvents;
                }
            };
        }

        // The inline dashboard historically re-evaluated freshness from sound occurrence
        // time. Keep the backend's accepted/display-expiry contract authoritative when
        // those fields are present, while preserving the legacy 15 s fallback.
        if(typeof liveDroneSensorEvidence==='function'){
            liveDroneSensorEvidence=function(now=Date.now()){
                const byDevice=new Map(),devices=new Map(currentDevices().map(device=>[String(device.device_id),device]));
                for(const event of state.events){
                    if(!['drone','aircraft'].includes(String(classLabel(event)||'').toLowerCase()))continue;
                    const time=eventTime(event),id=String(event?.device_id||'');
                    if(!id||!backendAlertFresh(event,time,now,FALLBACK_FRESH_MS))continue;
                    const device=devices.get(id),position=device?nodeLocation(device):null;
                    if(!device||!liveNodeEligible(device)||!deviceOnline(device)||!position)continue;
                    const previous=byDevice.get(id);
                    if(!previous||time>previous.time)byDevice.set(id,{device,event,time,position});
                }
                return [...byDevice.values()];
            };
        }
        if(typeof freshBackendMultiNodeEvidence==='function'){
            freshBackendMultiNodeEvidence=function(now=Date.now()){
                return [...state.groups.values()].some(group=>
                    isLiveTargetGroup(group)&&liveGroupIds(group).length>=2&&!terminalGroup(group)&&
                    backendAlertFresh(group,groupTime(group),now,FALLBACK_FRESH_MS)
                );
            };
        }
        if(typeof freshBackendLocatedGroup==='function'){
            freshBackendLocatedGroup=function(now=Date.now()){
                return [...state.groups.values()].some(group=>
                    isLiveTargetGroup(group)&&groupLocation(group)&&liveGroupIds(group).length>=2&&!terminalGroup(group)&&
                    backendAlertFresh(group,groupTime(group),now,FALLBACK_FRESH_MS)
                );
            };
        }
        if(typeof selectedOrLatestGroup==='function'){
            selectedOrLatestGroup=function(){
                const selected=state.selectedGroupId?state.groups.get(state.selectedGroupId):null;
                if(selected&&isLiveTargetGroup(selected)&&groupLocation(selected)&&liveGroupIds(selected).length>0)return selected;
                const now=Date.now();
                return [...state.groups.values()].filter(group=>
                    isLiveTargetGroup(group)&&groupLocation(group)&&liveGroupIds(group).length>0&&!terminalGroup(group)&&
                    backendAlertFresh(group,groupTime(group),now,FALLBACK_FRESH_MS)
                ).sort((a,b)=>groupTime(b)-groupTime(a))[0]||null;
            };
        }

        // A live track should not hide a newer position from the exact same fusion
        // group. Compare observation timestamps (not backend updated_at) so the two
        // clocks have the same semantic meaning. Once every source node for an
        // associated group has stopped, the live track also stops being eligible.
        if(typeof isFreshLiveTrack==='function'){
            const baseTrackFresh=isFreshLiveTrack;
            isFreshLiveTrack=function(track,now=Date.now()){
                if(!baseTrackFresh(track,now))return false;
                const groupId=associatedGroupId(track);
                if(!groupId)return true;
                const group=state.groups.get(String(groupId));
                if(group&&liveGroupIds(group).length===0)return false;
                if(!group||terminalGroup(group)||!groupLocation(group)||!backendAlertFresh(group,groupTime(group),now,FALLBACK_FRESH_MS))return true;
                return !groupIsNewerThanAssociatedTrack(track,group);
            };
        }

        // Keep the existing synchronous metric, then add browser-side visual milestones
        // for both event-group and track updates. These are deliberately named
        // "eligible" because browsers/Google Maps do not expose an exact operator-visible
        // paint timestamp for overlays.
        if(typeof handleWebSocketMessage==='function'){
            const baseHandle=handleWebSocketMessage;
            handleWebSocketMessage=function(data){
                const messageType=String(data?.type||'');
                const entity=messageType==='event_group'?(data.group||data):messageType==='track_update'?(data.track||data):null;
                const hasPosition=messageType==='event_group'?groupHasLocation(entity):messageType==='track_update'?trackHasLocation(entity):false;
                const measure=Boolean(entity&&hasPosition&&state.runtime?.critical_path_diagnostics_enabled===true);
                const receivedAt=measure?(root.performance?.now?.()||0):null;
                const result=baseHandle(data);
                if(!measure||!Number.isFinite(receivedAt))return result;
                const eventId=String(data?.critical_path?.event_id||'');
                const entityId=String(messageType==='event_group'?(entity?.id??entity?.group_id??''):(entity?.id??entity?.track_id??''));
                const allSamples=state.browserMapVisualSamples||(state.browserMapVisualSamples=[]);
                const typedSamples=messageType==='event_group'
                    ? (state.browserGroupVisualSamples||(state.browserGroupVisualSamples=[]))
                    : (state.browserTrackVisualSamples||(state.browserTrackVisualSamples=[]));
                const sample={message_type:messageType,entity_id:entityId,event_id:eventId,dashboard_ws_visual_received:receivedAt};
                pushBounded(allSamples,sample);
                pushBounded(typedSamples,sample);
                afterTwoFrames(frameAt=>{
                    sample.dashboard_next_paint_eligible=frameAt;
                    sample.next_paint_eligible_ms=Math.max(0,frameAt-receivedAt);
                });
                const settleDelay=Math.max(0,Number(root.DashboardMapVisuals?.LIVE_MOTION_DURATION_MS)||Number(root.DashboardMapVisuals?.MOTION_DURATION_MS)||0);
                setTimeout(()=>afterTwoFrames(frameAt=>{
                    sample.dashboard_marker_settle_eligible=frameAt;
                    sample.marker_settle_eligible_ms=Math.max(0,frameAt-receivedAt);
                }),settleDelay);
                return result;
            };
        }
        if(typeof renderLatencyDiagnostics==='function'){
            const baseRenderLatency=renderLatencyDiagnostics;
            renderLatencyDiagnostics=function(){
                const result=baseRenderLatency.apply(this,arguments);
                if(state.runtime?.critical_path_diagnostics_enabled===true){
                    const groupSamples=state.browserGroupVisualSamples||[];
                    const trackSamples=state.browserTrackVisualSamples||[];
                    metricRow('browserGroupNextPaintEligibleLatency','Browser group map next-paint eligible',percentileText(groupSamples,'next_paint_eligible_ms'));
                    metricRow('browserGroupMarkerSettleEligibleLatency','Browser group marker settle eligible',percentileText(groupSamples,'marker_settle_eligible_ms'));
                    metricRow('browserTrackNextPaintEligibleLatency','Browser track map next-paint eligible',percentileText(trackSamples,'next_paint_eligible_ms'));
                    metricRow('browserTrackMarkerSettleEligibleLatency','Browser track marker settle eligible',percentileText(trackSamples,'marker_settle_eligible_ms'));
                }
                return result;
            };
        }
        return true;
    }

    const api=Object.freeze({
        FALLBACK_FRESH_MS,MAX_SAMPLES,nearestRank,pushBounded,timeMs,backendAlertFresh,percentileText,afterTwoFrames,
        liveNodeEligible,rawGroupDeviceIds,liveGroupDeviceIdsFrom,sanitizeGroupForLive,sanitizeEventsForLive,
        groupHasLocation,trackHasLocation,associatedGroupId,groupObservationTime,trackObservationTime,groupIsNewerThanAssociatedTrack,install
    });
    if(typeof module==='object'&&module.exports)module.exports=api;
    else{
        root.DashboardLiveMapPatch=api;
        install();
    }
})(typeof globalThis==='object'?globalThis:this);
