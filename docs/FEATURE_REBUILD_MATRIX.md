# Feature rebuild matrix

此表用來選擇驗收範圍。Core 用新的 PostgreSQL 與合成節點可以驗證。地圖、音訊與公開部署有各自資源。

| Feature | Dependencies | Setup required | How to test | Required for baseline |
|---|---|---|---|---|
| PostgreSQL persistence | PostgreSQL 或 Supabase，psycopg2 | 空庫、16 檔 migration、runtime DSN | postcheck，SQL 比對 event／group／track | Core |
| V2 Dashboard／CSV | Backend、browser | `DASHBOARD_V2_ENABLED=true` | 總覽、事件、節點、track、CSV | Core |
| Node WS／Dashboard WS | 單 worker，browser 或 client | node WS 開，同一 host | hello_ack、heartbeat、ONLINE、Dashboard broadcast | Core |
| HTTP event ingest | DB、upload token、client | 新 token、三個必要欄位 | 200、db_id、SQL、重送同 ID、Dashboard | Core |
| AI classification result | v1 payload、migration v6_0 | 開 v1 flags | 檢查 DB metadata、分類顯示與 WS | Demo 分類展示；模型運行在 client |
| Event fusion | 兩個有效節點回報、融合視窗 | Drone label、有效座標、相近時間 | 查同一 group 與兩個 event IDs | Core |
| Region localization | 節點幾何、fusion | 不同位置、固定位置或事件座標 | 兩點 segment／三點 polygon | Core 粗略區域 |
| Tracking | group region、有效時間及 confidence | `TRACKING_ENABLED=true` | group-track endpoint 與 persisted points | Core |
| Operational map／protected site | Google Maps JavaScript API、browser referrer | 自建 Maps key，操作 browser local state | 底圖、固定節點、據點／警戒圈 | 完整地理底圖展示 |
| Audio Evidence | GCS、key JSON、bucket IAM、event | 啟用儲存，先寫 metadata | multipart、DB audio_path、read、signed GET、UI 播放 | 有音訊時的 Demo 展示 |
| Live audio／控制 | node command、audio WS 協定 | 對應 flags、實際 client | ACK／result、audio frame、monitor | 選用的運維／串流功能 |
| Simulation Lab | browser，V2／Simulation flags | 選預設情境 | 模擬地圖、truth、alert、reset、replay | Core 展示 |
| Kalman comparison | Simulation Lab、CV tracker | 同上 | 獨立 trail／點數、reset、Alpha-Beta ETA | Core 模擬比較 |
| Gateway test endpoint | HTTP、upload token | 任意 JSON object | `POST /api/test-gateway` 回同一 object，DB event count 不增 | 連通性展示 |
| 真實 Gateway adapter | 外部 MCU／Wi-SUN／Gateway | vendor 自己建節點、mapping、時鐘、ACK／retry | 以自身裝置送入正式 HTTP event，觀察重送與回復 | 外部整合，synthetic Core 可先驗收 |
| TDOA／GCC-PHAT prototype | 時間同步、有效 capture metadata、原型 code | 原型研究環境 | 合成 solver tests、另建實地驗證 | Research-only |
| HTTPS／WSS deployment | 自有 hosting、網路、PostgreSQL | 單 worker、TLS、WS Upgrade | 對自己的 host 重跑完整 applicable smoke | 雲端展示範圍 |

[從零重建](FROM_SCRATCH_SETUP.md) · [驗收表](SYSTEM_ACCEPTANCE_CHECKLIST.md)
