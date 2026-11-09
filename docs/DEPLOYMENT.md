# Current Demo Baseline 的 deployment、promotion 與 rollback

本頁記錄既有 Demo 與歷史部署。用自己的帳號、資料庫與網址建置時，從 [Deploy From Scratch](DEPLOY_FROM_SCRATCH.md) 開始。

此為操作說明；本次文件整理不部署、不改 Render、不改 DB／secrets。

## 環境

| 用途 | Service／URL | Branch | 2026-11-07 runtime commit |
|---|---|---|---|
| 正式 Demo | `sound_backend`／[production](https://sound-backend.onrender.com) | `staging` | `01f35377bcb1314d9f7f879d015920f79c9297f5` |
| 開發 staging | `sound-backend-staging`／[staging](https://sound-backend-staging.onrender.com) | `fix/dashboard-alert-map-latency` | `48705eb4817fa53f97ece896df11fd5d21b4e8ba` |

`main` 不是正式來源。上表 build／branch 已用 `/runtime-status` 核對，不由 branch 名稱或 badge 猜測。既有交接 service IDs：production `srv-d8f572eq1p3s73dimgig`；staging `srv-da6kdn61egvs7392r92g`。

資料隔離不能由 service 名稱推定。正式 DB 已修復；本工作不讀取連線字串，也不保證兩環境 DB 隔離。後續寫入測試前必須另外確認 staging 資源隔離。

## 分支與 promotion 流程（本次未執行）

```text
feature/* 或 fix/* → review / CI
→ fix/dashboard-alert-map-latency → staging Render 驗證
→ PR 至 staging branch → 經授權的 production promotion
```

1. 在獨立 branch 完成變更與風險說明，鎖定 SHA，檢查 diff 無 secrets／未批准 migration。
2. 執行 [Testing](TESTING.md) 的相關 Python／JS／integration 檢查。現有 CI 觸發範圍有限，沒有綠勾不能解讀為通過。
3. staging 驗證 build、API、WebSocket、Dashboard、Simulation 及所需實機 canary；不把合成測試當 field validation。
4. 維護者審查至 `staging` 的 PR；promotion 前記錄現行成功 deployment／SHA 與 rollback 點。
5. 經授權部署後核對實際 build、flags、API JSON 狀態及 logs。`/health=200`、`/events=200` 均不能單獨證明 DB 正常。
6. 異常依核准計畫回退，不直接在 production 試新功能。

本次文件分支 `docs/demo-baseline-handoff-20261107` 基於開發 staging，不直接更新任一部署分支。

## Important environment variables

| 設定 | 正式 Demo 值／用途 | 注意 |
|---|---|---|
| `APP_ENV` | `DEMO` | 交接值；runtime 正規化為 `demo` |
| `DASHBOARD_V2_ENABLED` | `true` | 新版 Dashboard |
| `DASHBOARD_SIMULATION_ENABLED` | `true` | 明確標示模擬的獨立工作區 |
| `DASHBOARD_V2_EXPERIMENTAL_MOTION_ENABLED` | `false` | 不開啟正式實驗 motion 呈現 |
| `DEMO_STABLE_MODE` | `true` | 隱藏工程／診斷控制，renderer 強制關閉 experimental motion |
| `LOCALIZATION_ENABLED` | `false` | 不宣稱實際 TDOA 定位 |
| `TRACKING_ENABLED` | `true` | 既有 tracking 路徑 |
| `NODE_WEBSOCKET_ENABLED`／`COMMAND_WEBSOCKET_ENABLED` | `true` | 不代表本次發送控制命令 |
| `DATABASE_URL` | secret，只記名稱 | DB 已修復；不記值、不複製進 Git |
| `GCS_BUCKET_NAME`／`GOOGLE_APPLICATION_CREDENTIALS_JSON` | 音訊儲存設定 | 本次未讀取憑證 |
| `GOOGLE_MAPS_API_KEY` | 地圖設定 | 不寫入值 |
| `UPLOAD_TOKEN`／`DASHBOARD_ADMIN_TOKEN`／`DASHBOARD_WRITE_TOKEN_REQUIRED` | ingest／Dashboard 寫入政策 | 不變更認證政策、不記 secret |
| `POSTGRES_SCHEMA_AUTO_INIT` | source 預設 `false` | 不是本次 Render env 審計值；不自行開啟 |
| `STAGING_WRITE_FREEZE`／`STAGING_DB_LATENCY_PROBE_ENABLED` | staging 維護／診斷 | 不是一般 Demo 操作開關 |
| `EVENT_DRIVEN_*`／`REDIS_*`／`OBSERVATION_*`／`MOTION_*` | 研究與 shadow | 不因文件存在就啟用正式流量 |

前八列非 secret 設定已由 runtime 核對；其餘只盤點名稱與 source 行為，不宣稱讀過完整 Render 設定。

## Blueprint／CI 歷史落差

[`../render.staging.yaml`](../render.staging.yaml) 仍宣告 `feat/latency-diagnostics-staging`、Singapore、starter、auto deploy off，不能視為當前 Render Dashboard 的完整設定。本次不套用 Blueprint、不調整 branch／plan／region／build／start。

CI 的 PR base 仍為 `feat/event-driven-redis-staging-shadow`，不是目前 production promotion 目標。這兩個被引用的舊 branch 先保留，見 [Branch archive plan](BRANCH_ARCHIVE_PLAN.md)。

## Rollback（只記錄，不執行）

| 保留分支 | SHA | 用途 |
|---|---|---|
| `backup/production-pre-ui-polish-20261107` | `0c162b5cdb452a7e48efd62da94c663b921a3afd` | UI polish 前最近回退點 |
| `backup/production-pre-demo-20261107` | `5babe2bafaffbb77b48d16a5e1675f202ae7286b` | 舊 production |
| `backup/wisun-gateway-test-20261107` | `1233e58145b86c506e1fb8fb9baffea167033a5d` | Gateway test 導入前保留點 |

經維護者授權，先判定故障、schema 相容性與當時 env，再選已驗證 Render deployment／immutable commit。Application rollback 不會自動復原 DB schema、資料或 env，不能假設 rollback branch 會還原 DB 連線設定。

回退後重做 build、八個 smoke endpoints、`/ws/dashboard` 與節點重連檢查。禁止 force push、rewrite production history、刪 rollback branch、為程式回退而刪資料。正式 schema／DB restore 必須另案審核備份，不把舊 migration 當作自動 rollback。
