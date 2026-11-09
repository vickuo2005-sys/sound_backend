# Environment variable reference

本表從固定 source 的 `main.py`、`app/`、`services/` 與 `tools/` 掃描 `os.getenv`、`os.environ.get`、索引及動態讀取。下方 **103 個 runtime 變數**另加 tooling／hosting 專用項。來源欄連到主要讀取點，重複讀取合在同一列。範例用自己配置的值替換尖括號。一般 boolean 以 `true` 啟用，數字須可被對應的 int／float 解析。source 的下限和 conditional gate 依連結為準。

核心重建請使用 [從零重建](FROM_SCRATCH_SETUP.md) 的 profile。啟用音訊／地理底圖時加入 [Storage Setup](STORAGE_SETUP.md) 的設定。環境值由 terminal／process／secret store 注入，這些啟動命令沒有 dotenv loader。Render metadata 缺失時用 Git 或 image metadata 核對。

## Core

| Variable | Required? | Component | 用途 | Safe example | Source default | 本機／部署 | 失敗／停用行為 |
|---|---|---|---|---|---|---|---|
| `APP_ENV` | 建議顯式設定 | [main.py](../main.py#L110) | 環境標籤及 staging 路徑的開關 | `development` | `空字串，V2 renderer 缺省顯示 STAGING` | 本機 development，部署 DEMO，隔離診斷才用 staging | 值不符 staging 時 staging 專屬診斷與 freeze 不生效 |
| `UPLOAD_TOKEN` | HTTP ingest 必要 | [main.py](../main.py#L8353) | 驗證 events、位置更新、音訊上傳、Gateway echo | `<YOUR_UPLOAD_TOKEN>` | `原始碼的開發 fallback，顯式空值走 503` | 兩者都用自己產生的 token | 缺或錯 token 回 401，設定空值可回 503 |
| `FAST_EVENT_INGEST_ENABLED` | 選用 | [main.py](../main.py#L380) | 事件初始快速持久化路徑 | `true` | `true` | 本機／部署皆可使用預設 | 停用後走既有非快速處理 |
| `POST_INGEST_WORKERS` | 選用 | [main.py](../main.py#L438) | post-ingest 背景 worker 數 | `2` | `2` | 本機／部署皆可使用預設 | 解析錯誤可阻止 app 啟動 |
| `DEVICE_STATUS_WORKERS` | 選用 | [main.py](../main.py#L439) | 裝置狀態背景 worker 數 | `1` | `1` | 本機／部署皆可使用預設 | 解析錯誤可阻止 app 啟動 |
| `EVENT_FUSION_WINDOW_SECONDS` | 選用 | [main.py](../main.py#L241) | 事件融合基準視窗秒數 | `10` | `10` | 本機／部署皆可使用預設 | 解析錯誤可阻止 app 啟動 |

## Database

| Variable | Required? | Component | 用途 | Safe example | Source default | 本機／部署 | 失敗／停用行為 |
|---|---|---|---|---|---|---|---|
| `DATABASE_URL` | PostgreSQL 必要 | [main.py](../main.py#L1175) | psycopg2 DB DSN，URL encode 特殊字元 | `postgresql://<USER>:<PASSWORD>@<HOST>:<PORT>/<DATABASE>?sslmode=require` | `空值使用 SQLite，缺 sslmode 補 require` | 獨立本機可用 sslmode=disable，部署依 provider TLS | 無法連線時 Postgres 讀寫失敗，部分 GET 回 degraded |
| `POSTGRES_SCHEMA_AUTO_INIT` | 選用 | [main.py](../main.py#L239) | import main 時執行 PostgreSQL 內建 DDL | `false` | `false` | 兩者都用顯式 migration | 設 true 時 DDL 權限不足可記初始化錯誤，health 仍可能 200 |
| `POSTGRES_POOL_MIN` | 選用 | [main.py](../main.py#L1268) | 最小連線池大小 | `1` | `1` | 本機／部署皆可使用預設 | 格式錯可造成 pool 或 runtime status 失敗 |
| `POSTGRES_POOL_MAX` | 選用 | [main.py](../main.py#L1269) | 最大連線池大小 | `20` | `20` | 本機／部署皆可使用預設 | 格式錯可造成 pool 或 runtime status 失敗 |
| `POSTGRES_CONNECT_TIMEOUT_SECONDS` | 選用 | [main.py](../main.py#L1270) | PG 連線與 staging probe timeout 秒數 | `10` | `10` | 本機／部署皆可使用預設 | 格式錯或連線過慢時 DB 連線失敗 |
| `POSTGRES_POOL_ACQUIRE_TIMEOUT_SECONDS` | 選用 | [main.py](../main.py#L433) | 等待 pool slot 的上限秒數 | `5` | `5` | 本機／部署皆可使用預設 | 解析錯誤可阻止 app 啟動 |
| `POSTGRES_SCHEMA_CACHE_TTL_SECONDS` | 選用 | [main.py](../main.py#L429) | PostgreSQL schema introspection cache 秒數 | `300` | `300` | 本機／部署皆可使用預設 | 解析錯誤可阻止 app 啟動 |

## Storage

| Variable | Required? | Component | 用途 | Safe example | Source default | 本機／部署 | 失敗／停用行為 |
|---|---|---|---|---|---|---|---|
| `GCS_BUCKET_NAME` | 音訊必要 | [main.py](../main.py#L9363) | 私有 bucket 純名稱 | `<YOUR_GCS_BUCKET>` | `未設` | Core 可留空，音訊兩環境皆用自己的 bucket | 缺值時 GCS 存取失敗 |
| `GOOGLE_APPLICATION_CREDENTIALS_JSON` | 音訊必要 | [main.py](../main.py#L9364) | service account key JSON 全文 | `<YOUR_SERVICE_ACCOUNT_JSON>` | `未設` | Core 可留空，音訊由 secret store 注入 | 缺值或 JSON 錯誤時 GCS 存取失敗 |
| `GCS_UPLOAD_RETRY_ATTEMPTS` | 選用 | [main.py](../main.py#L442) | GCS 上傳嘗試次數 | `3` | `3` | 本機／部署皆可使用預設 | 解析錯誤可阻止 app 啟動 |
| `GCS_UPLOAD_RETRY_BACKOFF_SECONDS` | 選用 | [main.py](../main.py#L446) | GCS 上傳重試基準延遲秒數 | `0.5` | `0.5` | 本機／部署皆可使用預設 | 解析錯誤可阻止 app 啟動 |
| `GCS_UPLOAD_TIMEOUT_SECONDS` | 選用 | [main.py](../main.py#L450) | GCS 單次上傳 timeout 秒數 | `60` | `60` | 本機／部署皆可使用預設 | 解析錯誤可阻止 app 啟動 |

## Dashboard

| Variable | Required? | Component | 用途 | Safe example | Source default | 本機／部署 | 失敗／停用行為 |
|---|---|---|---|---|---|---|---|
| `DASHBOARD_V2_ENABLED` | Core profile 必要 | [main.py](../main.py#L405) | 選擇 V2 renderer | `true` | `false` | 本機／部署均採範例 | false 會呈現 legacy fallback |
| `DEMO_STABLE_MODE` | Demo profile | [main.py](../main.py#L413) | 正式展示樣式與 experimental motion 抑制 | `true` | `true` | 本機／部署均採範例 | false 改用非 Demo 呈現 |
| `GOOGLE_MAPS_API_KEY` | 地理底圖必要 | [main.py](../main.py#L12020) | Maps JavaScript browser key | `<YOUR_MAPS_API_KEY>` | `空值` | 各 host 設自己的 API／referrer 限制 | 未設或載入失敗顯示座標示意 |
| `DASHBOARD_ADMIN_TOKEN` | 啟用寫入驗證時建議 | [main.py](../main.py#L8372) | Dashboard mutation 授權 | `<YOUR_DASHBOARD_ADMIN_TOKEN>` | `未設時可用 UPLOAD_TOKEN 或程式 fallback` | 本機測試可留空，部署用獨立新 token | 缺或錯請求 token 在驗證開啟時回 401 |
| `DASHBOARD_WRITE_TOKEN_REQUIRED` | 部署寫入政策 | [main.py](../main.py#L8367) | 啟用 Dashboard mutation token 檢查 | `true` | `false` | 隔離本機可 false，部署建議 true | 開啟後缺 token 拒絕寫入，現有舊 staging 位置例外由服務識別判斷 |
| `DASHBOARD_EVENT_ORDER_GUARD_ENABLED` | 選用 | [main.py](../main.py#L426) | Dashboard 新舊事件排序保護 | `true` | `true` | 本機／部署皆可使用預設 | false 省略順序防護 |
| `DASHBOARD_BROADCAST_TIMEOUT_SECONDS` | 選用 | [main.py](../main.py#L436) | Dashboard WebSocket 廣播 timeout 秒數 | `1.5` | `1.5` | 本機／部署皆可使用預設 | 解析錯誤可阻止 app 啟動 |
| `DEVICE_STATUS_CACHE_TTL_SECONDS` | 選用 | [main.py](../main.py#L373) | 裝置狀態 cache 秒數 | `10` | `10` | 本機／部署皆可使用預設 | 解析錯誤可阻止 app 啟動 |
| `DEVICE_FIXED_LOCATION_CACHE_TTL_SECONDS` | 選用 | [main.py](../main.py#L377) | 固定位置 cache 秒數 | `60` | `60` | 本機／部署皆可使用預設 | 解析錯誤可阻止 app 啟動 |

## Realtime / WebSocket

| Variable | Required? | Component | 用途 | Safe example | Source default | 本機／部署 | 失敗／停用行為 |
|---|---|---|---|---|---|---|---|
| `NODE_WEBSOCKET_ENABLED` | Core profile 必要 | [main.py](../main.py#L343) | 啟用節點 hello、heartbeat 與控制 | `true` | `true` | 本機／部署均採範例 | false 拒絕 node WS |
| `COMMAND_WEBSOCKET_ENABLED` | 選用 | [main.py](../main.py#L365) | 啟用命令 WebSocket 投遞 | `true` | `true` | 本機／部署皆可使用預設 | false 時不走 WSS 命令投遞 |
| `NODE_HEARTBEAT_INTERVAL_SECONDS` | 選用 | [main.py](../main.py#L345) | hello_ack 建議 client 心跳秒數 | `5` | `5` | 本機／部署皆可使用預設 | 解析錯誤可阻止 app 啟動 |
| `NODE_DEGRADED_TIMEOUT_SECONDS` | 選用 | [main.py](../main.py#L348) | 心跳進 DEGRADED 的界線秒數 | `10` | `10` | 本機／部署皆可使用預設 | 解析錯誤可阻止 app 啟動 |
| `NODE_OFFLINE_TIMEOUT_SECONDS` | 選用 | [main.py](../main.py#L351) | 心跳進 OFFLINE 的界線秒數 | `20` | `20` | 本機／部署皆可使用預設 | 解析錯誤可阻止 app 啟動 |
| `NODE_ALERT_HOLD_SECONDS` | 選用 | [main.py](../main.py#L353) | 節點警示保持秒數 | `15` | `15` | 本機／部署皆可使用預設 | 解析錯誤可阻止 app 啟動 |
| `NODE_ALERT_MAX_LATENESS_SECONDS` | 選用 | [main.py](../main.py#L355) | live alert 可接受事件延遲秒數 | `30` | `30` | 本機／部署皆可使用預設 | 解析錯誤可阻止 app 啟動 |
| `LIVE_ALERT_REGION_WINDOW_SECONDS` | 選用 | [main.py](../main.py#L361) | 即時警示區域節點時間範圍秒數 | `60` | `跟 TRACK_REGION_MEMORY_SECONDS` | 本機／部署皆可使用預設 | 解析錯誤可阻止 app 啟動 |
| `LIVE_AUDIO_ENABLED` | 選用 | [main.py](../main.py#L367) | binary audio streams | `true` | `true` | 本機／部署皆可使用預設 | false 關閉 live audio，事件 evidence 仍由 GCS 管理 |
| `LIVE_AUDIO_RING_BUFFER_SECONDS` | 選用 | [main.py](../main.py#L369) | 即時音訊記憶體緩衝秒數 | `10` | `10` | 本機／部署皆可使用預設 | 解析錯誤可阻止 app 啟動 |
| `LIVE_AUDIO_MAX_FRAME_BYTES` | 選用 | [main.py](../main.py#L371) | 即時音訊最大 frame bytes | `65536` | `65536` | 本機／部署皆可使用預設 | 解析錯誤可阻止 app 啟動 |
| `LIVE_AUDIO_DEFAULT_CODEC` | 選用 | [main.py](../main.py#L11396) | 發出 start live audio 命令時的預設 codec | `pcm_s16le` | `pcm_s16le` | 本機／部署皆可使用預設 | 無效 codec 會影響音訊協定相容性 |

## Classification

| Variable | Required? | Component | 用途 | Safe example | Source default | 本機／部署 | 失敗／停用行為 |
|---|---|---|---|---|---|---|---|
| `CLASSIFICATION_V1_ENABLED` | 分類 profile | [main.py](../main.py#L389) | 開啟 v1 metadata 回應能力 | `true` | `false` | 重建分類展示時設 true | 未開啟時不完整呈現 v1 metadata |
| `CLASSIFICATION_V1_PERSISTENCE_ENABLED` | 分類寫入需要 | [main.py](../main.py#L392) | 寫入 v1 欄位 | `true` | `跟 CLASSIFICATION_V1_ENABLED` | 先執行 v6_0 migration | 欄位未安裝時無法驗收分類持久化 |
| `CLASSIFICATION_V1_WEBSOCKET_ENABLED` | 分類即時需要 | [main.py](../main.py#L399) | 將分類 metadata 加到即時通知 | `true` | `跟 CLASSIFICATION_V1_ENABLED` | 本機／部署均採範例 | false 不附即時分類資料 |

## Simulation

| Variable | Required? | Component | 用途 | Safe example | Source default | 本機／部署 | 失敗／停用行為 |
|---|---|---|---|---|---|---|---|
| `DASHBOARD_SIMULATION_ENABLED` | Core profile 必要 | [main.py](../main.py#L411) | 注入 Simulation Lab、比較軌跡及獨立 UI | `true` | `false` | 本機／部署均採範例 | false 時不提供 Simulation workspace |

## Tracking

| Variable | Required? | Component | 用途 | Safe example | Source default | 本機／部署 | 失敗／停用行為 |
|---|---|---|---|---|---|---|---|
| `TRACKING_ENABLED` | Core profile 必要 | [main.py](../main.py#L254) | 啟用 backend tracking | `true` | `true` | 本機／部署均採範例 | false 時不產生新的 tracks |
| `TRACKS_CACHE_TTL_SECONDS` | 選用 | [main.py](../main.py#L375) | 軌跡列表 cache 秒數 | `10` | `10` | 本機／部署皆可使用預設 | 解析錯誤可阻止 app 啟動 |
| `TRACK_MAX_GAP_SECONDS` | 選用 | [main.py](../main.py#L333) | 同軌跡關聯最大時間差秒數 | `180` | `180` | 本機／部署皆可使用預設 | 解析錯誤可阻止 app 啟動 |
| `TRACK_CLOSE_AFTER_SECONDS` | 選用 | [main.py](../main.py#L335) | stale track 關閉秒數 | `240` | `max(TRACK_MAX_GAP_SECONDS, 240)` | 本機／部署皆可使用預設 | 解析錯誤可阻止 app 啟動 |
| `TRACK_MAX_SPEED_MPS` | 選用 | [main.py](../main.py#L338) | 軌跡 gate 的速度上限 m/s | `80` | `80` | 本機／部署皆可使用預設 | 解析錯誤可阻止 app 啟動 |
| `TRACK_BASE_GATE_METERS` | 選用 | [main.py](../main.py#L339) | 關聯與 innovation gate 基準公尺 | `100` | `100` | 本機／部署皆可使用預設 | 解析錯誤可阻止 app 啟動 |
| `TRACK_MIN_CONFIDENCE` | 選用 | [main.py](../main.py#L340) | track measurement confidence 下限 | `0.25` | `0.25` | 本機／部署皆可使用預設 | 解析錯誤可阻止 app 啟動 |
| `TRACK_MIN_REGION_NODES` | 選用 | [main.py](../main.py#L341) | 進 region tracking 的最少節點數 | `2` | `2` | 本機／部署皆可使用預設 | 解析錯誤可阻止 app 啟動 |
| `TRACK_REGION_MEMORY_SECONDS` | 選用 | [main.py](../main.py#L358) | 區域 tracking 記住節點的秒數 | `60` | `60` | 本機／部署皆可使用預設 | 解析錯誤可阻止 app 啟動 |
| `TRACK_ALLOW_FALLBACK` | 選用 | [main.py](../main.py#L342) | 允許 fallback 定位結果送追蹤 | `false` | `false` | 本機／部署皆可使用預設 | true 時可能納入低品質 fallback 量測 |
| `TRACKING_REORDER_BUFFER_ENABLED` | 選用 | [main.py](../main.py#L323) | 開啟 track observation reorder buffer | `false` | `false` | 本機／部署皆可使用預設 | false 直接處理，不使用重排緩衝 |
| `TRACKING_REORDER_WINDOW_MS` | 選用 | [main.py](../main.py#L327) | 重排 buffer 視窗毫秒 | `500` | `500` | 本機／部署皆可使用預設 | 解析錯誤可阻止 app 啟動 |

## Diagnostics

| Variable | Required? | Component | 用途 | Safe example | Source default | 本機／部署 | 失敗／停用行為 |
|---|---|---|---|---|---|---|---|
| `POST_INFERENCE_LATENCY_TRACING_ENABLED` | 選用 | [main.py](../main.py#L383) | 事件路徑 latency trace／Server-Timing | `true` | `true` | 本機／部署皆可使用預設 | false 省略相關 timing |
| `RENDER_GIT_COMMIT` | 平台 metadata | [main.py](../main.py#L768) | Render 注入 build SHA | `<COMMIT_SHA>` | `未設` | 本機缺省，平台自動提供 | 缺值時 runtime 無 SHA metadata |
| `RENDER_GIT_BRANCH` | 平台 metadata | [main.py](../main.py#L769) | Render 注入 branch | `rebuild-demo` | `未設` | 本機缺省，平台自動提供 | 缺值時 runtime 無 branch metadata |
| `RENDER_SERVICE_ID` | 平台 metadata | [main.py](../main.py#L771) | Render 注入 ID，用於 runtime 與既有 staging 判斷 | `<YOUR_SERVICE_ID>` | `未設` | 本機缺省，平台自動提供 | 缺值用一般寫入政策 |
| `RENDER_SERVICE_NAME` | 平台 metadata | [main.py](../main.py#L770) | Render 注入服務名稱 | `sound-rebuild` | `未設` | 本機缺省，平台自動提供 | 缺值用一般寫入政策 |

## Staging-only

| Variable | Required? | Component | 用途 | Safe example | Source default | 本機／部署 | 失敗／停用行為 |
|---|---|---|---|---|---|---|---|
| `CRITICAL_PATH_DIAGNOSTICS_ENABLED` | 選用 | [main.py](../main.py#L10625) | staging critical path trace | `true` | `true` | 本機／部署皆可使用預設 | 只有 APP_ENV=staging 且啟用才追蹤 |
| `STAGING_WRITE_FREEZE` | 選用 | [main.py](../main.py#L112) | 隔離 staging 封鎖受管寫入 | `false` | `false` | 本機／部署皆可使用預設 | 啟用時相關寫入回 503 |
| `STAGING_DB_LATENCY_PROBE_ENABLED` | 選用 | [main.py](../main.py#L386) | 隔離 staging 的 DB latency probe | `false` | `false` | 本機／部署皆可使用預設 | 未啟用時 probe 不可用 |
| `REDIS_SHADOW_ENABLED` | 選用 | [redis_shadow.py](../services/events/redis_shadow.py#L26) | staging Redis shadow 旁路 | `false` | `false` | 本機／部署皆可使用預設 | 未啟用時不建立 shadow |
| `REDIS_SHADOW_URL` | shadow 必要 | [redis_shadow.py](../services/events/redis_shadow.py#L59) | 獨立 Redis 連線 URL | `rediss://<YOUR_REDIS_HOST>:<PORT>` | `空值` | 一般重建省略，staging shadow 配獨立 Redis | 缺值或 Redis 不可達時 shadow 無法運行 |
| `REDIS_SHADOW_STREAM` | 選用 | [redis_shadow.py](../services/events/redis_shadow.py#L59) | shadow stream key | `rebuild:acoustic-events:v1` | `staging:acoustic-events:v1` | 本機／部署皆可使用預設 | 無效值影響此功能的行為 |
| `REDIS_SHADOW_GROUP` | 選用 | [redis_shadow.py](../services/events/redis_shadow.py#L60) | shadow consumer group | `rebuild-shadow-group` | `staging-shadow-audit-v1` | 本機／部署皆可使用預設 | 無效值影響此功能的行為 |
| `REDIS_SHADOW_CONSUMER` | 選用 | [redis_shadow.py](../services/events/redis_shadow.py#L60) | shadow consumer 名稱 | `rebuild-shadow-consumer` | `staging-shadow-single` | 本機／部署皆可使用預設 | 無效值影響此功能的行為 |
| `REDIS_SHADOW_CONSUMERS` | 選用 | [redis_shadow.py](../services/events/redis_shadow.py#L56) | 固定單 shadow consumer | `1` | `1` | 本機／部署皆可使用預設 | 非 1 無法通過 shadow 設定驗證 |
| `REDIS_SHADOW_QUEUE_MAX` | 選用 | [redis_shadow.py](../services/events/redis_shadow.py#L61) | shadow queue 容量 | `256` | `256` | 本機／部署皆可使用預設 | 格式錯使 shadow 無法啟用 |
| `REDIS_SHADOW_MAX_EVENT_BYTES` | 選用 | [redis_shadow.py](../services/events/redis_shadow.py#L61) | shadow event bytes 上限 | `65536` | `65536` | 本機／部署皆可使用預設 | 格式錯使 shadow 無法啟用 |
| `REDIS_SHADOW_TRANSPORT_PROBE` | 選用 | [redis_shadow.py](../services/events/redis_shadow.py#L304) | shadow transport probe | `false` | `false` | 本機／部署皆可使用預設 | false 時省略 transport probe |
| `REDIS_REAL_TRAFFIC_ENABLED` | 保留 false | [redis_shadow.py](../services/events/redis_shadow.py#L57) | shadow guard 避免真實 traffic | `false` | `false` | 本機／部署均採範例 | true 時拒絕 shadow 設定 |

## Experimental

| Variable | Required? | Component | 用途 | Safe example | Source default | 本機／部署 | 失敗／停用行為 |
|---|---|---|---|---|---|---|---|
| `DASHBOARD_V2_EXPERIMENTAL_MOTION_ENABLED` | Demo 使用 false | [main.py](../main.py#L407) | 啟用實驗 motion 呈現 | `false` | `false` | 本機／部署均採範例 | Demo Stable renderer 抑制此呈現 |
| `LOCALIZATION_ENABLED` | Demo 使用 false | [main.py](../main.py#L252) | 啟用 experimental localization solver | `false` | `false` | 本機／部署均採範例 | false 時使用既有監控 region 路徑 |
| `GCC_PHAT_ENABLED` | 選用 | [main.py](../main.py#L253) | 在 localization 開啟 GCC-PHAT refine | `false` | `false` | 本機／部署皆可使用預設 | false 時略過 GCC-PHAT |
| `GCC_MIN_CORRELATION_SCORE` | 選用 | [main.py](../main.py#L332) | GCC correlation gate | `0.04` | `0.04` | 本機／部署皆可使用預設 | 解析錯誤可阻止 app 啟動 |
| `TDOA_MIN_NODES` | 選用 | [main.py](../main.py#L329) | TDOA 原型最少節點 | `3` | `3` | 本機／部署皆可使用預設 | 解析錯誤可阻止 app 啟動 |
| `TDOA_MAX_SYNC_AGE_SECONDS` | 選用 | [main.py](../main.py#L330) | TDOA 同步資料最舊秒數 | `120` | `120` | 本機／部署皆可使用預設 | 解析錯誤可阻止 app 啟動 |
| `TDOA_MAX_RESIDUAL_METERS` | 選用 | [main.py](../main.py#L331) | TDOA 解的殘差門檻公尺 | `100` | `100` | 本機／部署皆可使用預設 | 解析錯誤可阻止 app 啟動 |
| `TIME_SYNC_MAX_AGE_SECONDS` | 選用 | [main.py](../main.py#L251) | 同步 metadata 可用年齡秒數 | `120` | `120` | 本機／部署皆可使用預設 | 解析錯誤可阻止 app 啟動 |
| `MOTION_SHADOW_ENABLED` | 選用 | [main.py](../main.py#L414) | 啟用 motion shadow | `false` | `false` | 本機／部署皆可使用預設 | false 不執行 motion shadow |
| `MOTION_FIELD_TELEMETRY_ENABLED` | 選用 | [main.py](../main.py#L416) | motion 量測品質與 field telemetry | `false` | `false` | 本機／部署皆可使用預設 | false 不附加實驗 field telemetry |
| `MOTION_OUTLIER_SPEED_GUARD_ENABLED` | 選用 | [main.py](../main.py#L419) | 啟用實驗 motion speed guard | `false` | `false` | 本機／部署皆可使用預設 | false 不套用額外 speed guard |
| `MOTION_MAX_DIAGNOSTIC_SPEED_MPS` | 選用 | [main.py](../main.py#L423) | 實驗診斷速度門檻 m/s | `200` | `200` | 本機／部署皆可使用預設 | 解析錯誤可阻止 app 啟動 |
| `EVENT_DRIVEN_PIPELINE_ENABLED` | 保留 false | [redis_shadow.py](../services/events/redis_shadow.py#L57) | local／staging event pipeline 試驗 guard | `false` | `false` | 本機／部署均採範例 | true 時 Redis shadow 會拒絕 |
| `EVENT_DRIVEN_SHADOW_ENABLED` | 選用 | [shadow.py](../services/events/shadow.py#L19) | local／staging canonical event 投影比較 | `false` | `false` | 本機／部署皆可使用預設 | false 不啟用比較 |
| `OBSERVATION_SHADOW_ENABLED` | 選用 | [main.py](../main.py#L256) | 啟用 observation shadow 端點與狀態 | `false` | `false` | 本機／部署皆可使用預設 | false 時 shadow ingest 不可用 |
| `OBSERVATION_TRACKING_ENABLED` | 選用 | [main.py](../main.py#L259) | 把符合條件的 shadow observation 用於 shadow tracking | `false` | `false` | 本機／部署皆可使用預設 | false 時不執行 shadow tracking |
| `OBSERVATION_SHADOW_MAX_RECORDS` | 選用 | [main.py](../main.py#L263) | 記憶體 shadow records 上限 | `10000` | `10000` | 本機／部署皆可使用預設 | 解析錯誤可阻止 app 啟動 |
| `OBSERVATION_SHADOW_MAX_STREAMS` | 選用 | [main.py](../main.py#L282) | 記憶體 shadow streams 上限 | `2048` | `2048` | 本機／部署皆可使用預設 | 解析錯誤可阻止 app 啟動 |
| `OBSERVATION_SHADOW_TTL_SECONDS` | 選用 | [main.py](../main.py#L278) | shadow records 保留秒數 | `3600` | `3600` | 本機／部署皆可使用預設 | 解析錯誤可阻止 app 啟動 |
| `OBSERVATION_IDEMPOTENCY_TTL_SECONDS` | 選用 | [main.py](../main.py#L286) | 記憶體去重保留秒數 | `21600` | `21600` | 本機／部署皆可使用預設 | 解析錯誤可阻止 app 啟動 |
| `OBSERVATION_IDEMPOTENCY_MAX_IDS` | 選用 | [main.py](../main.py#L290) | 記憶體去重 ID 上限 | `50000` | `50000` | 本機／部署皆可使用預設 | 解析錯誤可阻止 app 啟動 |
| `OBSERVATION_LIVE_MAX_AGE_MS` | 選用 | [main.py](../main.py#L294) | shadow live 年齡上限毫秒 | `5000` | `5000` | 本機／部署皆可使用預設 | 解析錯誤可阻止 app 啟動 |
| `OBSERVATION_LIVE_TRACKING_MAX_AGE_MS` | 選用 | [main.py](../main.py#L299) | shadow tracking 年齡上限毫秒 | `120000` | `120000` | 本機／部署皆可使用預設 | 解析錯誤可阻止 app 啟動 |
| `OBSERVATION_HISTORICAL_MAX_AGE_MS` | 選用 | [main.py](../main.py#L304) | shadow historical 年齡上限毫秒 | `21600000` | `21600000` | 本機／部署皆可使用預設 | 解析錯誤可阻止 app 啟動 |
| `OBSERVATION_MAX_PENDING_PER_KEY` | 選用 | [main.py](../main.py#L308) | shadow mailbox 每 key 待處理上限 | `1024` | `1024` | 本機／部署皆可使用預設 | 解析錯誤可阻止 app 啟動 |
| `OBSERVATION_MAX_TRACKS` | 選用 | [main.py](../main.py#L312) | shadow tracking track 容量 | `2048` | `2048` | 本機／部署皆可使用預設 | 解析錯誤可阻止 app 啟動 |
| `OBSERVATION_MAILBOX_WORKERS` | 選用 | [main.py](../main.py#L316) | shadow mailbox worker 數 | `4` | `4` | 本機／部署皆可使用預設 | 解析錯誤可阻止 app 啟動 |
| `OBSERVATION_MISSING_SEQUENCE_TIMEOUT_MS` | 選用 | [main.py](../main.py#L268) | 等候缺序 observation 的時間毫秒 | `2000` | `跟 OBSERVATION_SEQUENCE_MAX_LATE_MS，後者預設 2000` | 本機／部署皆可使用預設 | 解析錯誤可阻止 app 啟動 |
| `OBSERVATION_SEQUENCE_MAX_LATE_MS` | 選用 | [main.py](../main.py#L270) | 缺序 timeout 舊名稱 | `2000` | `2000` | 本機／部署皆可使用預設 | 解析錯誤可阻止 app 啟動 |
| `OBSERVATION_FUSION_LATE_ATTACH_MS` | 選用 | [main.py](../main.py#L320) | 延遲 observation 可附回 group 的視窗毫秒 | `2000` | `2000` | 本機／部署皆可使用預設 | 解析錯誤可阻止 app 啟動 |

## Tools、tests 與平台注入

| Variable | Required? | Component／用途 | Safe example | Default | 失敗行為 |
|---|---|---|---|---|---|
| `PORT` | 平台啟動命令使用時 | Uvicorn CLI 的 listen port 參數 | `10000` | Render 注入，本機命令自行指定 | 未展開或不合法時無法 bind |
| `PYTHON_VERSION` | 選用 | Render Python runtime pin | `3.11.9` | 平台預設 | 不支援的版本可能建置失敗 |
| `PGHOST` | 用 psql 跑 migration 時 | 自己 PostgreSQL 的 host | `127.0.0.1` | libpq 預設 | 連錯 host 或失敗 |
| `PGPORT` | 非預設 port 時 | psql 連線 port | `5432` | libpq 預設 | 連錯 port 或失敗 |
| `PGDATABASE` | 用 psql 跑 migration 時 | 自己的空 DB | `sound_rebuild` | libpq 通常同 username | 查不到 DB 或操作錯庫 |
| `PGUSER` | 用 psql 跑 migration 時 | 自己的 DDL role | `sound_rebuild` | libpq 通常同 OS user | 驗證或 DDL 權限失敗 |
| `PGSSLMODE` | 視 DB provider | psql TLS policy | `require` | libpq 預設 | TLS 不相容時連線失敗 |
| `BI15_UPLOAD_TOKEN` | staging BI-1.5 工具替代值 | `tools/validate_bi1_5_staging.py` | `<YOUR_UPLOAD_TOKEN>` | 空，參照 CLI 參數 | 受保護請求無有效 token 時失敗 |
| `SOURCE_DSN` | 僅資料 rehearsal 工具 | `tools/verify_data_rehearsal.py` 來源 | `<YOUR_SOURCE_DSN>` | 無 | 缺值拋錯 |
| `DEST_DSN` | 僅資料 rehearsal 工具 | 同上，目的 | `<YOUR_DESTINATION_DSN>` | 無 | 缺值拋錯 |
| `_TOKYO_STAGING_DSN_PROMPT` | 工具內部 | `tools/prompt_db_inventory.py` 暫存 prompt | `<YOUR_TEST_DSN>` | 由工具設定及清除 | 工具缺 DSN 時不能執行比較 |
| `_SINGAPORE_STAGING_DSN_PROMPT` | 工具內部 | 同上，第二個 prompt | `<YOUR_TEST_DSN>` | 由工具設定及清除 | 工具缺 DSN 時不能執行比較 |
| `CRITICAL_PATH_TEST_PG_DSN` | 選用測試 | PostgreSQL critical-path integration | `<YOUR_DISPOSABLE_PG_DSN>` | 未設時 skip | 連線／schema 失敗使測試失敗 |
| `EVENT_DRIVEN_TEST_REDIS_URL` | 選用測試 | 真 Redis integration | `<YOUR_DISPOSABLE_REDIS_URL>` | 未設時 skip | 連線失敗使測試失敗 |

動態讀取 `tools/verify_db_migration.py` 由 `--source-dsn-env`／`--target-dsn-env` 指定變數名稱。僅比較自己的隔離 DB，使用自己的變數名。另有 `tools/benchmark_critical_path.py` 讀取 `DATABASE_URL`，重建驗收不需執行這類 benchmark。

`tools/run_local.py` 動態清除一組繼承值，並注入本機 profile。清除清單內的 `GOOGLE_APPLICATION_CREDENTIALS` 與 `DEVICE_TOKEN` 並非此 runtime 的 GCS／node auth 替代設定。舊 Blueprint 及工具可能出現未被 runtime 讀取的 `COMMAND_REST_FALLBACK_ENABLED`、`LIVE_AUDIO_MAX_CONCURRENT_STREAMS`。配置存在不構成該 flag 生效的證據。
