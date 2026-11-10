# 重建完成驗收表

對自己的新環境逐項保存結果、source SHA、Python／套件版本、PostgreSQL 版本及驗收時間。Core 全通過可標記 **Core 等價**。若目標包含完整 Demo 地圖、音訊與部署，對應項目也須完成。每個 check 都應能指出 API、DB 或 UI 證據。

## Core

- [ ] `GET /health` 200，啟動 logs 無 schema init error。
- [ ] `/runtime-status.database=postgres`，版本／flags 符合預期。
- [ ] PostgreSQL postcheck 與 12 tables、分類欄位及關鍵索引通過。
- [ ] `/events`、`/tracks`、`/event-groups`、`/device-status`、`/device-locations` 200 且 JSON 非 degraded。
- [ ] Dashboard V2 開啟，可進總覽、事件、節點及位置與軌跡頁。
- [ ] `/ws/dashboard` 握手並接到自己節點的 heartbeat。
- [ ] `/ws/node/node_A01` 連線，收到相符 `hello_ack`。
- [ ] 心跳可見，節點顯示 ONLINE。可選驗證逾時與 reconnect。
- [ ] `POST /events` 接受 event，回同一 `event_id` 與 `db_id`。
- [ ] SQL 與 GET 查到同一 event ID。Dashboard 事件列可依節點、時間與 label 對應。測試 client 保留同一 ID 重送，DB 仍一列。
- [ ] 兩個真正在本測試送入的 event IDs 出現在同一個多節點 group，具有 segment／polygon 區域與有效座標。
- [ ] `/event-groups/{group_id}/tracks` 可查本群組的 track，track points 非空。
- [ ] 分類 profile 啟用時，用完整 v1 payload 檢查 DB 分類欄位及 Dashboard 顯示。
- [ ] 若展示 Gateway 連通性，對自己的 `/api/test-gateway` 測合法 echo 與錯 token，echo 不會新增 DB event。

操作見 [DB](DATABASE_SETUP.md)、[Node](FIRST_NODE_GUIDE.md)、[Event](FIRST_EVENT_GUIDE.md) 與 [API Contract](API_CONTRACT.md)。

## Simulation

- [ ] 進入標示為模擬／非實地驗證的 Simulation Lab。
- [ ] 用既有接近警戒情境驗證載入、Start、Pause／Resume、場景切換。
- [ ] Ground Truth、Alpha-Beta、Kalman CV 各有軌跡，點數與誤差合理。
- [ ] Reset／Clear 後 Kalman state／trail 清除，再跑不殘留前輪；場景不寫正式 event。
- [ ] ETA／Alert／Approach 的演算法來源仍是 Alpha-Beta。Kalman CV 只作比較。

## 選用功能與部署

- [ ] 若驗收地理底圖，用自己的 Maps key，核對底圖、固定節點與選點／referrer。
- [ ] 若驗收 Audio Evidence，以有效 MP3／WAV 測上傳、DB metadata、`/audio-content`、signed GET 和 UI 播放。
- [ ] 若驗收 live audio 或控制，使用獨立節點與當前協定測命令 ACK／result、stream frame／monitor。
- [ ] 若驗收雲端，以自己的 HTTPS host 重跑 HTTP smoke 與兩種 WSS，核對 hosting worker／port、DB TLS、logs 和 reconnect。

[Storage／Maps](STORAGE_SETUP.md) · [新部署](DEPLOY_FROM_SCRATCH.md)

## Research-only

- [ ] 記錄 `LOCALIZATION_ENABLED=false` 的 Demo 設定，確認研究原型獨立驗收。
- [ ] TDOA／GCC-PHAT／同步、Kalman 場域、實際定位、prediction 與 ETA 的 field validation 另按研究計畫執行。Simulation 或此表 Core 通過不能替代場域資料。

[研究範圍](RESEARCH_STATUS.md) · [本次重建證據](REBUILD_VALIDATION.md)
