(function (root) {
    'use strict';
    const number = value => typeof value === 'number' && Number.isFinite(value) ? value : null;
    const text = value => typeof value === 'string' && value.trim() ? value.trim() : null;
    function coordinates(lat, lng) {
        return number(lat) !== null && number(lng) !== null && Math.abs(lat) <= 90 && Math.abs(lng) <= 180
            ? `${lat.toFixed(6)}, ${lng.toFixed(6)}` : null;
    }
    function time(value) {
        if (!text(value)) return null;
        const milliseconds = Date.parse(value);
        return Number.isFinite(milliseconds) ? milliseconds : null;
    }
    function date(value) {
        const milliseconds = time(value);
        return milliseconds === null ? '未提供有效時間' : new Intl.DateTimeFormat('zh-TW', {
            year:'numeric', month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit', second:'2-digit', hour12:false
        }).format(milliseconds);
    }
    function measurement(value, unit) {
        return number(value) === null ? '未提供' : `${value} ${unit}`;
    }
    function summarize(payload, runtime = {}) {
        const event = payload.event || {};
        const group = payload.group || null;
        const reasons = [];
        if (group?.node_evidence_truncated) reasons.push('節點證據僅列出前 100 個節點，並非完整清單。');
        const first = time(group?.first_event_time);
        const last = time(group?.last_event_time);
        const ids = [...new Set([...(Array.isArray(group?.devices) ? group.devices : []),
            ...(Array.isArray(group?.reporting_device_ids) ? group.reporting_device_ids : [])].filter(text))];
        const raw = coordinates('raw_latitude' in event ? event.raw_latitude : event.latitude,
            'raw_longitude' in event ? event.raw_longitude : event.longitude);
        const fixed = coordinates(event.fixed_latitude, event.fixed_longitude);
        const region = coordinates(group?.region_center_lat, group?.region_center_lng);
        const estimate = coordinates(group?.estimated_lat, group?.estimated_lng);
        const method = text(group?.localization_method);
        if (!group) reasons.push('尚無事件融合關聯；可能尚在處理、未符合融合條件或為舊資料。');
        else {
            if (first === null || last === null) reasons.push('群組起訖時間不完整，無法計算觀測跨度。');
            else if (last < first) reasons.push('群組時間順序異常，無法計算觀測跨度。');
            if (ids.length < 2) reasons.push('不足兩個有識別碼的參與節點，缺少跨節點比對依據。');
            if (!region && !estimate) reasons.push('群組未提供有效區域中心或聲源估測座標。');
            if (method === 'multi_node_region') reasons.push('目前結果是節點涵蓋區域估測，並非精準聲源位置。');
        }
        if (!raw) reasons.push('事件未保留有效回報座標。');
        if (!event.classification) reasons.push('此事件缺少完整五類分類資料，無法呈現各類模型分數。');
        if (!text(event.time_sync_quality)) reasons.push('事件未提供時鐘同步品質。');
        if (number(event.gps_accuracy_m) === null || event.gps_accuracy_m < 0) reasons.push('事件未提供有效 GPS 誤差資料。');
        if (runtime.localization_enabled === false) reasons.push('服務目前未啟用精準定位；此狀態不代表事件當時設定。');
        if (!event.audio_path) reasons.push('事件未有錄音檔案紀錄。');
        if (runtime.gcs_configured === false) reasons.push('服務目前未配置音訊儲存，無法提供播放。');
        const source = {manual_map:'人工地圖設定', current_gps:'以 GPS 儲存的固定位置'}[event.fixed_location_source] || '來源未記錄';
        const relative = Array.isArray(group?.device_relative_times) ? group.device_relative_times : [];
        return {
            sections: [
                {title:'事件與觀測時間', rows:[
                    ['事件回報時間', date(event.timestamp)], ['後端建立時間', date(event.created_at)],
                    ['群組首次偵測', date(group?.first_event_time)], ['群組最後偵測', date(group?.last_event_time)],
                    ['群組更新時間', date(group?.updated_at)],
                    ['觀測跨度', first !== null && last !== null && last >= first ? `${((last-first)/1000).toFixed(1)} 秒` : '無法計算'],
                    ['錄音片段長度', number(event.duration_s) !== null && event.duration_s >= 0 ? `${event.duration_s} 秒` : '未提供']
                ], note:'時間依瀏覽器當地時區顯示。觀測跨度與片段長度均不代表目標持續存在。'},
                {title:'參與節點', rows:[['此事件回報節點', text(event.device_id) || '未提供'],
                    ['群組參與節點', ids.length ? ids.join('、') : '尚無節點清單'],
                    ['已列出節點數', String(ids.length)],
                    ...relative.map(item => [`${text(item.device_id) || '未識別節點'} 首次事件`,
                        `${date(item.event_timestamp)} · 相對 ${measurement(item.relative_time_ms, 'ms')}`])
                ], note:'相對事件時間不是精準聲波到達差。事件當時的節點健康狀態尚無快照。'},
                {title:'位置與來源', rows:[
                    ['事件當時回報座標', raw || '未提供有效座標'],
                    ['目前固定座標', fixed ? `${fixed}（${source}）` : '未設定'],
                    ['群組區域中心', region || '未提供有效座標'],
                    ['聲源估測座標', method && method !== 'multi_node_region' && estimate ? estimate : '未提供精準聲源位置'],
                    ['估測方法', method === 'multi_node_region' ? '節點涵蓋區域估測' : method || '未提供'],
                    ['事件 GPS 誤差', number(event.gps_accuracy_m) !== null && event.gps_accuracy_m >= 0 ? `${event.gps_accuracy_m} m` : '未提供']
                ], note:'回報座標與固定座標都是節點位置。固定位置為目前設定，區域中心為群組儲存結果，皆不能當成已驗證的聲源真實位置。'},
                {title:'事件時鐘診斷', rows:[['同步品質', text(event.time_sync_quality) || '未提供'],
                    ['同步偏移', measurement(event.time_sync_offset_ms, 'ms')],
                    ['往返延遲 RTT', measurement(event.time_sync_rtt_ms, 'ms')],
                    ['同步資料年齡', measurement(event.time_sync_age_ms, 'ms')]
                ], note:'這些是事件所帶的診斷值，並非實地校正通過證明。'}
                , ...((Array.isArray(group?.node_evidence) ? group.node_evidence : []).map(item => ({
                    title:`節點證據：${text(item.device_id) || '未識別節點'}`,
                    rows:[['參照事件', text(item.event_id) || '未提供'],
                        ['首次事件回報時間', date(item.event_timestamp)],
                        ['融合紀錄建立時間', date(item.created_at)],
                        ['融合時儲存的節點座標', coordinates(item.latitude, item.longitude) || '未提供'],
                        ['該次同步品質', text(item.time_sync_quality) || '未提供'],
                        ['該次同步偏移', measurement(item.time_sync_offset_ms, 'ms')],
                        ['該次往返延遲 RTT', measurement(item.time_sync_rtt_ms, 'ms')]],
                    note:'每節點選取群組內最早事件；建立時間不是網路接收時間。座標為融合紀錄快照，未保留 GPS／固定位置來源，不能當成聲源位置或目前節點健康狀態。'
                })))
            ],
            reasons,
            groupId: text(group?.id) || '尚無關聯',
            qualityNote:'模型分數與定位品質分開解讀；目前未提供經實地校正的綜合可信度百分比。'
        };
    }
    const api = {summarize};
    if (typeof module === 'object' && module.exports) module.exports = api;
    else root.DashboardEventContext = api;
})(typeof window === 'object' ? window : globalThis);
