# 事件詳情與資料品質摘要

後續錄音檢視已擴充為同來源 bytes、播放器及波形／聲譜，詳見 AUDIO_EVIDENCE.md；原有音訊簽名 URL API 仍保留。

新增唯讀 `GET /events/{event_id}/context`，從持久化的融合 observation 關聯查詢群組，獨立於最近 20 組列表。沒有以時間、節點或分類猜配事件；不修改 schema、融合政策、定位旗標或上傳流程。

成功回應：`status: success`、`event`、`group`、`association_status`。event 沿用 Dashboard 事件序列化；group 沿用融合群組摘要。group 為 null 時 association_status 為 `not_associated`，代表查詢時無關聯，不代表永遠無法融合。事件不存在回 404；讀取失敗回 503，不偽裝成無群組。

事件頁包含群組首次／最後偵測與更新時間、觀測跨度、錄音片段長度、參與節點及相對事件時間、位置來源、事件時鐘診斷，以及缺失原因。時間採瀏覽器當地時區。跨度與片段長度不等於目標持續存在。

`raw_latitude/raw_longitude` 保留事件回報位置，與讀取時的 `fixed_latitude/fixed_longitude` 分開。區域中心採群組保存值。節點座標、區域中心與聲源估測有不同語意，不展示未校正的綜合可信度百分比。Runtime 旗標描述目前服務狀態，不回推事件當時設定；目前節點健康資料不冒充歷史快照。

前端按選取事件取得 context，合併同一事件的進行中請求，15 秒內重用結果；隨既有 snapshot 更新再次檢查，另提供重新讀取。不同選取事件的遲到回應會被忽略。重新讀取失敗會顯示錯誤並移除舊摘要，防止把舊結果當成最新狀態。一般未變更事件重繪不重建音訊播放器；切換事件後的音訊 URL 遲到回應不插入另一個事件。

摘要函式在 `static/dashboard_event_context.js`，以資料產生段落；所有 API 字串由模板的 `safe` 函式轉義後輸出。展開／收合狀態在摘要更新時保留。事件時鐘診斷預設收合。

## 驗證

- `venv/Scripts/python.exe -m pytest -q`
- `node tests/js/test_dashboard_event_context.js`
- `node tests/js/test_dashboard_event_context_loading.js`
- 原有三套 `tests/js/test_dashboard_{status,simulation_prediction,location_picker}.js`

新增測試涵蓋：超出最近 20 組的歷史事件、無關聯與讀取失敗的區分、保留原始與目前固定座標、時間缺失／逆序、單節點、舊分類、合法零值、非法座標、切換事件競態、重複請求合併及重試。瀏覽器使用本機合成資料檢查桌面與手機寬度，不代表線上服務或實地定位驗收。
# 跨節點歷史證據補充（2026-09-10）

事件 context 的 group 新增 `node_evidence` 與 `node_evidence_truncated`。
每節點依 `event_timestamp, id` 選取最早的融合觀測，最多回傳 100 個節點，
超過時畫面明示截斷。回傳參照事件、事件時間、融合紀錄建立時間、儲存座標與同步診斷。
不套用目前固定位置。舊觀測未記錄座標來源，因此不宣稱是原始 GPS 或聲源座標。
`created_at` 是融合紀錄建立時間，並非網路接收時間；頁面不提供逐筆觀測瀏覽或歷史健康快照。
