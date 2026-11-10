# 用自己的 hosting 從零部署

先完成 [空庫 migration](DATABASE_SETUP.md)，再建立自己的 Web Service。從 [從零重建](FROM_SCRATCH_SETUP.md) 的歸檔 tag 取得程式，在自己的 repository 建立 release branch 指向該 commit，再於 hosting 選取該 branch。啟動後驗證服務並記錄實際部署 SHA。

## Render Web Service

在自己的 Render workspace 建立 Web Service，選擇自己的 repository 與 branch。程式根目錄包含 `main.py` 與 `requirements.txt`。

| 欄位 | 設定 |
|---|---|
| Runtime | Python 3.11 系列。可用平台支援的 `PYTHON_VERSION` 設定，例如驗證使用的 `3.11.9` |
| Build command | `python -m pip install -r requirements.txt` |
| Start command | `uvicorn main:app --host 0.0.0.0 --port $PORT --workers 1` |
| Health check path | `/health` |
| Processes / replicas | 1 worker／1 instance，節點與 Dashboard connection state 在程序記憶體中 |
| DB | 自己的 PostgreSQL DSN，已跑顯式 migrations，`POSTGRES_SCHEMA_AUTO_INIT=false` |
| Storage / Maps | 按驗收範圍配置自己的 GCS JSON／bucket 及 Maps key |
| Autodeploy | 首次建置可選 manual，驗收後由資源擁有者決定 |

[Render FastAPI 指南](https://render.com/docs/deploy-fastapi) · [Render Web Services](https://render.com/docs/web-services) · [Python 版本設定](https://render.com/docs/python-version)

將 [env reference](ENVIRONMENT_REFERENCE.md) 的 Demo profile 寫入平台環境，部署版 `APP_ENV=DEMO`，V2／Simulation／Demo Stable 開，experimental motion／localization 關。以新值配置 `DATABASE_URL`、`UPLOAD_TOKEN`、`DASHBOARD_ADMIN_TOKEN`，並按操作政策設定 `DASHBOARD_WRITE_TOKEN_REQUIRED=true`。使用 platform secret store。需要正式地圖時，Google Maps key 的 allowed referrer 要包含自己的 HTTPS host。需要音訊時，依 [Storage Setup](STORAGE_SETUP.md) 注入整份服務帳戶 JSON 字串。

## Generic FastAPI hosting

可使用有 Python、持久程序與 TLS reverse proxy 的 VM、container 或 PaaS。把 `PORT` 設為平台分配值，按相同 build／start 命令運行一個 worker。Proxy 保留 WebSocket Upgrade 與相關 headers，支援長連線及斷線重連。外部 HTTP 使用 HTTPS，兩種 WS 使用 WSS，由相同 host 提供。Node route 的 URL device ID 要與 hello 一致。若需要只對內開放，使用網路限制或 HTTP／WS 都能通過的代理存取政策。Node protocol 本身未驗證上傳 token，token 檢查用於 HTTP ingest。 [Render WebSockets](https://render.com/docs/websocket)

```text
https://<YOUR_BACKEND_HOST>/dashboard
https://<YOUR_BACKEND_HOST>/health
wss://<YOUR_BACKEND_HOST>/ws/dashboard
wss://<YOUR_BACKEND_HOST>/ws/node/{device_id}
```

`RENDER_GIT_*`／`RENDER_SERVICE_*` 由平台注入。非 Render 上，直接在 release／image metadata 保存 commit，並用 runtime／功能檢查核對。不要仿造任何舊 service ID 來改變 token policy。

## 部署驗收

1. 確認自己的 DNS、TLS、release SHA、DB schema 與 health logs。
2. 對自己的 `/health`、`/runtime-status`、`/device-status`、`/device-locations`、`/events`、`/event-groups`、`/tracks`、`/dashboard` 驗證 HTTP 200，JSON 非 degraded，runtime database 是 postgres。
3. 依 [First Node](FIRST_NODE_GUIDE.md) 實際做 HTTPS host 的 WSS hello／heartbeat，同時接 `/ws/dashboard`。
4. 在自己的驗收部署送入合成 event，核對 DB、Dashboard、fusion／tracks；執行 [系統驗收](SYSTEM_ACCEPTANCE_CHECKLIST.md)。Audio／Maps 如為驗收範圍，也要實際驗證。
5. 記錄 chosen host、SHA、非秘密設定與 smoke 結果。部署與 DB schema 的回退分開規劃。
