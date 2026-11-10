# 從零重建 Drone Acoustic Monitoring

新開發者可以從公開 Git repository 建立自己的 Backend、資料庫、節點與 Dashboard。本文以 2026-11-07 Demo 的程式行為為驗收基準。既有部署座標見 [Current Demo Baseline](DEMO_BASELINE_2026-11-07.md)，原型與場域驗證界限見 [Research Status](RESEARCH_STATUS.md)。

選定驗收範圍。**Core** 包含 PostgreSQL、V2 Dashboard、HTTP ingest、節點與 Dashboard WebSocket、融合區域、軌跡、Simulation Lab 和 Kalman 比較。**地圖**加入自己的 Google Maps 設定，驗收即時地圖與選點。**Audio Evidence**加入自己的 GCS，驗收上傳、物件讀取與播放。**部署**加入自己的 HTTPS／WSS hosting。要比對完整 Demo 展示範圍，請完成所有適用項目。

## 13 步重建順序

| 步驟 | 操作 | 完成訊號 |
|---|---|---|
| 1 | 準備 Git、Python 3.11、pip／venv、現代瀏覽器及 PostgreSQL（本次驗證 18.6）。重跑歸檔驗證時使用 Python 3.11.9。可裝 psql 查 schema。Node.js 20 僅 JS tests 需要。地圖或音訊驗收需自己的 Google Cloud project，雲端驗收需可連 DB 的 FastAPI hosting。 | 可建立 venv，資料庫可使用 |
| 2 | Clone 公開 repository，checkout 下方重建 tag。 | 同一份 checkout 有 Demo 原始碼、重建文件和依賴快照 |
| 3 | 建立隔離 Python venv。 | venv 的 Python 版本符合驗收目標 |
| 4 | 安裝 runtime 與驗收套件。重跑歸檔驗證時使用依賴快照。 | 安裝與 `pip check` 成功 |
| 5 | 建立自己的 PostgreSQL 或 Supabase 空庫。依 16 檔順序建 schema，檢查 tables／indexes。 | postcheck 通過，分類欄位存在 |
| 6 | 建立自己管理的 GCS bucket／service account（音訊）與 Maps JavaScript API key（地圖）。 | bucket IAM／referrer 設定完成，待功能測試 |
| 7 | 用自己的 DB 連線設定及新產生的 token 填入 env。對照完整 env 表，選定地圖／音訊 profile。 | app process 可以讀取設定 |
| 8 | 啟動本機 Uvicorn，或在自己的 hosting 建立單 worker Web Service。 | HTTP 可連線 |
| 9 | 開 `/dashboard`，查 `/health`、`/runtime-status`、`/events`、`/event-groups`、`/tracks`，連 `/ws/dashboard`。 | V2 workspace、Postgres、非 degraded、WS 握手成功 |
| 10 | 用 `node_A01` 做節點 WSS hello／heartbeat。Gateway 供應商可另做 token 驗證的 echo。 | `hello_ack`、`ONLINE`、Dashboard heartbeat |
| 11 | 送第一筆帶唯一 ID 的 HTTP event，查 DB 與 Dashboard。 | HTTP 200、`db_id`、UI 出現同一事件 |
| 12 | 加第二節點與新鮮事件，觀察 fusion、region、track point。驗收 Simulation Lab reset／replay，測試選用的地圖、音訊與雲端路徑。 | 有多節點 group、非空 track points、模擬三軌跡 |
| 13 | 填寫驗收表，記錄 checkout 的 commit（`git rev-parse HEAD`）、套件版本及結果摘要。 | 適用項目皆通過，證據可重跑 |

## 取得重建歸檔

```sh
git clone https://github.com/vickuo2005-sys/sound_backend.git
cd sound_backend
git checkout rebuild-baseline-2026-11-09
```

這個 tag 對應一個固定的 Git commit，內含 Demo baseline 原始碼、重建指南、[環境參考](ENVIRONMENT_REFERENCE.md)、[重建驗證](REBUILD_VALIDATION.md)及 Python 依賴快照。往後的歸檔使用新 tag。歷史 production source SHA 留在驗證紀錄，供核對原始碼。

## 重現已驗證的 Python 環境

先確認使用 Python 3.11.9。Windows PowerShell 的安裝流程如下。

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -m pip install -r requirements-rebuild-2026-11-09.txt
.\.venv\Scripts\python.exe -m pip check
```

若版本檢查顯示其他 3.11 patch，使用 Python 3.11.9 的可執行檔建立新的 venv，再安裝快照。[requirements-rebuild-2026-11-09.txt](../requirements-rebuild-2026-11-09.txt) 是 baseline reproducibility snapshot，包含已驗證的 Windows runtime、測試與安裝工具版本。日常開發與其他平台的標準安裝流程見 [Local Development](LOCAL_DEVELOPMENT.md)，可繼續使用 repo 的一般 requirements。

## 依序填入新環境

- [Database Setup](DATABASE_SETUP.md) 包含 PostgreSQL 版本、空庫 SQL 順序、必要表與驗證。
- [Storage Setup](STORAGE_SETUP.md) 包含 GCS key JSON、bucket IAM、音訊 path、Maps key 的獨立設定與服務降級。
- [Environment Reference](ENVIRONMENT_REFERENCE.md) 提供每個 source 變數的必要性、用途、安全範例、預設、部署差異與失敗行為。
- [Deploy From Scratch](DEPLOY_FROM_SCRATCH.md) 提供自己的 Render 或 generic hosting 流程。

下面是最小 PostgreSQL Demo profile 的示意值。把尖括號替換成自己建立的資源。實際設定由 shell 或 hosting secret store 注入，Uvicorn 的這條啟動路徑不會自行載入 `.env`。

```dotenv
APP_ENV=development
DATABASE_URL=postgresql://<USER>:<PASSWORD>@<HOST>:<PORT>/<DATABASE>?sslmode=require
UPLOAD_TOKEN=<YOUR_UPLOAD_TOKEN>
DASHBOARD_V2_ENABLED=true
DASHBOARD_SIMULATION_ENABLED=true
DASHBOARD_V2_EXPERIMENTAL_MOTION_ENABLED=false
DEMO_STABLE_MODE=true
NODE_WEBSOCKET_ENABLED=true
TRACKING_ENABLED=true
CLASSIFICATION_V1_ENABLED=true
POSTGRES_SCHEMA_AUTO_INIT=false
```

本機獨立 PostgreSQL 若無 TLS，只在 loopback 使用 `sslmode=disable`。雲端保留 provider 的 TLS 參數，並使用自己的 `DASHBOARD_ADMIN_TOKEN` 及 `DASHBOARD_WRITE_TOKEN_REQUIRED=true`。完整 profile 及缺省行為以 env 表為準。

## 首次功能驗收

依 [First Node](FIRST_NODE_GUIDE.md) 與 [First Event](FIRST_EVENT_GUIDE.md) 逐步跑通 WebSocket、第一筆 event、雙節點 fusion 和 track。瀏覽器中開事件查詢核對 ID，接著在模擬工作區驗證 truth／Alpha-Beta／Kalman、清除與第二輪，最後檢查對應的 [Feature Matrix](FEATURE_REBUILD_MATRIX.md) 與 [System Acceptance Checklist](SYSTEM_ACCEPTANCE_CHECKLIST.md)。

**如果以上步驟與選定範圍的驗收全部成功，代表已重建出功能等價系統。** 對完整 Demo 作此判定時，還要有地圖、音訊與新部署的適用證據。研究原型的驗收範圍由 [Research Status](RESEARCH_STATUS.md) 界定。
