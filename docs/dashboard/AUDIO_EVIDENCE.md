# 錄音證據、波形與聲譜

事件詳情新增「載入錄音與分析」。只有使用者點擊才讀取錄音，不自動播放。檔案最多 8 MiB；解碼後 30 秒內錄音產生波形及聲譜，較長片段保留播放器並說明圖表限制。支援格式依瀏覽器解碼器，預期使用既有 WAV／MP3；本次瀏覽器實測音檔為 WAV。

## 讀取契約

`GET /events/{event_id}/audio-content` 依既有事件的 audio_path 讀取已配置 GCS bucket，不接受外部 URL 或任意物件路徑。事件讀取與權限範圍沿用既有音訊 API；沒有修改憑證、bucket CORS、上傳或資料庫 schema。

取得物件大小與 generation 後檢查上限，再以 generation precondition、明確 byte range 和 raw download 讀取，防止讀到中途替換的版本或透明解壓擴張。完成後再核對 bytes 長度。中繼資料與下載分別有 10／20 秒 timeout 且不自動重試。回應禁止快取及 MIME sniffing。

主要錯誤：事件不存在／未上傳／物件不存在為 404；物件變更為 409；超過大小上限為 413；空檔為 422；不完整內容為 502；儲存或事件查詢暫不可用為 503。前端顯示對應中文原因，不暴露 SDK／憑證錯誤內容。

既有 `/audio-url` 簽名連結仍保留；新檢視器從同來源取得 bytes，避免 Canvas 分析依賴 GCS CORS。

## 圖表語意

- 優先使用 OfflineAudioContext 解碼，不要求麥克風權限或音訊輸出裝置。顯示的是解碼取樣率，可能因瀏覽器重取樣而不同於原始檔案。
- 波形以每個時間區段的最小／最大振幅呈現，縱向 −1 至 +1。
- 聲譜使用 Hann window 與 1024 點 FFT，最多 160 個時間窗。時間窗均勻覆蓋錄音，但不是無遺漏的瞬態事件分析。
- 聲譜顯示 0 至 min(8 kHz, 解碼 Nyquist)，頻率由下往上；色階為 −80 至 0 dBFS。頻率縮圖採區段最大值，避免細窄頻率峰在縮圖時消失。
- 僅分析第 1 聲道；dBFS 不是校準聲壓，不代表模型分類、定位可信度或跨節點到達差。

## 資源與更新

同一檢視器合併進行中載入；前端讀取有 35 秒界限。切換事件會 abort 舊請求、清除播放器來源並 revoke object URL。遲到的 fetch／decode 結果不會重新插入已離開的事件。重載也會釋放舊來源；解碼不支援或失敗時保留可供嘗試的播放器但不生成假圖。

錄音檢視器獨立於事件摘要重繪；只有事件 ID、音訊路徑／格式或可用狀態改變時重建，避免一般事件 metadata 更新打斷播放。

## 驗證

- `venv/Scripts/python.exe -m pytest -q`
- 原有五套 Dashboard JavaScript 測試。
- `node tests/js/test_dashboard_audio_analysis.js`
- `node tests/js/test_dashboard_audio_viewer.js`

新增 API 測試涵蓋 generation／range、大小與空檔、內容不完整、儲存錯誤與禁止任意 URL；分析測試以已知 1 kHz／3 kHz 訊號檢查頻率、dBFS、時間順序及靜音。檢視器測試涵蓋重試、decode 失敗、切換事件、URL 回收與請求合併。本機瀏覽器驗證 2 秒合成 WAV 及 390px 圖表排版。

本次沒有部署或配置 GCS；真實雲端 MP3／WAV 讀取、手機產生的錄音、原始取樣時序與現場精度仍須另外驗證。
