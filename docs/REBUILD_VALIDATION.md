# 從零重建驗證｜2026-11-09

## A. 結論

**Core rebuild：YES。Full Demo rebuild：PARTIAL。**

Core 已從空白 PostgreSQL 重建並實測。完整 Demo 驗收還包含自己的雲端 HTTPS／WSS、Google Maps 和 GCS 音訊。這三條路徑已補操作流程與驗收條件，尚待在新資源上實跑。

## B. 待完成的驗收

| 範圍 | 待完成項目 |
|---|---|
| 自建雲端 | 在自己的 hosting 部署歸檔 commit，核對 TLS、proxy 的 WebSocket Upgrade、外部 WSS、DB provider 的路由／pooler／TLS。已實跑的 DB 是本機 PostgreSQL 18.6。 |
| 地理底圖 | 建自己的 Maps JavaScript key、設定 referrer 並驗收 Google 底圖及選點。此次瀏覽器實跑相對座標圖。 |
| Audio Evidence | 建私有 GCS、service account 及 bucket IAM，完成 upload、read、signed GET、UI 播放。若組織禁止 service account key，現行 JSON-key client 需要另外接上組織核准的認證方式。其他 object storage 需要 adapter。 |
| 真實設備整合（若納入範圍） | 取得自有 MCU／Wi-SUN／Android／Gateway client 與 vendor schema，驗證其網路、事件 mapping、時鐘、重送與音訊串流。已驗收合成節點和 Gateway HTTP echo。 |

## C. 實際重建步驟

**13 步**。從乾淨電腦、clone、venv、依賴、空庫與資源設定，到啟動、連線、事件與功能驗收的順序見 [從零重建](FROM_SCRATCH_SETUP.md)。

## D. 重建者自行建立的資源

- 自己的 PostgreSQL instance／Supabase project、DB role、DSN。
- 自己的 upload token 與所需 Dashboard admin token。
- 需要上線時，自己的 Render 或其他 FastAPI host、HTTPS hostname 和 DB network access。可使用 provider 發的網址。
- 需要地理底圖時，自己的 Google Cloud project、Maps API、受 API／referrer 限制的 browser key。
- 需要音訊時，自己的私有 GCS bucket、service account、IAM 與授權使用的 JSON key。
- 真實設備驗收才需要自有節點、Gateway、韌體或 Android client。

## E. 以新資源可重建的功能

| 實測 | 結果 |
|---|---|
| 固定 source | 以 `01f35377bcb1314d9f7f879d015920f79c9297f5` 的獨立 checkout 執行 |
| 乾淨環境 | Windows 新 Python 3.11.9 venv，從 repo requirements 安裝。測試 app 環境由 allowlist 建立，資料落在獨立本機目錄 |
| SQLite | 既有 `tools/run_local.py`＋`tools/smoke_local.py` 通過，包含 command delivery／ACK／result |
| 空白 PostgreSQL 18.6 | 逐字執行文件的 Python migration 範例。16 檔全部成功，重複執行時空庫 guard 拒絕。唯讀 postcheck、12 tables、9 分類欄位和指定索引核對成功 |
| HTTP | SQLite 和 PostgreSQL 兩路的 `/health`、`/runtime-status`、`/events`、`/tracks`、`/event-groups`、`/device-status`、`/device-locations`、`/dashboard` 均 200，JSON 非 degraded |
| Node／Dashboard WS | 逐字執行文件的節點範例，兩個 node 均收到 hello_ack，Dashboard socket 收到 node_heartbeat，API 看到 ONLINE |
| Event／fusion／tracking | 逐字執行 First Event 的單事件與 `--fusion` 範例。SQL 查到事件，雙節點事件同一 segment group，group 可回查實際 track point |
| 分類與重送 | PostgreSQL 寫入 v1 分類 payload，再送相同 ID，取得相同 db_id、SQL 確認只有一列且分類值正確 |
| Gateway／無音訊路徑 | 兩個 DB 路徑的 Gateway echo 200。沒有音訊的事件回 evidence 404 |
| Browser | 本機 SQLite Dashboard 正常載入，看到合成節點的事件列及相對座標圖。Simulation 載入後可暫停，觀察到真值 68、Alpha-Beta 10、Kalman 10 點，全部清空後時間歸零且無模擬事件 |
| Python 基本套件 | 83 passed，涵蓋 protocol、Gateway、Dashboard／Simulation、融合、group track 與分類 |
| JavaScript | Node v24.22.1 上 28 個既有 suite 檔案通過 |

Windows 路徑已實跑。Linux／macOS 已有啟動指令，仍待獨立實跑。Python 測試出現 TestClient／httpx、Pydantic 及 pytest-asyncio 的棄用提示。

### 2026-11-10 歸檔複驗

- [依賴快照](../requirements-rebuild-2026-11-09.txt) 以 `python -m pip freeze --all` 從上表的原始 Windows Python 3.11.9 venv 匯出，共 48 個套件，含直接與間接依賴、測試工具、pip 和 setuptools。這是 baseline reproducibility snapshot，日常開發沿用 `requirements.txt` 與 `requirements-dev.txt`。
- 只用快照在另一個全新的 Windows Python 3.11.9 venv 安裝，`pip check` 通過，`pip freeze --all` 的套件及版本與原始環境完全一致。
- 使用新 venv 重跑 SQLite smoke、空白 PostgreSQL 18.6 的 16 檔 migration 與 postcheck、兩個後端的八個 HTTP 讀取端點、節點及 Dashboard WebSocket、事件寫入、融合與軌跡、Gateway echo、PostgreSQL 分類與去重。83 項既有 Python 測試通過，棄用提示仍存在。上表的瀏覽器和 JavaScript 結果來自 2026-11-09。
- 重建 tag `rebuild-baseline-2026-11-09` 將上述 production source SHA 的 runtime 檔案、重建文件和依賴快照收在同一個 commit。與 production source 比對，只有 Markdown 文件及快照有差異。[從零重建](FROM_SCRATCH_SETUP.md#取得重建歸檔)

## F. 需由重建者決定的外部設定

| 設定 | 如何補齊 |
|---|---|
| DB host、pooler mode／username、SSL／CA、連線數、角色與網路 ACL | 由自己的 provider／DBA 決定並驗收。空庫 SQL 順序和最低 schema 已核對 |
| Hosting hostname、region、plan、Python patch、TLS／proxy／timeouts、replica policy | 用自己的部署設定。程序內 connection state 以單 worker／instance 驗收 |
| GCS project、bucket、region、IAM、key policy、資料保留及 Maps referrer | 由資源擁有者建立。Repo 僅定義 GCS JSON 接口與使用方式 |
| 各環境 credentials、原本帳號政策、既有事件／音訊資料 | 重建者配置自己的值與資料。驗收可用合成資料 |
| 實機 node IDs、固定位置、據點／半徑、韌體、模型、Gateway vendor 欄位、時鐘／校正 | 依現場設備和瀏覽器設定重建，測試使用合成節點和座標 |

參考 [完整 env](ENVIRONMENT_REFERENCE.md)、[部署](DEPLOY_FROM_SCRATCH.md) 與 [研究狀態](RESEARCH_STATUS.md)。
