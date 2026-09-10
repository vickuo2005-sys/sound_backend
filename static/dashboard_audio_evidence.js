(function (root) {
    'use strict';
    const MAX_BYTES = 8 * 1024 * 1024;
    const MAX_SECONDS = 30;
    const FLOOR_DB = -80;
    const FFT_SIZE = 1024;
    function availability(event, runtime = {}) {
        if (!event?.audio_path) {
            const failed = /fail|error/i.test(String(event?.audio_encoding_status || ''));
            return {available:false, text:failed ? '錄音編碼失敗，尚無可讀取檔案' : '尚未收到此事件的錄音檔案'};
        }
        if (runtime.gcs_configured !== true) return {available:false,
            text:runtime.gcs_configured === false ? '服務尚未配置錄音儲存' : '錄音儲存狀態尚未確認'};
        return {available:true, text:'可載入錄音證據'};
    }
    function fft(real, imaginary) {
        const n = real.length;
        for (let i=1,j=0; i<n; i++) {
            let bit = n >> 1;
            for (; j & bit; bit >>= 1) j ^= bit;
            j ^= bit;
            if (i<j) { [real[i],real[j]]=[real[j],real[i]]; [imaginary[i],imaginary[j]]=[imaginary[j],imaginary[i]]; }
        }
        for (let size=2; size<=n; size*=2) {
            const angle=-2*Math.PI/size, wr=Math.cos(angle), wi=Math.sin(angle);
            for (let offset=0; offset<n; offset+=size) {
                let ur=1,ui=0;
                for (let k=0; k<size/2; k++) {
                    const a=offset+k,b=a+size/2;
                    const tr=ur*real[b]-ui*imaginary[b], ti=ur*imaginary[b]+ui*real[b];
                    real[b]=real[a]-tr; imaginary[b]=imaginary[a]-ti; real[a]+=tr; imaginary[a]+=ti;
                    const next=ur*wr-ui*wi; ui=ur*wi+ui*wr; ur=next;
                }
            }
        }
    }
    function analyze(samples, sampleRate) {
        if (!samples?.length || !Number.isFinite(sampleRate) || sampleRate<8000 || sampleRate>192000) throw new Error('audio_invalid');
        if (samples.length/sampleRate>MAX_SECONDS) throw new Error('audio_too_long');
        for (const value of samples) if (!Number.isFinite(value)) throw new Error('audio_invalid');
        const duration=samples.length/sampleRate, waveform=[];
        const width=Math.min(512,samples.length);
        for (let x=0; x<width; x++) {
            let min=Infinity,max=-Infinity;
            for (let i=Math.floor(x*samples.length/width); i<Math.floor((x+1)*samples.length/width); i++) {
                min=Math.min(min,samples[i]); max=Math.max(max,samples[i]);
            }
            waveform.push([min,max]);
        }
        const window=new Float64Array(FFT_SIZE);
        let sum=0;
        for (let i=0;i<FFT_SIZE;i++) { window[i]=.5-.5*Math.cos(2*Math.PI*i/(FFT_SIZE-1)); sum+=window[i]; }
        const columns=Math.min(160,Math.max(1,Math.ceil((samples.length-FFT_SIZE)/(FFT_SIZE/2))+1));
        const spectrum=[];
        for (let x=0;x<columns;x++) {
            const start=columns===1 ? 0 : Math.round(x*(samples.length-FFT_SIZE)/(columns-1));
            const real=new Float64Array(FFT_SIZE), imaginary=new Float64Array(FFT_SIZE);
            for (let i=0;i<FFT_SIZE;i++) real[i]=(samples[start+i] || 0)*window[i];
            fft(real,imaginary);
            const bins=new Float32Array(FFT_SIZE/2+1);
            for (let k=0;k<bins.length;k++) {
                const amplitude=Math.hypot(real[k],imaginary[k])*(k===0 || k===FFT_SIZE/2 ? 1 : 2)/sum;
                bins[k]=Math.max(FLOOR_DB,Math.min(0,20*Math.log10(Math.max(amplitude,1e-12))));
            }
            spectrum.push(bins);
        }
        return {duration,sampleRate,waveform,spectrum,fftSize:FFT_SIZE,floorDb:FLOOR_DB,displayMaxHz:Math.min(8000,sampleRate/2)};
    }
    function draw(waveCanvas, spectrumCanvas, result) {
        const ctx=waveCanvas.getContext('2d');
        ctx.fillStyle='#081421'; ctx.fillRect(0,0,waveCanvas.width,waveCanvas.height);
        ctx.strokeStyle='#20384c'; ctx.beginPath(); ctx.moveTo(0,waveCanvas.height/2); ctx.lineTo(waveCanvas.width,waveCanvas.height/2); ctx.stroke();
        ctx.strokeStyle='#26c8dc'; ctx.beginPath();
        result.waveform.forEach(([min,max],i) => {
            const x=(i+.5)*waveCanvas.width/result.waveform.length;
            ctx.moveTo(x,(1-Math.max(-1,Math.min(1,max)))*waveCanvas.height/2);
            ctx.lineTo(x,(1-Math.max(-1,Math.min(1,min)))*waveCanvas.height/2);
        }); ctx.stroke();
        const heat=spectrumCanvas.getContext('2d'), pixels=heat.createImageData(spectrumCanvas.width,spectrumCanvas.height);
        for (let y=0;y<spectrumCanvas.height;y++) for (let x=0;x<spectrumCanvas.width;x++) {
            const frame=result.spectrum[Math.min(result.spectrum.length-1,Math.floor(x*result.spectrum.length/spectrumCanvas.width))];
            const maxBin=result.displayMaxHz*result.fftSize/result.sampleRate;
            const low=Math.max(0,Math.floor((1-(y+1)/spectrumCanvas.height)*maxBin));
            const high=Math.min(frame.length-1,Math.ceil((1-y/spectrumCanvas.height)*maxBin));
            let db=FLOOR_DB;
            for (let bin=low;bin<=high;bin++) db=Math.max(db,frame[bin]);
            const value=(db-FLOOR_DB)/-FLOOR_DB, index=(y*spectrumCanvas.width+x)*4;
            pixels.data[index]=Math.round(8+247*Math.pow(value,3));
            pixels.data[index+1]=Math.round(20+215*value);
            pixels.data[index+2]=Math.round(33+135*Math.sin(value*Math.PI/2));
            pixels.data[index+3]=255;
        }
        heat.putImageData(pixels,0,0);
    }
    const errors = {
        audio_too_large:'錄音超過 8 MiB，暫不支援載入分析。',
        audio_too_long:'錄音超過 30 秒；可播放，但暫不產生圖表。',
        audio_object_missing:'事件有錄音紀錄，但儲存空間找不到檔案。',
        audio_not_uploaded:'此事件尚未上傳錄音。', event_not_found:'事件已不存在。',
        audio_storage_unavailable:'錄音儲存目前無法存取，請稍後重試。',
        audio_changed_retry:'錄音剛被更新，請重新載入。',
        audio_empty:'錄音檔案是空的。', audio_incomplete:'錄音內容不完整，請重新載入。',
        audio_decode_failed:'瀏覽器無法解碼這份錄音；可嘗試播放器，但暫無圖表。',
        audio_unsupported:'此瀏覽器不支援音訊解碼；可使用播放器。',
        audio_invalid:'錄音資料不適合分析，暫無圖表。'
    };
    function createViewer(element, event, runtime, env = root) {
        const available=availability(event,runtime);
        element.innerHTML='<strong>錄音證據</strong><p data-audio-status class="context-note" role="status"></p>'+
            '<button type="button" data-audio-load class="action-button">載入錄音與分析</button>'+
            '<audio data-audio-player controls preload="metadata" hidden></audio>'+
            '<div data-audio-charts hidden><p data-audio-meta class="context-note"></p>'+
            '<p class="context-note">波形 · 正規化振幅 −1 至 +1</p><canvas data-wave width="640" height="160" role="img" aria-label="錄音波形：時間與正規化振幅"></canvas>'+
            '<div class="audio-axis"><span>0 秒</span><span data-duration></span></div>'+
            '<p data-frequency class="context-note"></p><canvas data-spectrum width="320" height="256" role="img" aria-label="錄音聲譜：時間與頻率，顏色表示相對滿刻度振幅"></canvas>'+
            '<div class="audio-axis"><span>0 秒</span><span data-duration></span></div>'+
            '<p class="context-note">暗：低能量／亮：高能量（−80 至 0 dBFS）。聲譜採時間窗抽樣，只分析第 1 聲道；非校準聲壓、AI 分類或定位證據。</p></div>';
        const find=selector=>element.querySelector(selector), button=find('[data-audio-load]'), status=find('[data-audio-status]');
        const player=find('[data-audio-player]'), charts=find('[data-audio-charts]');
        status.textContent=available.text; button.disabled=!available.available;
        button.title='最大 8 MiB；30 秒內錄音可產生圖表';
        let disposed=false,controller=null,objectUrl=null,context=null;
        function closeContext() {
            const closing=context; context=null;
            if (typeof closing?.close==='function') closing.close().catch(()=>{});
        }
        function releaseUrl() {
            player.pause(); player.removeAttribute('src'); player.load(); player.hidden=true;
            if (objectUrl) env.URL.revokeObjectURL(objectUrl);
            objectUrl=null;
        }
        async function load() {
            if (disposed || controller || !available.available) return;
            controller=new env.AbortController(); const request=controller;
            const timeout=env.setTimeout(()=>request.abort(),35000);
            button.disabled=true; status.textContent='正在讀取錄音…'; charts.hidden=true; releaseUrl();
            try {
                const response=await env.fetch(`/events/${encodeURIComponent(event.event_id)}/audio-content`,{signal:request.signal,cache:'no-store'});
                if (!response.ok) { let code='audio_storage_unavailable'; try { code=(await response.json()).detail; } catch (_) {} throw new Error(code); }
                const size=Number(response.headers.get('content-length'));
                if (size>MAX_BYTES) throw new Error('audio_too_large');
                const data=await response.arrayBuffer();
                if (disposed) return;
                if (request.signal.aborted) throw Object.assign(new Error('timeout'), {name:'AbortError'});
                if (data.byteLength>MAX_BYTES) throw new Error('audio_too_large');
                if (!data.byteLength) throw new Error('audio_empty');
                objectUrl=env.URL.createObjectURL(new env.Blob([data],{type:response.headers.get('content-type') || 'audio/wav'}));
                player.src=objectUrl; player.hidden=false;
                const OfflineContext=env.OfflineAudioContext || env.webkitOfflineAudioContext;
                const AudioContext=env.AudioContext || env.webkitAudioContext;
                if (!OfflineContext && !AudioContext) throw new Error('audio_unsupported');
                status.textContent='正在解碼並產生波形與聲譜…';
                context=OfflineContext ? new OfflineContext(1,1,48000) : new AudioContext();
                let buffer;
                try { buffer=await context.decodeAudioData(data); } catch (_) { throw new Error('audio_decode_failed'); }
                if (disposed) return;
                if (request.signal.aborted) throw Object.assign(new Error('timeout'), {name:'AbortError'});
                const result=analyze(buffer.getChannelData(0),buffer.sampleRate);
                draw(find('[data-wave]'),find('[data-spectrum]'),result);
                find('[data-audio-meta]').textContent=`錄音 ${result.duration.toFixed(2)} 秒 · 解碼取樣率 ${result.sampleRate} Hz · ${buffer.numberOfChannels} 聲道`;
                find('[data-frequency]').textContent=`聲譜 · 顯示頻率由下往上：0–${(result.displayMaxHz/1000).toFixed(1)} kHz`;
                element.querySelectorAll('[data-duration]').forEach(item=>item.textContent=`${result.duration.toFixed(2)} 秒`);
                charts.hidden=false; status.textContent='錄音已載入，可播放及檢視圖表。';
            } catch (error) {
                if (!disposed) status.textContent=error.name==='AbortError' ? '讀取逾時，請重新載入。' : errors[error.message] || '無法讀取錄音，請重新載入。';
            } finally {
                env.clearTimeout(timeout);
                closeContext();
                if (controller===request) controller=null;
                if (!disposed) { button.disabled=false; button.textContent='重新載入錄音'; }
            }
        }
        button.addEventListener('click',load);
        player.addEventListener('error',()=>{ if (!disposed) status.textContent='播放器無法播放此檔案，請重新載入或檢查錄音格式。'; });
        return {load,dispose() {
            disposed=true; controller?.abort(); releaseUrl();
            closeContext();
        }};
    }
    const api={availability,analyze,createViewer,MAX_BYTES,MAX_SECONDS};
    if (typeof module==='object' && module.exports) module.exports=api;
    else root.DashboardAudioEvidence=api;
})(typeof window==='object' ? window : globalThis);
