(function (root) {
    'use strict';
    const FRESH_MS = 20000;
    const RECENT_EVENT_MS = 60000;
    function summarize(input) {
        const result = (tone, title, detail, action = 'nodes') => ({tone, title, detail, action});
        if (!input.loaded) return result('info', '正在確認系統狀態', '讀取節點與服務狀態中…', 'system');
        if (!input.backendConnected) return result('error', '無法確認監控狀態', '服務暫時無法連線；畫面可能保留先前資料。請檢查網路或重新整理。', 'system');
        if (!input.devicesAt || input.now - input.devicesAt > FRESH_MS || input.devicesFailed)
            return result('warn', '節點狀態尚未確認', '節點資料讀取失敗或已過期，不能判斷目前是否正在監聽。', 'system');
        if (!input.online) return result('warn', '尚未開始監控', '目前沒有節點在線。請開啟手機上的測試 APP，確認網路連線。');
        if (!input.listening) return result('warn', '節點已連線，尚未監聽', '前往節點頁確認運作模式，再開始監聽。');
        if (!input.wsConnected) return result('warn', '監聽中・即時更新重連中', `${input.listening} 台節點回報監聽中；事件暫以定期更新同步，可能延遲。`, 'system');
        return result('ok', '聲音監聽中', `${input.listening} 台節點回報監聽中。偵測結果請查看下方紀錄；沒有事件不代表周遭沒有聲音。`);
    }
    function eventRecency(timestamp, now) {
        const value = Number(timestamp);
        return Number.isFinite(value) && value > 0 && now >= value && now - value <= RECENT_EVENT_MS;
    }
    const api = Object.freeze({summarize, eventRecency, FRESH_MS, RECENT_EVENT_MS});
    if (typeof module !== 'undefined' && module.exports) module.exports = api;
    else root.DashboardStatus = api;
})(typeof window !== 'undefined' ? window : globalThis);
