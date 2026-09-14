(function (root) {
    'use strict';
    // This workspace owns all of its state. It must never import live dashboard state,
    // call application APIs, or publish simulated events onto the real event bus.
    const ORIGIN = Object.freeze({ lat: 25.039, lng: 121.5752 });
    const LIMITS = Object.freeze({ nodes: 12, targets: 20, events: 80, points: 600 });
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
    function velocity(target) {
        if (target.lost || !point(target.position) || target.speed<=0) return { x:0, y:0 };
        const next = target.waypoints[0];
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
    class LabModel {
        constructor() { this.sequence=0; this.reset(); }
        reset() {
            this.time=0; this.playing=false; this.rate=1; this.nodes=[]; this.targets=[]; this.events=[]; this.alerts=[]; this.selectedId=null;
            this.site={ x:0,y:0,name:'模擬據點',radius:150,arrivalRadius:20 }; this.replay=null;
        }
        id(prefix) { return `SIM-${prefix}-${++this.sequence}`; }
        addNode(position) {
            if (!point(position) || this.nodes.length>=LIMITS.nodes) return null;
            const node={ id:this.id('NODE'), name:`節點 ${this.nodes.length+1}`,x:position.x,y:position.y,online:true,reporting:true };
            this.nodes.push(node); return node;
        }
        moveNode(id,position) { const n=this.nodes.find(n=>n.id===id); if(n&&point(position)) { n.x=position.x;n.y=position.y;return true; } return false; }
        setSite(position,radius=this.site?.radius??150) {
            if (!point(position)||!finite(radius)||radius<20||radius>5000) return false;
            this.site={ x:position.x,y:position.y,name:'模擬據點',radius,arrivalRadius:Math.min(20,radius) };
            this.targets.forEach(t=>{t.inside=false;}); this.inspect(); return true;
        }
        createEvent(options={}) {
            if(this.targets.length>=LIMITS.targets) return null;
            const kind=['drone','car','airplane','rainfall','electric_saw'].includes(options.kind)?options.kind:'drone';
            const reporters=(options.reporters || this.nodes.filter(n=>n.reporting&&n.online).map(n=>n.id)).filter(id=>this.nodes.some(n=>n.id===id&&n.online));
            const target={ id:this.id('TARGET'),kind,position:point(options.position)?{x:options.position.x,y:options.position.y}:null,
                speed:clamp(finite(options.speed)?options.speed:15,0,100),heading:((finite(options.heading)?options.heading:90)%360+360)%360,
                waypoints:[],reporters,lost:false,inside:false,trail:[],score:clamp(finite(options.score)?options.score:.95,0,1) };
            if(target.position) target.trail.push({...target.position,time:this.time});
            this.targets.push(target);this.selectedId=target.id;
            const event={ id:this.id('EVENT'),targetId:target.id,kind,time:this.time,reporters:reporters.slice(),simulation:true };
            this.events.unshift(event);this.events=this.events.slice(0,LIMITS.events);this.replay=null;this.inspect();
            if(this.alerts.length)this.selectedId=this.alerts[0].targetId;
            return target;
        }
        selected() { return this.targets.find(t=>t.id===this.selectedId)||null; }
        reportingNodes(target=this.selected()) { return this.nodes.filter(n=>n.online&&target?.reporters.includes(n.id)); }
        geometry(target=this.selected()) { return hull(this.reportingNodes(target)); }
        positionTarget(id,p) {
            const t=this.targets.find(t=>t.id===id);if(!t||!point(p)) return false;
            t.position={x:p.x,y:p.y};t.lost=false;t.waypoints=[];t.trail.push({...t.position,time:this.time});t.trail=t.trail.slice(-LIMITS.points);this.inspect();return true;
        }
        loseTarget(id) { const t=this.targets.find(t=>t.id===id);if(t){t.lost=true;this.alerts=this.alerts.filter(a=>a.targetId!==id);} }
        inspect() {
            for(const target of this.targets) {
                const state=assess(target,this.site);
                if(state.status==='inside'&&!target.inside) {
                    this.alerts.push({id:this.id('ALERT'),targetId:target.id,time:this.time,simulation:true});
                    this.selectedId=target.id;
                }
                if(['inside','outside'].includes(state.status)) target.inside=state.status==='inside';
            }
            this.alerts=this.alerts.slice(-LIMITS.targets);
        }
        acknowledge(id) { this.alerts=this.alerts.filter(a=>a.id!==id); }
        step(seconds) {
            if(!finite(seconds)||seconds<=0||seconds>60) return;
            this.time+=seconds;
            for(const target of this.targets) {
                if(!point(target.position)||target.lost||target.speed<=0) continue;
                let remaining=seconds*target.speed;
                if(target.waypoints.length) {
                    while(remaining>0&&target.waypoints.length) {
                        const p=target.waypoints[0],dx=p.x-target.position.x,dy=p.y-target.position.y,d=Math.hypot(dx,dy);
                        if(d<=remaining) { target.position={...p};remaining-=d;target.waypoints.shift();if(!target.waypoints.length){target.speed=0;remaining=0;} }
                        else {target.position.x+=dx/d*remaining;target.position.y+=dy/d*remaining;target.heading=(Math.atan2(dx,dy)*180/Math.PI+360)%360;remaining=0;}
                    }
                } else { const v=velocity(target);target.position.x+=v.x*seconds;target.position.y+=v.y*seconds; }
                target.trail.push({...target.position,time:this.time});target.trail=target.trail.slice(-LIMITS.points);
            }
            this.inspect();
        }
        replayEvent(eventId) {
            const event=this.events.find(e=>e.id===eventId),target=this.targets.find(t=>t.id===event?.targetId);
            if(!event) return false;
            this.playing=false;this.alerts=[];
            this.replay={eventId,kind:event.kind,points:copy(target?.trail||[]),fraction:0,playing:(target?.trail.length||0)>1};
            return true;
        }
        leave() { this.playing=false;this.alerts=[];if(this.replay)this.replay.playing=false; }
        preset(name) {
            this.reset();
            const count=name==='one'?1:name==='two'?2:3;
            [{x:-220,y:-120},{x:220,y:-120},{x:0,y:240}].slice(0,count).forEach(p=>this.addNode(p));
            if(name==='idle') return;
            const options={position:{x:-500,y:0},speed:25,heading:90,kind:name==='non_drone'?'car':'drone'};
            if(name==='depart') Object.assign(options,{position:{x:220,y:0},heading:90});
            if(name==='passby') Object.assign(options,{position:{x:-450,y:260},heading:90});
            if(name==='inside') Object.assign(options,{position:{x:60,y:20},speed:0});
            if(name==='missing') Object.assign(options,{position:null,speed:0});
            this.createEvent(options);
            if(name==='multiple') this.createEvent({position:{x:90,y:50},speed:0,heading:270});
            if(name==='lost') this.loseTarget(this.selectedId);
            if(name==='offline') this.nodes[1].online=false;
            this.playing=!['inside','missing','lost','non_drone'].includes(name);
        }
    }
    function replayPoint(replay) {
        const path=replay?.points||[];if(!path.length)return null;
        const first=path[0],last=path.at(-1),time=first.time+(last.time-first.time)*clamp(replay.fraction,0,1);
        let index=path.findLastIndex(p=>p.time<=time);index=Math.max(0,index);
        const a=path[index],b=path[index+1];
        const f=b&&b.time>a.time?(time-a.time)/(b.time-a.time):0;
        return {x:a.x+(b?b.x-a.x:0)*f,y:a.y+(b?b.y-a.y:0)*f,time,index};
    }
    const names={drone:'無人機',car:'汽車',airplane:'飛機',rainfall:'雨聲',electric_saw:'電鋸'};
    const statuses={inside:'已進入警戒區',outside:'警戒區外',located:'已放置模擬位置',lost:'目標失聯',unlocated:'位置未知'};
    const trends={approaching:'往據點靠近',departing:'正在遠離據點',stationary:'停止或橫向移動'};
    const duration=seconds=>seconds===null?'—':seconds===0?'已到達':`${Math.ceil(seconds)} 秒`;
    const clock=seconds=>`${Math.floor(seconds/60).toString().padStart(2,'0')}:${Math.floor(seconds%60).toString().padStart(2,'0')}`;
    const DRONE_PATH='M -9 -6 L 9 6 M -9 6 L 9 -6 M -13 -6 A 4 4 0 1 0 -5 -6 A 4 4 0 1 0 -13 -6 M 5 -6 A 4 4 0 1 0 13 -6 A 4 4 0 1 0 5 -6 M -13 6 A 4 4 0 1 0 -5 6 A 4 4 0 1 0 -13 6 M 5 6 A 4 4 0 1 0 13 6 A 4 4 0 1 0 5 6';
    class Workspace {
        constructor(container) {
            this.container=container;this.model=new LabModel();this.model.preset('idle');this.active=false;this.timer=null;this.mode='inspect';this.editNode=null;
            this.pendingPosition={x:-450,y:0};this.googleMap=null;this.googleOverlays=[];this.googleListener=null;this.fitted=false;this.lastTime=0;
            this.mount();
        }
        $(selector) { return this.container.querySelector(selector); }
        mount() {
            this.container.innerHTML=`<section class="slab" aria-label="獨立模擬工作區">
                <header class="slab-header"><div><span class="slab-eyebrow">SIMULATION LAB</span><h2>模擬工作區</h2><p>親手佈置節點、建立事件與演示警戒，所有操作都留在這個工作區。</p></div><strong class="slab-isolation">模擬資料 · 不影響即時系統</strong></header>
                <div class="slab-steps" aria-label="操作順序"><span><b>1</b> 點地圖放置節點與據點</span><span><b>2</b> 勾選回報節點、建立事件</span><span><b>3</b> 播放移動、觀察警告與 ETA</span></div>
                <div class="slab-presets"><label>快速展示 <select data-field="preset"><option value="approach">無人機接近 → 進入警戒</option><option value="idle">一般監控／沒有事件</option><option value="one">單節點偵測脈動</option><option value="two">兩節點連線</option><option value="three">三節點偵測範圍</option><option value="passby">旁側飛越、不會抵達</option><option value="depart">遠離據點</option><option value="inside">直接出現在警戒區內</option><option value="multiple">多目標、警戒優先</option><option value="missing">有偵測、目標位置未知</option><option value="lost">目標失聯</option><option value="offline">節點離線</option><option value="non_drone">非無人機聲音</option></select></label><button data-action="preset" class="slab-primary">載入展示</button><span>載入會取代目前的模擬內容。</span><button data-action="clear">清空模擬</button></div>
                <div class="slab-layout"><aside class="slab-tools"><section class="slab-card"><h3><span>01</span> 佈置場景</h3><div class="slab-two"><button data-action="place-node">＋ 點圖新增節點</button><button data-action="place-site">◎ 點圖設定據點</button></div><label>警戒半徑（公尺）<input data-field="radius" type="number" min="20" max="5000" value="150"></label><button data-action="radius">更新模擬警戒區</button><div data-slot="site" class="slab-hint"></div><p class="slab-hint">選擇「移動」後點擊地圖調整位置。勾選的線上節點會參與下一個事件。</p><div data-slot="nodes"></div></section>
                <section class="slab-card"><h3><span>02</span> 建立模擬事件</h3><label>聲音類型<select data-field="kind"><option value="drone">無人機 Drone</option><option value="car">汽車 Car</option><option value="airplane">飛機 Airplane</option><option value="rainfall">雨聲 Rainfall</option><option value="electric_saw">電鋸 Electric_saw</option></select></label><div class="slab-two"><label>速度（m/s）<input data-field="speed" type="number" min="0" max="100" value="25"></label><label>航向（度）<input data-field="heading" type="number" min="0" max="359" value="90"></label></div><p class="slab-hint">0° 向北、90° 向東；速度與航向是你指定的模擬值。</p><label class="slab-check"><input data-field="unlocated" type="checkbox"> 模擬只有聲音、尚未定位</label><button data-action="place-target">點地圖選擇出現位置</button><div data-slot="pending" class="slab-hint"></div><button data-action="create" class="slab-primary slab-wide">建立事件並主動顯示</button></section></aside>
                <main class="slab-main"><section class="slab-card slab-map-card"><div class="slab-map-top"><h3>模擬現場</h3><span data-slot="clock">00:00</span><button data-action="fit">顯示全部位置</button></div><div data-slot="mode" class="slab-mode" role="status"></div><div class="slab-map-frame"><div data-slot="google" class="slab-google" hidden></div><svg data-slot="map" class="slab-map" viewBox="0 0 800 520" role="img" aria-label="可點擊的模擬位置圖"></svg><span class="slab-map-watermark">SIMULATION · 全部位置均為人為設定</span></div><div class="slab-legend"><span>◆ 節點</span><span>◎ 據點 / 警戒圈</span><span>✣ 無人機</span><span>連線 / 色塊為回報節點覆蓋示意，不是定位精度</span></div><div class="slab-playbar"><button data-action="play" class="slab-primary">▶ 開始模擬</button><button data-action="step">前進 1 秒</button><label>播放速度<select data-field="rate"><option value="1">1×</option><option value="2">2×</option><option value="5">5×</option><option value="10">10×</option></select></label><button data-action="place-waypoint">點圖加入飛行路徑</button><button data-action="stop-target">停止選取目標</button></div><p class="slab-hint">加入路徑前，先在右側選擇一台無人機；可連續點擊，飛到最後一點會停止。</p></section>
                <section class="slab-card slab-history"><h3>動畫回顧 <small>只包含本工作區建立的事件</small></h3><div data-slot="replay"></div><div data-slot="events"></div></section></main>
                <aside class="slab-detail"><section class="slab-card slab-important"><h3>重要資訊 <span class="slab-badge">主動更新</span></h3><div data-slot="targets"></div><div data-slot="detail"></div><div class="slab-two"><button data-action="lost">模擬目標失聯</button><button data-action="reconnect-target">恢復目標回報</button></div><button data-action="apply-motion" class="slab-wide">套用左側速度 / 航向至選取目標</button></section><section class="slab-card slab-notes"><h3>展示操作提示</h3><ul><li>一般監控時，右側顯示節點概況。</li><li>建立無人機事件，資訊自動切換；進區時在此工作區內彈出警告。</li><li>節點離線後仍保留位置，回報連線會排除離線節點。</li><li>按歷史事件即可原地播放軌跡；沒有位置時清楚顯示缺少軌跡。</li><li>離開工作區會暫停模擬並關閉警告。</li></ul></section></aside></div>
                <div data-slot="message" class="slab-message" role="status"></div><div data-slot="alert" class="slab-alert-host" aria-live="assertive"></div>
            </section>`;
            this.boundClick=e=>this.handleClick(e);this.boundChange=e=>this.handleChange(e);
            this.container.addEventListener('click',this.boundClick);this.container.addEventListener('change',this.boundChange);
            this.render();
        }
        enter() {
            if(this.active)return;this.active=true;this.lastTime=Date.now();this.tryGoogle();this.render();
            this.timer=root.setInterval(()=>{const now=Date.now(),elapsed=Math.min(1,(now-this.lastTime)/1000);this.lastTime=now;
                if(this.model.replay?.playing) {this.model.replay.fraction=Math.min(1,this.model.replay.fraction+elapsed/12*this.model.rate);if(this.model.replay.fraction>=1)this.model.replay.playing=false;this.renderMap();this.renderReplay();}
                else if(this.model.playing){this.model.step(elapsed*this.model.rate);this.$('[data-slot="clock"]').textContent=`模擬 ${clock(this.model.time)}`;this.renderDetail();this.renderAlert();this.renderMap();}
            },200);
        }
        leave() {this.active=false;if(this.timer)root.clearInterval(this.timer);this.timer=null;this.model.leave();this.render();}
        destroy() {this.leave();this.container.removeEventListener('click',this.boundClick);this.container.removeEventListener('change',this.boundChange);this.clearGoogle();if(this.googleListener?.remove)this.googleListener.remove();this.container.innerHTML='';}
        message(text) {this.$('[data-slot="message"]').textContent=text;}
        field(name) {return this.$(`[data-field="${name}"]`);}
        setMode(mode,nodeId=null) {this.mode=mode;this.editNode=nodeId;this.renderMode();}
        handleClick(event) {
            const button=event.target.closest('[data-action]');
            if(button&&this.container.contains(button)) {
                const action=button.dataset.action,id=button.dataset.id,m=this.model;
                if(action==='preset'){m.preset(this.field('preset').value);this.mode='inspect';this.field('radius').value=m.site.radius;this.fit();this.message('已載入模擬展示；所有內容僅存在於此工作區。');}
                else if(action==='clear'){m.reset();this.mode='inspect';this.field('radius').value=150;this.message('模擬內容已清空，即時系統未變更。');}
                else if(action==='place-node')this.setMode('node');
                else if(action==='place-site')this.setMode('site');
                else if(action==='move-node')this.setMode('move-node',id);
                else if(action==='toggle-node'){const n=m.nodes.find(n=>n.id===id);if(n)n.online=!n.online;}
                else if(action==='remove-node'){m.nodes=m.nodes.filter(n=>n.id!==id);}
                else if(action==='radius'){const radius=Number(this.field('radius').value);if(!m.setSite(m.site,radius))this.message('請輸入 20 到 5000 公尺的警戒半徑。');else this.message('已更新模擬警戒區。');}
                else if(action==='place-target')this.setMode('target');
                else if(action==='place-waypoint'){if(!point(m.selected()?.position)||m.selected()?.lost)this.message('請先建立或選取一個有位置且正在回報的目標。');else this.setMode('waypoint');}
                else if(action==='create'){
                    const speed=Number(this.field('speed').value),heading=Number(this.field('heading').value);
                    if(!finite(speed)||speed<0||speed>100||!finite(heading)||heading<0||heading>=360){this.message('速度需為 0–100 m/s，航向需為 0–359°。');return;}
                    const target=m.createEvent({kind:this.field('kind').value,position:this.field('unlocated').checked?null:this.pendingPosition,speed,heading});
                    if(!target)this.message('最多展示 20 個目標，請先清空模擬。');else {this.mode='inspect';this.message(`已建立 ${target.id}，右側資訊已主動更新。`);}
                }
                else if(action==='play'){m.replay=null;m.playing=!m.playing;this.mode='inspect';}
                else if(action==='step'){m.replay=null;m.playing=false;m.step(1);}
                else if(action==='select-target'){m.selectedId=id;m.replay=null;}
                else if(action==='stop-target'){const t=m.selected();if(t){t.speed=0;t.waypoints=[];}else this.message('請先選擇目標。');}
                else if(action==='lost')m.loseTarget(m.selectedId);
                else if(action==='reconnect-target'){const t=m.selected();if(t){t.lost=false;m.inspect();}}
                else if(action==='apply-motion'){const t=m.selected(),speed=Number(this.field('speed').value),heading=Number(this.field('heading').value);if(!t)this.message('請先建立或選取目標。');else if(!finite(speed)||speed<0||speed>100||!finite(heading)||heading<0||heading>=360)this.message('請確認速度與航向範圍。');else{t.speed=speed;t.heading=heading;t.waypoints=[];this.message('已套用指定運動值，原飛行路徑已清除。');}}
                else if(action==='replay'){m.replayEvent(id);this.mode='inspect';}
                else if(action==='replay-play'){if(m.replay){if(m.replay.fraction>=1)m.replay.fraction=0;m.replay.playing=!m.replay.playing;}}
                else if(action==='replay-restart'){if(m.replay){m.replay.fraction=0;m.replay.playing=m.replay.points.length>1;}}
                else if(action==='replay-close')m.replay=null;
                else if(action==='ack')m.acknowledge(id);
                else if(action==='cancel-mode')this.mode='inspect';
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
            if(el.dataset.nodeCheck){const n=this.model.nodes.find(n=>n.id===el.dataset.nodeCheck);if(n)n.reporting=el.checked;}
            else if(el.dataset.field==='rate'){this.model.rate=clamp(Number(el.value)||1,1,10);}
            else if(el.dataset.field==='replay-range'&&this.model.replay){this.model.replay.fraction=clamp(Number(el.value)/100,0,1);this.model.replay.playing=false;this.renderMap();this.renderReplay();}
        }
        mapClick(p) {
            if(!point(p)){this.message('請在模擬地圖範圍內放置位置。');return;}
            if(this.mode==='node'){if(!this.model.addNode(p))this.message('最多放置 12 個模擬節點。');else this.message('已新增模擬節點，可繼續點擊新增。');}
            else if(this.mode==='move-node'){this.model.moveNode(this.editNode,p);this.mode='inspect';this.message('已移動模擬節點。');}
            else if(this.mode==='site'){this.model.setSite(p);this.mode='inspect';this.message('已設定模擬據點與警戒區。');}
            else if(this.mode==='target'){this.pendingPosition={...p};this.mode='inspect';this.message('出現位置已選好，按「建立事件並主動顯示」。');}
            else if(this.mode==='waypoint'){const t=this.model.selected();if(t&&point(t.position)){t.waypoints.push({...p});if(!t.speed)t.speed=clamp(Number(this.field('speed').value)||25,1,100);this.message(`已加入第 ${t.waypoints.length} 個路徑點；按開始模擬播放。`);}}
            this.render();
        }
        renderMode(){
            const labels={inspect:'可先選擇快速展示，或用左側工具親手佈置場景。',node:'正在新增節點：點擊地圖，可連續放置。','move-node':'正在移動節點：點擊新位置。',site:'正在設定據點：點擊地圖，警戒圈會一起移動。',target:'正在選擇無人機出現位置：點擊地圖。',waypoint:'正在加入飛行路徑：依序點擊，目標會沿著路徑移動。'};
            this.$('[data-slot="mode"]').innerHTML=`<span>${labels[this.mode]}</span>${this.mode!=='inspect'?'<button data-action="cancel-mode">完成選點</button>':''}`;
            this.$('[data-slot="map"]').classList.toggle('slab-picking',this.mode!=='inspect');
            if(this.googleMap)this.googleMap.setOptions({draggableCursor:this.mode==='inspect'?null:'crosshair'});
        }
        render() {
            const m=this.model;
            this.renderMode();this.$('[data-slot="clock"]').textContent=`模擬 ${clock(m.time)}`;
            this.$('[data-action="play"]').textContent=m.playing?'Ⅱ 暫停模擬':'▶ 開始模擬';
            this.field('rate').value=m.rate;
            this.$('[data-slot="nodes"]').innerHTML=m.nodes.length?m.nodes.map(n=>`<div class="slab-node-row"><label class="slab-check"><input type="checkbox" data-node-check="${n.id}" ${n.reporting?'checked':''} aria-label="${escape(n.name)} 參與回報"><b>${escape(n.name)}</b></label><span class="${n.online?'slab-online':'slab-offline'}">${n.online?'線上':'離線'}</span><button data-action="move-node" data-id="${n.id}">移動</button><button data-action="toggle-node" data-id="${n.id}">${n.online?'離線':'上線'}</button><button data-action="remove-node" data-id="${n.id}" aria-label="刪除 ${escape(n.name)}">×</button></div>`).join(''):'<p class="slab-empty">尚未放置節點。點「新增節點」後點擊地圖。</p>';
            const site=latLng(m.site);this.$('[data-slot="site"]').textContent=`據點：${site.lat.toFixed(5)}, ${site.lng.toFixed(5)} · 警戒 ${m.site.radius} m · 抵達 ${m.site.arrivalRadius} m`;
            const pending=latLng(this.pendingPosition);this.$('[data-slot="pending"]').textContent=`出現位置：${pending.lat.toFixed(5)}, ${pending.lng.toFixed(5)}`;
            this.renderDetail();this.renderReplay();this.renderAlert();this.renderMap();
        }
        renderDetail() {
            const m=this.model,t=m.selected(),slot=this.$('[data-slot="detail"]');
            const targetMenuKey=JSON.stringify([m.selectedId,m.targets.map(item=>[item.id,item.kind,assess(item,m.site).status])]);
            if(this.targetMenuKey!==targetMenuKey){
            this.targetMenuKey=targetMenuKey;
            this.$('[data-slot="targets"]').innerHTML=m.targets.length?`<label>目前目標<select data-field="target-select">${m.targets.map(item=>`<option value="${item.id}" ${item.id===m.selectedId?'selected':''}>${escape(names[item.kind])} · ${item.id.replace('SIM-TARGET-','#')}${assess(item,m.site).status==='inside'?' · 警戒中':''}</option>`).join('')}</select></label>`:'';
            const select=this.field('target-select');if(select)select.onchange=()=>{m.selectedId=select.value;m.replay=null;this.render();};
            }
            if(!t){slot.innerHTML=`<div class="slab-idle-icon">◎</div><h4>一般節點監控</h4><p>尚無模擬事件</p><div class="slab-metrics"><div><span>線上節點</span><b>${m.nodes.filter(n=>n.online).length} / ${m.nodes.length}</b></div><div><span>模擬警戒半徑</span><b>${m.site.radius} m</b></div></div><p class="slab-hint">建立事件後，這裡會自動顯示目標資訊。</p>`;return;}
            const a=assess(t,m.site),position=point(t.position)?latLng(t.position):null;
            slot.innerHTML=`<div class="slab-target-heading"><span class="slab-target-icon">${t.kind==='drone'?'✣':'◉'}</span><div><h4>${escape(names[t.kind])}</h4><small>${t.id}</small></div></div><strong class="slab-target-status ${a.status==='inside'?'slab-danger':''}">${statuses[a.status]}${a.trend?` · ${trends[a.trend]}`:''}</strong><div class="slab-metrics"><div><span>距據點</span><b>${a.distance===null?'—':Math.round(a.distance)+' m'}</b></div><div><span>指定速度</span><b>${t.lost?'—':t.speed.toFixed(1)+' m/s'}</b></div><div><span>進入警戒 ETA</span><b>${t.kind==='drone'?duration(a.zoneEta):'不適用'}</b></div><div><span>抵達據點 ETA</span><b>${t.kind==='drone'?duration(a.arrivalEta):'不適用'}</b></div></div><p class="slab-hint">${position?`${t.lost?'最後位置':'人為位置'}：${position.lat.toFixed(5)}, ${position.lng.toFixed(5)}`:'只有聲音回報：不產生目標座標、軌跡或 ETA。'}</p><p class="slab-hint">回報節點：${m.reportingNodes(t).map(n=>escape(n.name)).join('、')||'沒有線上節點'}<br>模擬分類分數 ${(t.score*100).toFixed(0)}% · 已記錄 ${t.trail.length} 個點</p><p class="slab-disclaimer">ETA 依你指定的目前方向與速度外推，路徑轉彎後會更新；僅供展示，未經實測。</p>`;
        }
        renderAlert() {
            const alerts=this.active&&!this.model.replay?this.model.alerts:[],alert=alerts[0];
            const key=JSON.stringify([alerts.map(a=>a.id),this.model.site.radius]);
            if(this.alertKey===key)return;
            this.alertKey=key;
            this.$('[data-slot="alert"]').innerHTML=alert?`<section class="slab-alert" role="alertdialog" aria-modal="false" aria-label="模擬警戒區進入警告"><div class="slab-alert-icon">!</div><div><span class="slab-badge">SIMULATION · 模擬警告</span><h3>無人機進入警戒區</h3><p>${alert.targetId} · 模擬據點 · ${clock(alert.time)}</p><p>警戒半徑 ${this.model.site.radius} 公尺${alerts.length>1?` · 另有 ${alerts.length-1} 則模擬警告`:''}</p></div><button data-action="ack" data-id="${alert.id}" class="slab-primary">確認模擬警告</button></section>`:'';
        }
        renderReplay() {
            const replay=this.model.replay,slot=this.$('[data-slot="replay"]');
            slot.innerHTML=replay?`<div class="slab-replay"><b>回顧 ${replay.eventId}</b><p>${replay.points.length>1?'地圖正在回放人為建立的歷史軌跡。':replay.points.length===1?'只有一個位置點，顯示靜態位置。':'此事件沒有目標位置，無法產生軌跡動畫。'}</p><div class="slab-playbar"><button data-action="replay-play" ${replay.points.length<2?'disabled':''}>${replay.playing?'Ⅱ 暫停回顧':'▶ 播放回顧'}</button><button data-action="replay-restart" ${replay.points.length<2?'disabled':''}>重播</button><input data-field="replay-range" aria-label="模擬歷史回顧時間軸" type="range" min="0" max="100" value="${Math.round(replay.fraction*100)}" ${replay.points.length<2?'disabled':''}><span>${Math.round(replay.fraction*100)}%</span><button data-action="replay-close">返回模擬現場</button></div></div>`:'<p class="slab-hint">點選下方事件，地圖會自動播放該目標在本次模擬留下的軌跡。</p>';
            this.$('[data-slot="events"]').innerHTML=this.model.events.length?this.model.events.slice(0,20).map(e=>`<button class="slab-event ${replay?.eventId===e.id?'is-selected':''}" data-action="replay" data-id="${e.id}"><span>${clock(e.time)} · ${names[e.kind]}</span><small>${e.id}</small><b>動畫回顧 →</b></button>`).join(''):'<p class="slab-empty">尚無模擬事件</p>';
        }
        bounds() {
            const points=[this.model.site,...this.model.nodes,...this.model.targets.filter(t=>point(t.position)).map(t=>t.position),...this.model.targets.flatMap(t=>t.waypoints),...(this.model.replay?.points||[])];
            let minX=-600,maxX=600,minY=-390,maxY=390;
            for(const p of points){minX=Math.min(minX,p.x-100);maxX=Math.max(maxX,p.x+100);minY=Math.min(minY,p.y-100);maxY=Math.max(maxY,p.y+100);}
            const site=this.model.site;minX=Math.min(minX,site.x-site.radius-80);maxX=Math.max(maxX,site.x+site.radius+80);minY=Math.min(minY,site.y-site.radius-80);maxY=Math.max(maxY,site.y+site.radius+80);
            const scale=Math.min(760/(maxX-minX),480/(maxY-minY));return {cx:(minX+maxX)/2,cy:(minY+maxY)/2,scale};
        }
        project(p) {const b=this.mapBounds;return {x:400+(p.x-b.cx)*b.scale,y:260-(p.y-b.cy)*b.scale};}
        unproject(p) {const b=this.mapBounds;return {x:(p.x-400)/b.scale+b.cx,y:(260-p.y)/b.scale+b.cy};}
        renderMap() {
            this.mapBounds=this.bounds();const m=this.model,p=this.project.bind(this),site=p(m.site),geometry=m.geometry(),replay=m.replay;
            const nodes=m.nodes.map(n=>{const xy=p(n),active=!replay&&m.reportingNodes().some(item=>item.id===n.id)&&m.selected()?.kind==='drone'&&!m.selected()?.lost;return `<g class="slab-node ${n.online?'':'is-offline'}" transform="translate(${xy.x},${xy.y})">${active?'<circle class="slab-pulse" r="20"/>':''}<path d="M0 -8L8 0L0 8L-8 0Z"/><text y="25">${escape(n.name)}${n.online?'':' · 離線'}</text></g>`;}).join('');
            const region=!replay&&m.selected()?.kind==='drone'&&!m.selected()?.lost&&geometry.length>=2?`<${geometry.length===2?'polyline':'polygon'} class="slab-reporting-region" points="${geometry.map(n=>{const q=p(n);return `${q.x},${q.y}`;}).join(' ')}"/>`:'';
            let targets='';
            if(replay){const current=replayPoint(replay);if(current){const q=p(current),path=replay.points.slice(0,current.index+1).concat(current);targets=`<polyline class="slab-trail" points="${path.map(n=>{const r=p(n);return `${r.x},${r.y}`;}).join(' ')}"/>${this.targetSvg(q,replay.kind,'回顧目標',false,true)}`;}}
            else for(const target of m.targets){if(!point(target.position))continue;const q=p(target.position);const path=target.trail.map(n=>{const r=p(n);return `${r.x},${r.y}`;}).join(' ');targets+=`<polyline class="slab-trail ${target.id===m.selectedId?'':'is-muted'}" points="${path}"/>`;if(target.waypoints.length)targets+=`<polyline class="slab-waypoints" points="${[target.position,...target.waypoints].map(n=>{const r=p(n);return `${r.x},${r.y}`;}).join(' ')}"/>`;targets+=this.targetSvg(q,target.kind,target.id.replace('SIM-TARGET-','#'),target.lost,target.id===m.selectedId);}
            const pending=this.mode==='target'?p(this.pendingPosition):null;
            this.$('[data-slot="map"]').innerHTML=`<defs><pattern id="slab-grid" width="40" height="40" patternUnits="userSpaceOnUse"><path d="M40 0H0V40" fill="none" stroke="currentColor" stroke-opacity=".1"/></pattern></defs><rect width="800" height="520" fill="url(#slab-grid)"/><text class="slab-north" x="770" y="30">N ↑</text><circle class="slab-zone" cx="${site.x}" cy="${site.y}" r="${m.site.radius*this.mapBounds.scale}"/>${region}<g class="slab-site" transform="translate(${site.x},${site.y})"><circle r="8"/><path d="M-13 0H13M0-13V13"/><text y="28">模擬據點</text></g>${nodes}${targets}${pending?`<circle class="slab-pending" cx="${pending.x}" cy="${pending.y}" r="10"/>`:''}<text class="slab-scale" x="20" y="495">${Math.round(100/this.mapBounds.scale)} m / 圖上 100 單位 · 相對位置圖</text>`;
            if(this.googleMap)this.renderGoogle();
        }
        targetSvg(p,kind,label,lost,selected){return `<g class="slab-aircraft ${lost?'is-lost':''} ${selected?'is-selected':''}" transform="translate(${p.x},${p.y})"><circle class="slab-target-halo" r="24"/>${kind==='drone'?`<path d="${DRONE_PATH}"/>`:'<circle r="7"/>'}<text y="39">${escape(label)}${lost?' · 失聯':''}</text></g>`;}
        tryGoogle(){
            if(this.googleMap||!root.google?.maps?.Map)return;
            try{this.googleMap=new root.google.maps.Map(this.$('[data-slot="google"]'),{center:ORIGIN,zoom:16,mapTypeControl:false,streetViewControl:false,fullscreenControl:false,gestureHandling:'cooperative'});
                this.googleListener=this.googleMap.addListener('click',event=>{if(this.mode!=='inspect'&&event.latLng)this.mapClick(offset({lat:event.latLng.lat(),lng:event.latLng.lng()}));});
                this.$('[data-slot="google"]').hidden=false;this.$('[data-slot="map"]').setAttribute('hidden','');this.renderGoogle();this.fit();
            }catch{this.googleMap=null;this.$('[data-slot="google"]').hidden=true;this.$('[data-slot="map"]').removeAttribute('hidden');}
        }
        clearGoogle(){this.googleOverlays.forEach(o=>o.setMap(null));this.googleOverlays=[];}
        renderGoogle(){
            const g=root.google.maps,m=this.model;this.clearGoogle();const add=o=>this.googleOverlays.push(o);
            add(new g.Circle({map:this.googleMap,center:latLng(m.site),radius:m.site.radius,strokeColor:'#FBBF24',strokeOpacity:.8,strokeWeight:2,fillColor:'#FBBF24',fillOpacity:.1,clickable:false}));
            add(new g.Marker({map:this.googleMap,position:latLng(m.site),label:{text:'據點',color:'#0B1220',fontWeight:'700'},icon:{path:g.SymbolPath.CIRCLE,scale:16,fillColor:'#5EEAD4',fillOpacity:1,strokeColor:'#0B1220',strokeWeight:2},clickable:false}));
            for(const n of m.nodes){add(new g.Marker({map:this.googleMap,position:latLng(n),title:`${n.name}${n.online?'':' 離線'}`,label:{text:n.name,color:'#0B1220',fontSize:'11px'},icon:{path:g.SymbolPath.CIRCLE,scale:18,fillColor:n.online?'#5EEAD4':'#9EACC0',fillOpacity:1,strokeColor:'#0B1220',strokeWeight:2},clickable:false}));}
            const geometry=m.geometry(),target=m.selected();
            if(!m.replay&&target?.kind==='drone'&&!target.lost){
                const pulse=(Math.sin(m.time*4)+1)/2;
                for(const n of m.reportingNodes(target))add(new g.Circle({map:this.googleMap,center:latLng(n),radius:18+pulse*18,strokeColor:'#5EEAD4',strokeWeight:2,strokeOpacity:1-pulse*.6,fillColor:'#5EEAD4',fillOpacity:.12,clickable:false}));
                if(geometry.length===2)add(new g.Polyline({map:this.googleMap,path:geometry.map(latLng),strokeColor:'#5EEAD4',strokeWeight:3,strokeOpacity:.7,clickable:false}));
                else if(geometry.length>=3)add(new g.Polygon({map:this.googleMap,paths:geometry.map(latLng),strokeColor:'#5EEAD4',strokeWeight:2,fillColor:'#5EEAD4',fillOpacity:.15,clickable:false}));
            }
            const draw=(position,kind,label,lost,trail)=>{
                if(trail.length>1)add(new g.Polyline({map:this.googleMap,path:trail.map(latLng),strokeColor:'#C4B5FD',strokeOpacity:.7,strokeWeight:3,clickable:false}));
                add(new g.Marker({map:this.googleMap,position:latLng(position),title:label,icon:{path:kind==='drone'?DRONE_PATH:g.SymbolPath.CIRCLE,scale:kind==='drone'?1.1:8,strokeColor:lost?'#9EACC0':'#FBBF24',strokeWeight:2,fillColor:'#142033',fillOpacity:1},clickable:false}));
            };
            if(m.replay){const current=replayPoint(m.replay);if(current)draw(current,m.replay.kind,'模擬回顧',false,m.replay.points.slice(0,current.index+1).concat(current));}
            else for(const t of m.targets){if(point(t.position))draw(t.position,t.kind,t.id,t.lost,t.trail);if(t.waypoints.length)add(new g.Polyline({map:this.googleMap,path:[t.position,...t.waypoints].map(latLng),strokeColor:'#60A5FA',strokeWeight:2,strokeOpacity:.7,clickable:false}));}
        }
        fit(){this.fitted=true;if(!this.googleMap)return;const g=root.google.maps,b=new g.LatLngBounds(),extent=this.bounds();[{x:extent.cx-400/extent.scale,y:extent.cy-260/extent.scale},{x:extent.cx+400/extent.scale,y:extent.cy+260/extent.scale}].forEach(p=>b.extend(latLng(p)));this.googleMap.fitBounds(b,30);}
    }
    let workspace=null;
    const api={LabModel,assess,circleEntry,hull,latLng,offset,replayPoint,LIMITS,
        mount(container){if(!container)throw new Error('A simulation workspace container is required');if(workspace)workspace.destroy();workspace=new Workspace(container);return workspace;},
        enter(){workspace?.enter();},leave(){workspace?.leave();},destroy(){workspace?.destroy();workspace=null;}};
    if(typeof module==='object'&&module.exports)module.exports=api;
    else root.DashboardSimulationLab=api;
})(typeof globalThis==='object'?globalThis:this);
