const assert=require('node:assert/strict');
const {createViewer}=require('../../static/dashboard_audio_evidence.js');
function deferred() { let resolve,reject; const promise=new Promise((yes,no)=>{resolve=yes;reject=no;}); return {promise,resolve,reject}; }
function harness(fetch,decode) {
    const nodes=new Map(),created=[],revoked=[],contexts=[];
    const node=key=>{
        if (!nodes.has(key)) nodes.set(key,{textContent:'',hidden:true,disabled:false,width:320,height:160,
            addEventListener(){},pause(){},load(){},removeAttribute(name){delete this[name];},
            getContext(){return {fillRect(){},beginPath(){},moveTo(){},lineTo(){},stroke(){},putImageData(){},
                createImageData(w,h){return {data:new Uint8ClampedArray(w*h*4)};}};}});
        return nodes.get(key);
    };
    class Context {
        constructor(){contexts.push(this);this.closed=false;}
        decodeAudioData(data){return decode ? decode(data) : Promise.resolve({sampleRate:16000,numberOfChannels:1,getChannelData:()=>new Float32Array(1600)});}
        close(){this.closed=true;return Promise.resolve();}
    }
    const element={innerHTML:'',querySelector:node,querySelectorAll:()=>[]};
    const env={fetch,AudioContext:Context,AbortController,Blob,setTimeout,clearTimeout,
        URL:{createObjectURL(){const url=`blob:test-${created.length}`;created.push(url);return url;},revokeObjectURL(url){revoked.push(url);}}};
    return {node,created,revoked,contexts,view:createViewer(element,{event_id:'A',audio_path:'a.wav'},{gcs_configured:true},env)};
}
const ok=()=>({ok:true,headers:new Map([['content-length','4'],['content-type','audio/wav']]),arrayBuffer:async()=>new ArrayBuffer(4)});
(async()=>{
    const ready=harness(async()=>ok());
    await ready.view.load();
    assert.equal(ready.node('[data-audio-charts]').hidden,false);
    assert.equal(ready.node('[data-audio-player]').src,'blob:test-0');
    assert(ready.contexts[0].closed);
    await ready.view.load();
    assert.deepEqual(ready.revoked,['blob:test-0']);
    ready.view.dispose();
    assert.deepEqual(ready.revoked,['blob:test-0','blob:test-1']);

    const pending=deferred(); let signal,calls=0;
    const stale=harness((url,options)=>{calls++;signal=options.signal;return pending.promise;});
    const loading=stale.view.load(); await stale.view.load(); assert.equal(calls,1);
    stale.view.dispose(); assert.equal(signal.aborted,true);
    pending.resolve(ok()); await loading;
    assert.equal(stale.created.length,0,'late response must not create a player after switching event');

    const decoding=deferred(); const late=harness(async()=>ok(),()=>decoding.promise);
    const task=late.view.load();
    while (!late.contexts.length) await Promise.resolve();
    late.view.dispose();
    decoding.resolve({sampleRate:16000,numberOfChannels:1,getChannelData:()=>new Float32Array(1600)});
    await task;
    assert.equal(late.node('[data-audio-charts]').hidden,true);
    assert.deepEqual(late.revoked,['blob:test-0']);

    const bad=harness(async()=>({ok:false,json:async()=>({detail:'audio_object_missing'})}));
    await bad.view.load();
    assert.match(bad.node('[data-audio-status]').textContent,/找不到檔案/);
    assert.equal(bad.node('[data-audio-load]').disabled,false);
    const undecodable=harness(async()=>ok(),async()=>{throw new Error('invalid codec');});
    await undecodable.view.load();
    assert.match(undecodable.node('[data-audio-status]').textContent,/無法解碼/);
    assert.equal(undecodable.node('[data-audio-charts]').hidden,true);
    assert.equal(undecodable.node('[data-audio-player]').hidden,false);
    undecodable.view.dispose();
    console.log('Audio viewer: playback, decode failures, stale requests and resource cleanup passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
