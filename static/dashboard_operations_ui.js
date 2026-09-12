(function() {
    'use strict';
    const O=DashboardOperations;
    const el=id=>document.getElementById(id);
    let config=null, seen=new Set(), entries=new O.Entries(), alerts=[], focused=null, noticeUntil=0;
    let targetMarker=null, siteMarker=null, zoneCircle=null;
    let historyMap=null, historyLine=null, historyMarker=null, replay=null, request=0, animation=null, currentTarget=null;
    try { config=O.site(JSON.parse(localStorage.getItem('sound-dashboard-site-v1'))); } catch(_) {}
    const panel=document.createElement('article');panel.id='operationalTarget';panel.className='card';panel.hidden=true;
    document.querySelector('.overview-summary').prepend(panel);
    const banner=document.createElement('button');banner.id='targetNotice';banner.className='target-notice';banner.hidden=true;
    banner.setAttribute('aria-live','polite');banner.onclick=()=>{banner.hidden=true;noticeUntil=0;switchView('dashboard');};document.body.append(banner);
    const dialog=document.createElement('dialog');dialog.id='zoneAlert';dialog.setAttribute('aria-labelledby','zoneAlertTitle');
    dialog.innerHTML='<h2 id="zoneAlertTitle">無人機進入警戒區</h2><div id="zoneAlertBody"></div><p>此警告依目標定位估測產生。</p><button id="ackZoneAlert" class="action-button primary">確認警告</button>';
    document.body.append(dialog);
    function showAlert() {
        if(!alerts.length){if(dialog.open)dialog.close();return;}
        const a=alerts[0];el('zoneAlertBody').textContent=`據點：${a.site}；目標：${a.id}；首次觀測於區內：${new Date(a.time).toLocaleString('zh-TW')}。待確認 ${alerts.length} 則。`;
        if(!dialog.open)dialog.showModal();
    }
    function acknowledge(){alerts.shift();showAlert();}
    el('ackZoneAlert').onclick=acknowledge;dialog.addEventListener('cancel',event=>{event.preventDefault();acknowledge();});
    const siteCard=document.createElement('details');siteCard.className='card';
    siteCard.innerHTML='<summary>據點與警戒區設定</summary><form id="siteForm" class="card-body"><p>儲存於此瀏覽器，作為本畫面的警戒參考。</p><label>據點名稱<input name="name" required maxlength="60"></label><label>緯度<input name="lat" type="number" min="-85" max="85" step="any" required></label><label>經度<input name="lng" type="number" min="-180" max="180" step="any" required></label><label>警戒半徑（公尺）<input name="radius" type="number" min="1" max="10000" required></label><label>抵達據點範圍（公尺）<input name="arrivalRadius" type="number" min="1" max="10000" required></label><p id="siteMessage" role="status"></p><button class="action-button primary" type="submit">儲存設定</button> <button id="clearSite" class="action-button" type="button">清除設定</button></form>';
    document.querySelector('.overview-summary').append(siteCard);
    const form=el('siteForm');
    function fillSite(){for(const key of ['name','lat','lng','radius','arrivalRadius'])form.elements[key].value=config?.[key]??'';}
    fillSite();
    form.onsubmit=event=>{
        event.preventDefault();const data=Object.fromEntries(new FormData(form));
        const next=O.site({name:data.name.trim(),lat:Number(data.lat),lng:Number(data.lng),radius:Number(data.radius),arrivalRadius:Number(data.arrivalRadius)});
        if(!next){el('siteMessage').textContent='請輸入有效座標，抵達範圍須小於或等於警戒半徑。';return;}
        try {localStorage.setItem('sound-dashboard-site-v1',JSON.stringify(next));config=next;entries=new O.Entries();el('siteMessage').textContent='已儲存；對目前有效定位重新判斷。';render();}
        catch(_){el('siteMessage').textContent='瀏覽器無法儲存設定，請允許此網站使用儲存空間。';}
    };
    el('clearSite').onclick=()=>{try{localStorage.removeItem('sound-dashboard-site-v1');}catch(_){}config=null;entries=new O.Entries();fillSite();render();};
    function mapObjects(target) {
        currentTarget=target;
        if(targetMarker){targetMarker.setMap(null);targetMarker=null;}
        if(siteMarker){siteMarker.setMap(null);siteMarker=null;}
        if(zoneCircle){zoneCircle.setMap(null);zoneCircle=null;}
        if(simulationIsVisible())return;
        if(!map || !window.google?.maps){renderCoordinateFallback();return;}
        if(config){
            siteMarker=new google.maps.Marker({map,position:config,title:config.name,label:'據',zIndex:35});
            zoneCircle=new google.maps.Circle({map,center:config,radius:config.radius,strokeColor:'#ef4444',strokeOpacity:.8,strokeWeight:2,fillColor:'#ef4444',fillOpacity:.09,clickable:false});
        }
        if(target?.position){targetMarker=new google.maps.Marker({map,position:target.position,title:`無人機估測位置 ${target.id}`,icon:droneMapIcon(target.status==='inside'?'#ef4444':'#f97316'),zIndex:40});}
    }
    function render() {
        const now=Date.now();
        const detections=state.events.filter(e=>String(classLabel(e)).toLowerCase()==='drone' && now-eventTime(e)>=-2000 && now-eventTime(e)<120000);
        const tracks=[...state.tracks.values()].filter(t=>String(t.label).toLowerCase()==='drone');
        const assessments=tracks.map(t=>O.assess(t,config,now,state.runtime?.localization_enabled===true,experimentalMotionEnabled));
        const valid=assessments.filter(a=>a.position).sort((a,b)=>(b.status==='inside')-(a.status==='inside') || b.time-a.time);
        const newest=detections[0];
        for(const d of detections.filter(e=>now-eventTime(e)<15000)) {
            if(!seen.has(d.event_id)){seen.add(d.event_id);banner.textContent='偵測到無人機，點此查看即時資訊';banner.hidden=false;noticeUntil=now+8000;}
        }
        // Keep memory bounded without re-announcing records still in the active window.
        if(seen.size>1000)seen=new Set(detections.map(d=>d.event_id));
        if(now>noticeUntil)banner.hidden=true;
        for(const a of valid)if(entries.update(a.id,a.status,a.time)){
            alerts.push({id:a.id,time:a.time,site:config.name});focused=a.id;
            banner.textContent='無人機進入警戒區，點此查看目標';banner.hidden=false;showAlert();
        }
        const selected=valid.find(a=>a.id===focused) || valid[0];
        const active=selected || newest;
        panel.hidden=!active;
        el('monitorStatus').hidden=!!active;
        if(!active){banner.hidden=true;mapObjects(null);return;}
        const lost=!selected && now-eventTime(newest)>15000;
        const title=lost?'目標失去更新':selected?.status==='inside'?'無人機進入警戒區':'偵測到無人機';
        const eta=value=>value===null||value===undefined?'資料不足或路徑未相交':value===0?'已進入':`約 ${Math.ceil(value)} 秒`;
        const names={inside:'位於警戒區內',outside:'位於警戒區外',boundary:'定位誤差跨越警戒邊界',located:'尚未設定據點'};
        panel.innerHTML=`<div class="card-header"><h2>${safe(title)}</h2></div><div class="card-body"><p>${safe(selected?`目標 ${selected.id}`:`回報節點 ${newest.device_id}`)}</p><p>${safe(selected?names[selected.status]:lost?'顯示最後偵測資訊；停止抵達估算。':'已辨識無人機聲音，目標尚未定位。')}</p><p>更新時間：${safe(new Date(selected?.time??eventTime(newest)).toLocaleTimeString('zh-TW'))}</p>${selected?'':`<p>模型分數：${formatPercent(modelScore(newest))}</p>`}<div class="detail-grid"><div class="detail-item"><span>與據點距離</span><strong>${selected?.distance!=null?`${selected.distance.toFixed(0)} m`:'—'}</strong></div><div class="detail-item"><span>移動狀態</span><strong>${safe({approaching:'往據點靠近',departing:'遠離據點',stationary:'接近分量不足'}[selected?.trend]||'資料不足')}</strong></div><div class="detail-item"><span>預估進入警戒區</span><strong>${eta(selected?.zoneEta)}</strong></div><div class="detail-item"><span>預估抵達據點範圍</span><strong>${eta(selected?.arrivalEta)}</strong></div></div><p>抵達範圍：${config?`${config.arrivalRadius} m`:'尚未設定'}。時間依最後定位與固定速度估算，尚待實地驗證。</p>${valid.length>1?`<label>其他目標<select id="operationalTargetSelect">${valid.map(a=>`<option value="${safe(a.id)}" ${a.id===selected?.id?'selected':''}>${safe(a.id)}</option>`).join('')}</select></label>`:''}</div>`;
        if(el('operationalTargetSelect'))el('operationalTargetSelect').onchange=e=>{focused=e.target.value;render();};
        mapObjects(selected);
    }
    const history=document.createElement('article');history.className='card history-replay';
    history.innerHTML='<div class="card-header"><h2>歷史軌跡動畫</h2></div><div class="card-body"><p id="historyReplayStatus" role="status">選擇左側事件或軌跡，自動開始回放。</p><div id="historyMap" role="application" aria-label="歷史軌跡地圖"></div><div id="historyFallback" role="img" aria-label="歷史軌跡相對座標圖"></div><div class="history-controls"><button id="historyPlay" class="action-button" disabled>播放</button><button id="historyRestart" class="action-button" disabled>重播</button><label>倍速<select id="historySpeed"><option value="1">1×</option><option value="4">4×</option><option value="8" selected>8×</option><option value="16">16×</option></select></label><input id="historySeek" type="range" min="0" max="1" step="0.001" value="0" aria-label="歷史回放時間軸" disabled></div><p id="historyTime"></p><p>僅重現已儲存定位點，連線表示觀測順序，不代表兩點之間已知的飛行路線。</p></div>';
    const grid=document.querySelector('#view-tracks .intelligence-grid');
    const list=document.createElement('div');list.className='history-selection';
    while(grid.firstChild)list.append(grid.firstChild);grid.append(list,history);
    function pause(){if(replay)replay.playing=false;cancelAnimationFrame(animation);animation=null;el('historyPlay').textContent='播放';}
    function clear(){pause();request++;replay=null;if(historyMarker)historyMarker.setMap(null);if(historyLine)historyLine.setMap(null);historyMarker=null;historyLine=null;el('historyFallback').innerHTML='';['historyPlay','historyRestart','historySeek'].forEach(id=>el(id).disabled=true);el('historyTime').textContent='';}
    function draw() {
        if(!replay)return;
        const f=O.frame(replay.points,replay.progress);el('historySeek').value=replay.progress;
        el('historyTime').textContent=`${f.index+1} / ${replay.points.length} 個定位點；${f.timed?new Date(f.point.time).toLocaleString('zh-TW'):'缺少完整時間，以觀測順序回放'}`;
        if(historyMap){historyLine.setPath(f.path);historyMarker.setPosition(f.point);}
        else {
            const all=replay.points,lats=all.map(p=>p.lat),lngs=all.map(p=>p.lng),loLat=Math.min(...lats),loLng=Math.min(...lngs),spanLat=Math.max(...lats)-loLat||.001,spanLng=Math.max(...lngs)-loLng||.001;
            const xy=p=>[30+(p.lng-loLng)/spanLng*540,290-(p.lat-loLat)/spanLat*260];const pos=xy(f.point);
            el('historyFallback').innerHTML=`<p>相對座標圖（非地理底圖）</p><svg viewBox="0 0 600 320" aria-label="歷史觀測軌跡"><polyline points="${f.path.map(p=>xy(p).join(',')).join(' ')}" fill="none" stroke="#f59e0b" stroke-width="3"/><g transform="translate(${pos[0]-15} ${pos[1]-15}) scale(0.394737)">${droneSvg().replace(/<svg[^>]*>|<\/svg>/g,'')}</g></svg>`;
        }
    }
    function play(){if(!replay)return;if(replay.progress>=1)replay.progress=0;pause();replay.playing=true;el('historyPlay').textContent='暫停';let last=performance.now();
        const tick=now=>{if(!replay?.playing)return;replay.progress=Math.min(1,replay.progress+(now-last)*Number(el('historySpeed').value)/replay.duration);last=now;draw();if(replay.progress>=1)pause();else animation=requestAnimationFrame(tick);};animation=requestAnimationFrame(tick);
    }
    async function start(id) {
        clear();const token=request;switchView('tracks');state.selectedTrackId=String(id);renderTracksView();el('historyReplayStatus').textContent='正在載入此軌跡…';
        try{
            const payload=await fetchJson(`/tracks/${encodeURIComponent(id)}/points?limit=500`);
            if(token!==request)return;
            if(!Array.isArray(payload.points))throw new Error('missing points');
            const path=O.points({points:payload.points});
            if(path.length<2){el('historyReplayStatus').textContent='此事件尚無足夠定位點，無法產生歷史軌跡動畫。';return;}
            replay={points:path,progress:0,duration:path.every(p=>p.time!==null)&&path.at(-1).time>path[0].time?path.at(-1).time-path[0].time:Math.max(4000,path.length*1000),playing:false};
            if(window.google?.maps && !mapsLoadFailed){
                if(!historyMap)historyMap=new google.maps.Map(el('historyMap'),{center:path[0],zoom:16,mapTypeControl:false,streetViewControl:false});
                el('historyMap').hidden=false;el('historyFallback').hidden=true;
                const bounds=new google.maps.LatLngBounds();path.forEach(p=>bounds.extend(p));google.maps.event.trigger(historyMap,'resize');historyMap.fitBounds(bounds,40);
                historyLine=new google.maps.Polyline({map:historyMap,path:[],strokeColor:'#f59e0b',strokeWeight:4});historyMarker=new google.maps.Marker({map:historyMap,position:path[0],icon:droneMapIcon('#f59e0b'),title:'歷史無人機定位點'});
            }else{historyMap=null;el('historyMap').hidden=true;el('historyFallback').hidden=false;}
            el('historyReplayStatus').textContent=`軌跡 ${id}；${payload.points.length>=500?'最多顯示前 500 點，可能未含完整軌跡。':'已載入儲存的定位點。'}`;
            ['historyPlay','historyRestart','historySeek'].forEach(key=>el(key).disabled=false);draw();play();
        }catch(_){if(token===request)el('historyReplayStatus').textContent='讀取軌跡失敗，請重新選取重試。';}
    }
    async function group(id){
        clear();const token=request;switchView('tracks');el('historyReplayStatus').textContent='正在查詢事件關聯軌跡…';
        try {
            const payload=await fetchJson(`/event-groups/${encodeURIComponent(id)}/tracks`);
            if(token!==request)return;
            if(!Array.isArray(payload.tracks))throw new Error('invalid response');
            if(payload.tracks.length===1){start(String(payload.tracks[0].id));return;}
            el('historyReplayStatus').textContent=payload.tracks.length?'此事件關聯多條軌跡，請選擇要回放的軌跡。':'此事件尚無已儲存的關聯軌跡，無法播放。';
            payload.tracks.forEach(t=>{const button=document.createElement('button');button.className='action-button';button.textContent=`回放 ${t.id}`;button.onclick=()=>start(String(t.id));el('historyReplayStatus').append(button);});
        } catch(_) {if(token===request)el('historyReplayStatus').textContent='事件關聯查詢失敗，請重新選取重試。';}
    }
    el('historyPlay').onclick=()=>replay?.playing?pause():play();el('historyRestart').onclick=()=>{if(replay){replay.progress=0;play();}};
    el('historySeek').oninput=e=>{pause();if(replay){replay.progress=Number(e.target.value);draw();}};
    document.addEventListener('visibilitychange',()=>{if(document.hidden)pause();});
    window.DashboardOperationsUI={render,start,group,pause,clear,leave:()=>{pause();request++;},target:()=>currentTarget};
})();
