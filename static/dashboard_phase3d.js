/* Opt-in on the existing dashboard socket. No per-message diagnostic DOM. */
(function(root){
    'use strict';
    const active = new URLSearchParams(root.location?.search || '').get('phase3d') === '1';
    const rows=[], seen=new Set(), latest=new Map();
    const browserSessionId='p3d_browser_'+(root.crypto?.randomUUID?.() || String(Date.now()));
    let current=null, ready=false, generation=0, socketRef=null;
    function begin(data,d0,d1){
        current=null;
        if(!active || !ready || !data?.phase3d || data.type!=='node_heartbeat')return;
        const t=data.phase3d,node=data.node, ds=node?.detection_state;
        if(!t.traceId || !ds || ds.sequence!==t.sequence)return;
        const prior=latest.get(t.nodeId);
        current={traceId:t.traceId,nodeId:t.nodeId,sequence:t.sequence,D0:d0,D1:d1,
            active:ds.active,label:ds.label,confidence:ds.confidence,observedAtMs:ds.observed_at_ms,
            browserSessionId,browserGeneration:generation,visible:root.document.visibilityState==='visible',
            duplicate:seen.has(t.traceId),outOfOrder:Number.isFinite(prior)&&ds.sequence<=prior,
            alertIndicator:'NOT_AVAILABLE',mapApplicable:false};
        seen.add(t.traceId);if(seen.size>512)seen.delete(seen.values().next().value);
        latest.set(t.nodeId,Math.max(prior||0,ds.sequence));
    }
    function stored(node){
        if(current&&node?.device_id===current.nodeId){
            current.D2=root.performance.now();
            const ds=node.detection_state;
            current.storeCorrect=ds?.sequence===current.sequence&&ds?.active===current.active;
        }
    }
    function marker(node,marker){
        if(current&&node?.device_id===current.nodeId&&marker){
            current.D3=root.performance.now();current.mapApplicable=true;
            current.alertIndicator='existing node marker icon alert state';
            current.markerAlertKey=marker.__dashboardAlertKey;
        }
    }
    function finish(){
        const row=current;current=null;
        if(!row)return;
        row.D4=root.performance.now();
        // A missing visible indicator remains a failure, never invented timing.
        if(!Number.isFinite(row.D3))row.D3=row.D4;
        if(!Number.isFinite(row.D2))row.D2=row.D1;
        root.requestAnimationFrame(()=>{
            row.D5=root.performance.now();
            rows.push(row);if(rows.length>512)rows.shift();
            if(socketRef?.readyState===1)socketRef.send(JSON.stringify({type:'phase3d_receipt',traceId:row.traceId,receipt:row}));
        });
    }
    function connected(ws){
        socketRef=ws;ready=false;generation++;
        if(active)ws.send(JSON.stringify({type:'phase3d_subscribe',browserSessionId}));
    }
    function control(data){
        if(data?.type==='phase3d_ready'&&data.browserSessionId===browserSessionId){ready=true;return true;}
        return false;
    }
    root.Phase3dDashboard={begin,stored,marker,finish,connected,control,rows,
        status:()=>({active,ready,generation,browserSessionId,visible:root.document.visibilityState==='visible'})};
})(globalThis);
