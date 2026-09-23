(function(root){
    'use strict';

    const TYPES=new Set(['event_trigger','event_group','track_update']);
    const STAGE_NAMES={
        ingest_total:'API 收件（完整）',
        event_db:'事件 DB 寫入',
        fixed_location:'固定位置查詢',
        postgres_pool_wait:'PostgreSQL 連線池等待',
        postgres_connection_check:'DB 連線驗證',
        fusion_db_lock_wait:'Fusion DB 鎖等待',
        queue_wait:'背景工作排隊',
        fusion:'事件 Fusion',
        region_tracking:'感測區域 Tracking',
        active_alert_tracking:'即時警示 Tracking',
        localization_group_load:'定位群組讀取',
        localization_compute:'定位運算（含 Solver）',
        tdoa_solver:'TDOA Solver（僅求解）',
        localization_save:'定位結果 DB 儲存',
        localization_tracking:'正式定位 Tracking',
        localization_total:'定位完整流程',
        post_ingest_total:'背景工作總耗時',
        ws_event_group:'WS 推播感測群組',
        ws_track_update:'WS 推播 Track',
        ws_localization_result:'WS 推播定位結果',
        broadcast_total:'後處理 WS 推播總耗時',
        queued_to_broadcast:'排隊至全部 WS 推播完成'
    };
    const STAGE_ORDER=Object.keys(STAGE_NAMES);
    const WINDOW_MS=15*60*1000;
    const MAX_SAMPLES=512;
    function percentile(sorted,q){
        if(!sorted.length)return null;
        const idx=(sorted.length-1)*q,lo=Math.floor(idx),hi=Math.ceil(idx);
        return sorted[lo]+(sorted[hi]-sorted[lo])*(idx-lo);
    }
    function createStore(capacity=MAX_SAMPLES){
        const data=new Map();
        return {
            record(type,elapsed,now){
                if(!Number.isFinite(elapsed)||elapsed<0||!TYPES.has(type))return;
                const key='ws_paint_'+type;
                const items=data.get(key)||[];
                items.push({ms:elapsed,at:now});
                if(items.length>capacity)items.splice(0,items.length-capacity);
                data.set(key,items);
            },
            snapshot(now){
                const output={};
                for(const [key,items] of data){
                    const filtered=items.filter(item=>now-item.at<=WINDOW_MS&&now-item.at>=0);
                    data.set(key,filtered);
                    if(!filtered.length)continue;
                    const values=filtered.map(item=>item.ms).sort((a,b)=>a-b);
                    output[key]={
                        count:values.length,
                        p50_ms:percentile(values,.5),
                        p95_ms:percentile(values,.95),
                        p99_ms:percentile(values,.99),
                        max_ms:values[values.length-1]
                    };
                }
                return output;
            }
        };
    }
    const store=createStore();
    const now=()=>root.performance?.now?.()??Date.now();
    const format=number=>Number.isFinite(number)?Math.round(number)+' ms':'—';
    function recordMessageHandled(type,receivedAt){
        if(!TYPES.has(type)||root.document?.hidden||!root.requestAnimationFrame)return;
        // Two animation frames approximate reception-to-paint, not network transport.
        root.requestAnimationFrame(()=>root.requestAnimationFrame(()=>{
            if(!root.document.hidden)store.record(type,now()-receivedAt,now());
        }));
    }
    function row(label,values){
        const tr=document.createElement('tr'),sample=Number(values?.count)||0;
        const cols=[label,sample||'—',format(values?.p50_ms),format(values?.p95_ms),format(values?.p99_ms)];
        for(const col of cols){const td=document.createElement('td');td.textContent=String(col);tr.appendChild(td);}
        if(sample>0&&sample<20)tr.title='樣本少於 20 筆，P95 / P99 暫不穩定';
        return tr;
    }
    function mount(){
        const host=document.querySelector('.overview-summary');
        if(!host||document.getElementById('latencyDiagnostics'))return;
        const card=document.createElement('article');
        card.id='latencyDiagnostics';
        card.className='card';
        card.style.cssText='margin-top:12px;min-width:0';
        card.innerHTML='<div class="card-header"><div><h2>Latency Diagnostics <small style="opacity:.75">STAGING</small></h2><small>最近 15 分鐘 · 同一台 Server Process · 毫秒</small></div><button type="button" class="action-button" id="latencyRefresh">更新</button></div>'+
            '<div class="card-body"><p id="latencyStatus" role="status">等待實機事件…</p>'+
            '<p id="latencyQueue" style="font-variant-numeric:tabular-nums"></p>'+
            '<div class="table-wrap" style="max-height:400px;overflow:auto"><table style="min-width:520px"><thead><tr><th>階段</th><th>筆數</th><th>P50</th><th>P95</th><th>P99</th></tr></thead><tbody id="latencyRows"></tbody></table></div>'+
            '<p style="font-size:11px;opacity:.8">瀏覽器延遲為 WS 收到訊息到後續繪製影格的近似值；不含手機上傳及網路傳輸。分位數為各階段獨立分布，不能直接相加。少於 20 筆僅供參考。</p></div>';
        host.appendChild(card);
        const status=document.getElementById('latencyStatus');
        const queue=document.getElementById('latencyQueue');
        const body=document.getElementById('latencyRows');
        let polling=false;
        async function refresh(){
            if(polling||document.hidden)return;
            polling=true;
            try{
                const response=await fetch('/diagnostics/latency',{cache:'no-store'});
                if(!response.ok)throw new Error('HTTP '+response.status);
                const payload=await response.json(),server=payload.stages||{},client=store.snapshot(now());
                body.replaceChildren();
                for(const stage of STAGE_ORDER)if(server[stage])body.appendChild(row(STAGE_NAMES[stage],server[stage]));
                const clientNames={ws_paint_event_trigger:'瀏覽器事件 WS → Paint',ws_paint_event_group:'瀏覽器群組 WS → Paint',ws_paint_track_update:'瀏覽器 Track WS → Paint'};
                for(const [key,name] of Object.entries(clientNames))if(client[key])body.appendChild(row(name,client[key]));
                if(!body.children.length){const tr=document.createElement('tr');const td=document.createElement('td');td.colSpan=5;td.textContent='尚無資料。請用實機觸發事件後再查看。';tr.appendChild(td);body.appendChild(tr);}
                queue.textContent='Queue：等待 '+(payload.queue?.pending??'—')+' ／ 處理中 '+(payload.queue?.running??'—')+'；已記錄的失敗 '+Object.values(payload.errors||{}).reduce((a,b)=>a+Number(b||0),0);
                status.textContent='最後更新：'+new Date(payload.generated_at).toLocaleTimeString('zh-TW')+' · Server 採樣 '+(payload.window_seconds/60)+' 分鐘';
            }catch(error){status.textContent='暫時無法取得伺服器延遲統計：'+String(error.message||error);}
            finally{polling=false;}
        }
        document.getElementById('latencyRefresh').addEventListener('click',refresh);
        refresh();
        root.setInterval(refresh,5000);
    }
    const api=Object.freeze({percentile,createStore,recordMessageHandled,mount,STAGE_NAMES});
    if(typeof module==='object'&&module.exports)module.exports=api;
    else {
        root.DashboardLatencyDiagnostics=api;
        if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',mount,{once:true});
        else mount();
    }
})(typeof globalThis==='object'?globalThis:this);
