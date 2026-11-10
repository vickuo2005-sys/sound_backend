# 正式 Demo baseline｜2026-11-07

此版本供正式專題 Demo，視為穩定工程 baseline。封存文件不部署、不改核心功能、不調整 Render／DB。研究宣稱界限見 [Research status](RESEARCH_STATUS.md)。

## 版本與來源

| 項目 | 值 |
|---|---|
| Repository | `vickuo2005-sys/sound_backend` |
| Production service | `sound_backend` |
| Production URL | [正式 Dashboard](https://sound-backend.onrender.com/dashboard) |
| Production branch | `staging` |
| Production commit | `01f35377bcb1314d9f7f879d015920f79c9297f5` |
| Staging service | `sound-backend-staging` |
| Staging branch | `fix/dashboard-alert-map-latency` |
| Staging commit | `48705eb4817fa53f97ece896df11fd5d21b4e8ba` |
| 共同 source tree | `2b6bd564379d8823d0e6a7760bc09923cac386ee` |

Production commit 是 merge commit，parents 為 `0c162b5` 與 `48705eb`；兩個目前 baseline 的檔案內容相同，Git history 並不相同。Git refs 與兩站 `/runtime-status.build` 已交叉核對，不把目前文件分支的 commit 算作新的 production baseline。

## Demo Stable flags

```text
APP_ENV=DEMO
DASHBOARD_V2_ENABLED=true
DASHBOARD_SIMULATION_ENABLED=true
DASHBOARD_V2_EXPERIMENTAL_MOTION_ENABLED=false
DEMO_STABLE_MODE=true
```

以上只有非 secret 設定。runtime 將 APP_ENV 正規化為 `demo`；另核對 `LOCALIZATION_ENABLED=false`、tracking／node WSS／command WSS 為 true，DB backend 為 PostgreSQL。`DATABASE_URL` 已於先前操作修復，本次不讀取、不輸出、不修改其值。

## 可展示內容／驗證分層

| 範圍 | 可展示內容 | 證據層級 |
|---|---|---|
| 正式監控 | Backend health、node status／location、WSS、AI classification metadata、events | 既有實作與使用者交接；本次重新核對 HTTP／Dashboard WSS |
| 證據與歷史 | 有資料時的音訊、event groups／多節點融合、historical tracks、CSV | source／既有 tests；本次未下載音訊或執行完整互動回放 |
| 地圖與據點 | node／event／track map、protected site、warning radius | source／既有介面；本次未改正式據點設定 |
| Gateway test | 授權 JSON 連通性 endpoint | source／既有 tests；不是 DB ingest，本次不 POST |
| Simulation Lab | 自訂節點／據點、多目標、range、truth、Alpha-Beta、Kalman CV comparison、prediction、ETA／Approach、alert、replay | 模擬／合成測試；不可說成實地能力 |

Kalman 僅 comparison/shadow，不驅動正式 ETA／Alert。正式部署開放 Simulation 不表示實驗 motion、TDOA 或實地 ETA 已啟用。

## 本次 runtime smoke

開始時間：2026-11-07 22:51:43 +08:00。Production 與 staging 均得到下列結果；沒有測試事件、控制命令、upload、admin 或 migration 操作。

| GET endpoint | Production | Staging |
|---|---:|---:|
| `/health` | 200 | 200 |
| `/events?limit=20` | 200 | 200 |
| `/tracks?limit=20&points_limit=100` | 200 | 200 |
| `/event-groups?limit=8` | 200 | 200 |
| `/device-status` | 200 | 200 |
| `/device-locations` | 200 | 200 |
| `/runtime-status` | 200 | 200 |
| `/dashboard` | 200 | 200 |

兩站的 `/ws/dashboard` handshake 均成功；JSON 未見 `status=degraded` 或所篩查 DB 連線錯誤。Dashboard HTML 具有 V2 workspace 結構。此為 bounded smoke，不是本次全量 Browser E2E、音訊／硬體 field validation 或長時間 logs 審計。

注意：`/tracks` GET 在非 freeze 時可能進行 stale-track close 維護；本次只做正常 Dashboard 讀取，沒有呼叫刪除／重建 endpoint。不要將所有 GET 都概括成無 DB 副作用。

## 保留的 rollback branches

- `backup/production-pre-ui-polish-20261107` → `0c162b5cdb452a7e48efd62da94c663b921a3afd`。
- `backup/production-pre-demo-20261107` → `5babe2bafaffbb77b48d16a5e1675f202ae7286b`。
- `backup/wisun-gateway-test-20261107` → `1233e58145b86c506e1fb8fb9baffea167033a5d`。

不得刪除、移動或覆寫這些 refs。Rollback 流程及 DB／env 不會隨 branch 自動回復的限制見 [Deployment](DEPLOYMENT.md)。
