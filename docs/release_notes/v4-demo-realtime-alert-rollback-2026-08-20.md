# DEMO 即時警示穩定版回退紀錄（2026-08-20）

## 決策

Dashboard 的即時節點警示回退為歸檔版的「事件抵達即顯示」模式，並加上一項安全邊界：只有 WebSocket `event_trigger` 可以啟動節點警示。融合群組與 REST 定時更新只能更新資料和估測，不得重新啟動或提前清除警示。

回退前版本已保留在 Git 提交 `d700dfe`，runtime marker 為 `archive-stable-ordered-alerts-v10`。本次 DEMO 基線 marker 為 `archived-dashboard-alert-flow-v11`。

## 已確認的現象

2026-08-20 14:02–14:03 的測試中，後端持續收到 14 筆 `node_A01`–`node_A04` 事件。事件抵達延遲約 -1.9 至 20.5 秒，全部通過 30 秒准入條件；六個節點 WebSocket 也保持連線。因此「只有第一個警示、後續不顯示」不是手機沒有送出，也不是 FastAPI 沒有收到，而是 Dashboard 顯示狀態退化。

回退前 Dashboard 同時由以下入口修改警示狀態：

1. WebSocket `event_trigger`。
2. WebSocket `event_group`。
3. 每 30 秒 REST `/events` 與 `/event-groups` 更新。
4. 節點 heartbeat / status 合併。
5. 全域 occurrence watermark 與批次淘汰。

同一個 `alertUntil` 被多條非同步路徑更新，導致後續合法事件可能被舊群組、狀態同步或時間浮水位覆寫。

## DEMO 資料流

1. Flutter 每 1.5 秒推進一次 3 秒音訊窗並執行分類。
2. 偵測事件以 HTTP 上傳至 FastAPI，包含裝置事件時間、RMS peak 時間、節點 ID 與定位資料。
3. FastAPI 寫入事件；固定節點顯示位置使用後端的 effective/fixed location。
4. 事件在 30 秒准入範圍內時，後端送出 WebSocket `event_trigger`。
5. Dashboard 收到 `event_trigger` 後，從「瀏覽器實際收到的時間」開始顯示完整 8 秒。
6. heartbeat、REST refresh 與融合群組不重啟警示；它們只更新節點資訊、歷史事件、估測與追蹤。

## 保留項目

- 固定節點位置與事件 marker 鎖定。
- 原始手機 GPS 留存。
- 30 秒後端舊事件准入判定。
- 8 秒 Dashboard 警示顯示。
- Flutter 1.5 秒重疊推論設定。
- 追蹤同時間去重、速度上限與異常座標過濾。
- 事件資料庫、融合、定位與歷史追蹤資料。

## 回退項目

- Dashboard 全域警示時間浮水位。
- Dashboard 批次容差與舊批次淘汰狀態機。
- REST `/events` 自動重建警示。
- 融合群組重新啟動節點警示。
- 以目前 `is_listening` 狀態決定已收到事件是否顯示。

## DEMO 驗收

1. 開啟 Dashboard 並強制重新整理。
2. 啟動指定節點監聽，觸發至少三輪事件。
3. 每一輪後端接受的事件都應讓對應固定節點顯示 8 秒。
4. 關閉監聽不應讓已開始的 8 秒警示提前消失。
5. 融合或 REST 更新不應讓已結束的舊節點警示重新出現。
6. `/runtime-status` 應回報 `archived-dashboard-alert-flow-v11`，且六個展示節點保持 WebSocket 連線。

## 後續改善邊界

若 DEMO 後重新加入跨節點排序，只能在 `event_trigger` 單一路徑內實作，且必須以錄製的亂序事件序列進行瀏覽器層回放測試。不得再讓 REST、融合群組和 heartbeat 共同寫入警示生命週期。
