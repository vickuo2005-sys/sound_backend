const assert = require('node:assert/strict');
const {summarize} = require('../../static/dashboard_event_context.js');
const rows = summary => Object.fromEntries(summary.sections.flatMap(section => section.rows));
const payload = {
    event: {event_id:'old-event', device_id:'A01', timestamp:'2026-09-01T00:00:00Z',
        created_at:'2026-09-01T00:00:05Z', duration_s:3,
        raw_latitude:25, raw_longitude:121, fixed_latitude:26, fixed_longitude:122,
        fixed_location_source:'manual_map', classification:{confidence:0.99}, audio_path:'evidence.mp3'},
    group: {id:'old-group', devices:['A01','A02','A01'], reporting_device_ids:['A02'],
        first_event_time:'2026-09-01T00:00:00Z', last_event_time:'2026-09-01T00:00:10Z',
        localization_method:'multi_node_region', region_center_lat:25.5, region_center_lng:121.5,
        estimated_lat:25.5, estimated_lng:121.5, confidence:null,
        device_relative_times:[{device_id:'A02',event_timestamp:'2026-09-01T00:00:01Z',relative_time_ms:1000}]}
};
let summary = summarize(payload, {localization_enabled:false, gcs_configured:false});
let values = rows(summary);
assert.equal(values['觀測跨度'], '10.0 秒');
assert.equal(values['錄音片段長度'], '3 秒');
assert.equal(values['已列出節點數'], '2');
assert.equal(values['群組參與節點'], 'A01、A02');
assert.equal(values['事件當時回報座標'], '25.000000, 121.000000');
assert.match(values['目前固定座標'], /^26.000000, 122.000000/);
assert.equal(values['聲源估測座標'], '未提供精準聲源位置');
assert(summary.reasons.some(value => value.includes('並非精準聲源位置')));
assert(!JSON.stringify(summary).includes('99%'));
assert(summary.reasons.some(value => value.includes('音訊儲存')));

summary = summarize({event:{latitude:25, longitude:121, raw_latitude:null, raw_longitude:null}});
values = rows(summary);
assert.equal(values['事件當時回報座標'], '未提供有效座標');
assert.equal(values['觀測跨度'], '無法計算');
assert.equal(summary.groupId, '尚無關聯');
assert(summary.reasons.some(value => value.includes('尚無事件融合關聯')));
assert(summary.reasons.some(value => value.includes('完整五類分類資料')));

const malformed = structuredClone(payload);
malformed.group.last_event_time = '2026-08-01T00:00:00Z';
malformed.group.devices = ['A01']; malformed.group.reporting_device_ids = [];
malformed.event.raw_latitude = 91; malformed.event.fixed_latitude = NaN;
summary = summarize(malformed);
assert.equal(rows(summary)['觀測跨度'], '無法計算');
assert.equal(rows(summary)['目前固定座標'], '未設定');
assert(summary.reasons.some(value => value.includes('時間順序異常')));
assert(summary.reasons.some(value => value.includes('不足兩個')));
malformed.group.first_event_time = null;
assert(summarize(malformed).reasons.some(value => value.includes('起訖時間不完整')));

const zero = summarize({event:{raw_latitude:0,raw_longitude:0,gps_accuracy_m:0,time_sync_offset_ms:0,time_sync_rtt_ms:0},
    group:{first_event_time:'2026-01-01T00:00:00Z',last_event_time:'2026-01-01T00:00:00Z'}});
assert.equal(rows(zero)['事件當時回報座標'],'0.000000, 0.000000');
assert.equal(rows(zero)['觀測跨度'],'0.0 秒');
assert.equal(rows(zero)['同步偏移'],'0 ms');
assert.equal(rows(zero)['事件 GPS 誤差'],'0 m');
console.log('Event context: historical times, coordinate provenance and missing-data semantics passed');

const peers = summarize({event:{},group:{node_evidence:[{device_id:'A02',event_id:'old-peer',
    event_timestamp:'2026-09-01T00:00:00Z',created_at:'2026-09-01T00:00:02Z',
    latitude:0,longitude:0,time_sync_offset_ms:0,time_sync_rtt_ms:5}],node_evidence_truncated:true}});
const peer = peers.sections.find(section => section.title === '節點證據：A02');
assert.equal(Object.fromEntries(peer.rows)['參照事件'], 'old-peer');
assert.equal(Object.fromEntries(peer.rows)['融合時儲存的節點座標'], '0.000000, 0.000000');
assert.match(peer.note, /不是網路接收時間/);
assert(peers.reasons.some(reason => reason.includes('前 100 個節點')));
