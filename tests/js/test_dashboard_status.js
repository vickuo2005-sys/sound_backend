const assert = require('node:assert/strict');
const {summarize, eventRecency} = require('../../static/dashboard_status.js');
const now = 1000000;
const ready = {loaded:true, backendConnected:true, devicesAt:now, now, online:2, listening:2, wsConnected:true};
assert.equal(summarize({...ready, loaded:false}).tone, 'info');
assert.equal(summarize({...ready, backendConnected:false}).tone, 'error');
for (const change of [{devicesAt:null}, {devicesAt:now-21000}, {devicesFailed:true}]) {
    assert.equal(summarize({...ready, ...change}).title, '節點狀態尚未確認');
}
assert.equal(summarize({...ready, online:0, listening:0}).title, '尚未開始監控');
assert.equal(summarize({...ready, listening:0}).title, '節點已連線，尚未監聽');
assert.equal(summarize({...ready, wsConnected:false}).tone, 'warn');
assert.equal(summarize(ready).title, '聲音監聽中');
assert.equal(eventRecency(now-59000, now), true);
for (const timestamp of [now-61000, now+1, null, undefined, NaN, 0]) {
    assert.equal(eventRecency(timestamp, now), false);
}
console.log('Dashboard status scenarios passed');
