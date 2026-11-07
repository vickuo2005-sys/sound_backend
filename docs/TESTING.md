# Testing

測試必須區分 unit／合成／本機 integration、staging runtime、真實硬體 field validation。本次文件整理的實際執行結果見 [Archive validation](ARCHIVE_VALIDATION_2026-11-07.md)。

## Python

Baseline 有 `tests/` 下 56 個 Python test files、`tools/` 下 10 個 `test_*.py`；檔案數不等於 test case 數。[`../pytest.ini`](../pytest.ini) 會收集這兩個目錄、使用 asyncio auto。

在沒有 production DB／bucket／secret 繼承的隔離環境準備 Python 3.11：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
```

可依變更聚焦 dashboard／gateway／classification／fusion／tracking／replay。Redis tests 區分 mock 與真實 Redis；真 PostgreSQL 或 Redis 工具只能指向獨立可拋棄的測試服務，不能沿用 production credentials。沒有啟用的 integration test 或 skipped case 不得計為實際 DB 驗證。

## JavaScript

[`../tests/js/`](../tests/js/) 有 28 個 Node regression files，不需 npm project 才能執行。CI 使用 Node.js 20。

```powershell
foreach ($testFile in Get-ChildItem -LiteralPath tests/js -Filter '*.js') {
    node $testFile.FullName
    if ($LASTEXITCODE -ne 0) { throw "JavaScript regression failed" }
}
```

涵蓋 event snapshot race、map／node geometry、live freshness、歷史 context／replay、Simulation Lab controls、Alpha-Beta、Kalman、prediction、ETA。合成 RMSE／平滑度測試只支持指定測試資料，不支持真實場域精度宣稱。

## CI 現況

[`../.github/workflows/dashboard-fix-validation.yml`](../.github/workflows/dashboard-fix-validation.yml)：

- push 僅 `fix/dashboard-alert-map-latency`、`demo-stable-v1`。
- pull_request base 僅 `feat/event-driven-redis-staging-shadow`。
- Python 3.11／Node 20；安裝 runtime requirements、pytest／asyncio、`httpx2`、redis；此處忠實記錄 workflow，未更動依賴。
- Python suite 排除一次 uptime-sensitive cache case，再等待 monotonic 超過 61 秒後單獨執行；接著跑全部 JS、compile Dashboard Python、`git diff --check`。

開發 baseline `48705eb` 的 [push run 42382252510](https://github.com/vickuo2005-sys/sound_backend/actions/runs/42382252510) 與 [PR run 42382256973](https://github.com/vickuo2005-sys/sound_backend/actions/runs/42382256973) 均為 success。這是已存在 baseline 的 CI 證據，不冒充本次文件 commit 的測試。

新的 docs branch 或 PR 至目前開發 branch 不符合上述自動觸發範圍。未出現 CI check 不是通過；要調整 workflow 或啟用 branch protection，另開工程工作，本次不修改。

## 本機 runtime

```powershell
.\.venv\Scripts\python.exe tools/run_local.py --port 8786
```

[`../tools/run_local.py`](../tools/run_local.py) 移除繼承的雲端 DB／bucket／token，使用 `.local-runtime/` SQLite，僅允許 loopback host。另一 shell 的 `tools/smoke_local.py` 會建立合成事件、node WSS、固定位置及 command，**只限本機**；不要把這類腳本改指 production。

## Runtime smoke

先 staging，再於已授權的正式 release 做同一組正常 GET：`/health`、`/runtime-status`、`/events?limit=20`、`/tracks?limit=20&points_limit=100`、`/event-groups?limit=8`、`/device-status`、`/device-locations`、`/dashboard`，加 `/ws/dashboard` handshake。不要發 node hello／command／合成 event 來冒充正式 smoke。

Acceptance：HTTP 200、JSON 不是 degraded、build SHA／branch 符合、必要非 secret flags 符合、Dashboard 可渲染／連線、logs 無新 DB connection error。health 是 liveness，不單獨證明 DB。`/tracks` 有 stale-track close 維護語義；測試者應先理解既有讀取路徑，不額外呼叫 close／cleanup／rebuild。

[`../tools/post_deploy_smoke.py`](../tools/post_deploy_smoke.py) 的既有 `ok` 對部分 endpoints 接受小於 500，且 `--allow-websocket` 會打 `/ws/node/{device_id}` 送 hello，**不是 Dashboard handshake**。因此不能只看該工具 exit code 就宣稱本節全部通過，也不在 production 直接使用其 node 選項。本次不改工具。

## Browser E2E（後續 staging checklist）

1. 首頁無原始 CSS、白屏、錯位；記錄 Console errors／warnings 與 Network。
2. 進入標明 Simulation／非實地驗證的工作區，啟動既有情境。
3. 同時辨識 truth、Alpha-Beta、Kalman，各自誤差／點數；排除 NaN、Infinity、遠距跳點。
4. 驗證 ETA／Alert／Approach 來源仍為 Alpha-Beta，不只依 UI 說明判斷。
5. Start、Pause、Resume、route restart、Clear、scenario switch；確認 Kalman state／trail 清除、第二輪無上一輪殘留。沒有設定路徑時 restart disabled 與一般 clear 不同，不能混為同一操作。
6. 回正式 workspace 驗證 Overview／Nodes／Events／Map／Tracks、API 與 Dashboard WSS。

此清單不是本次全量 Browser E2E 執行聲明；場域驗證 protocol 仍見 [Research status](RESEARCH_STATUS.md)。

## 文件變更驗證

檢查 `git diff --check`、新增／修改 Markdown 的相對檔案及 anchor links、JSON examples、branch／route 表與 source、changed files 的 secret patterns，並以 git path／blob 比較確認只改 README／docs。既有歷史文件的所有連結或 secrets 不在「新 diff 無新增 secret」保證範圍。
