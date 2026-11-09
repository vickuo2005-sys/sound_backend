# 本機開發與乾淨啟動

先按 [從零重建](FROM_SCRATCH_SETUP.md) 取得固定 source，進入 repo 根目錄。使用 Python 3.11 和瀏覽器。Node 20 僅 JS 回歸需要。以新的 terminal session 操作，並使用自己的本機測試設定。所有範例工作在 loopback。

## Windows PowerShell

```powershell
py -3.11 -m venv .venv
$py = '.\.venv\Scripts\python.exe'
& $py -m pip install -r requirements.txt -r requirements-dev.txt
Remove-Item Env:GOOGLE_APPLICATION_CREDENTIALS_JSON, Env:GOOGLE_MAPS_API_KEY -ErrorAction SilentlyContinue
& $py tools/run_local.py --port 8786 --data-dir .local-runtime
```

## Linux／macOS

```sh
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt -r requirements-dev.txt
unset GOOGLE_APPLICATION_CREDENTIALS_JSON GOOGLE_MAPS_API_KEY
.venv/bin/python tools/run_local.py --port 8786 --data-dir .local-runtime
```

若 Windows 裝了 Python 3.11 但 launcher 無法解析 `py -3.11`，用該版本的 `python.exe` 絕對路徑執行 `-m venv .venv`。本機 launcher 會建立 SQLite 與本機 upload token，開 V2／Simulation／節點 WSS。`.local-runtime/` 內包含 DB／token，`.venv/` 是虛擬環境，提交時只 stage 預定檔案。

另一個終端開 `http://127.0.0.1:8786/dashboard`，並以相同 venv 跑既有本機 smoke。它會寫入合成 event、固定位置與測試命令，適用於自己的測試 server。

```powershell
.\.venv\Scripts\python.exe tools/smoke_local.py --port 8786 --data-dir .local-runtime
```

```sh
.venv/bin/python tools/smoke_local.py --port 8786 --data-dir .local-runtime
```

## 本機 PostgreSQL 路徑

依 [Database Setup](DATABASE_SETUP.md) 建空庫、跑 migration。以下直接啟動 Uvicorn，因 `tools/run_local.py` 會清除 `DATABASE_URL`。為避免將密碼寫入 shell history，用互動方式輸入自己的 DSN 與 token。採非 TLS 的本機 server 時填 `sslmode=disable`。雲端 PostgreSQL 按 provider TLS 要求設定。

```powershell
$env:DATABASE_URL = [System.Net.NetworkCredential]::new('', (Read-Host 'Your test PostgreSQL DSN' -AsSecureString)).Password
$env:UPLOAD_TOKEN = [System.Net.NetworkCredential]::new('', (Read-Host 'Your test upload token' -AsSecureString)).Password
$env:APP_ENV = 'development'
$env:DASHBOARD_V2_ENABLED = 'true'
$env:DASHBOARD_SIMULATION_ENABLED = 'true'
$env:DEMO_STABLE_MODE = 'true'
$env:DASHBOARD_V2_EXPERIMENTAL_MOTION_ENABLED = 'false'
$env:CLASSIFICATION_V1_ENABLED = 'true'
$env:POSTGRES_SCHEMA_AUTO_INIT = 'false'
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8786 --workers 1
```

```bash
read -rs -p 'Your test PostgreSQL DSN: ' DATABASE_URL; printf '\n'
read -rs -p 'Your test upload token: ' UPLOAD_TOKEN; printf '\n'
export DATABASE_URL UPLOAD_TOKEN
export APP_ENV=development DASHBOARD_V2_ENABLED=true DASHBOARD_SIMULATION_ENABLED=true
export DEMO_STABLE_MODE=true DASHBOARD_V2_EXPERIMENTAL_MOTION_ENABLED=false
export CLASSIFICATION_V1_ENABLED=true POSTGRES_SCHEMA_AUTO_INIT=false
.venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8786 --workers 1
```

確認 `/runtime-status` 顯示 `postgres`，並從 [First Node](FIRST_NODE_GUIDE.md) 與 [First Event](FIRST_EVENT_GUIDE.md) 以剛才的 token 驗證。PG 路徑不要直接用依賴 SQLite token file 的 `smoke_local.py`。已啟用本機 Google Maps／GCS 時，依 [Storage Setup](STORAGE_SETUP.md) 注入設定並在對應 profile 重跑。

## 基本測試

在乾淨 env、獨立暫存工作目錄或只含測試資料的 clone 跑 `python -m pytest -q`。確認未繼承任何遠端 DB 或 Redis test URL。Protocol 可先跑 `python -m pytest -q tools/test_realtime_protocol.py tests/test_gateway_test_api.py`。JS 使用 [Testing](TESTING.md) 的 Node 命令。部署與 SSL 在自己的 hosting 驗收。
