# 10 分鐘交接

## 0–2 分鐘：現在在哪裡

這是 Drone Acoustic Monitoring Backend，不是 MCU／Wi-SUN／Gateway 韌體 repo。正式專題 Demo 已有穩定監控介面與獨立 Simulation Lab；真實聲學定位、Kalman／prediction／ETA field validation 尚未完成。

| 環境 | Branch | Runtime SHA |
|---|---|---|
| [Production](https://sound-backend.onrender.com/dashboard)，Render `sound_backend` | `staging` | `01f35377bcb1314d9f7f879d015920f79c9297f5` |
| [Staging](https://sound-backend-staging.onrender.com/dashboard)，Render `sound-backend-staging` | `fix/dashboard-alert-map-latency` | `48705eb4817fa53f97ece896df11fd5d21b4e8ba` |

兩者目前 source tree 相同。`main` 是舊預設 branch，不能當 production。版本、非 secret flags 與 smoke 見 [Demo baseline](DEMO_BASELINE_2026-11-07.md)。Production DB 已修復；不要重新「整理」連線設定。

## 2–4 分鐘：哪些不能亂動

- 正式 commit／部署 branch、Render env／settings、DB URL／schema／data、已成功 DB 連線。
- 既有事件 ingestion、fusion、tracking、alert timing／eligibility、Dashboard snapshot ordering、shared live/simulation helpers。
- `backup/production-pre-demo-20261107`、`backup/production-pre-ui-polish-20261107`、`backup/wisun-gateway-test-20261107`。
- Alpha-Beta 仍 authoritative；Kalman CV 僅模擬比較，不能接管正式 ETA／Alert。
- 不 force push、不 rewrite history、不刪 branch、不把模擬描述成實地驗證。

`DEMO_STABLE_MODE=true`、V2／Simulation 開、experimental motion 關；不要為看工程資訊而修改 production flags。清理計畫不是刪除授權。

## 4–6 分鐘：從哪裡看程式

讀 [Architecture](ARCHITECTURE.md)，再依工作進入 `main.py`、`services/event_fusion.py`、`services/region_localization.py`、`services/tracking/`、`services/realtime/`。Frontend 入口為 `services/dashboard_v2_4.py`、`templates/dashboard_v2_4.html`、`static/dashboard_*`。

Legacy `/dashboard/legacy` 仍是 fallback 且有測試；看似重複的 simulation helper 也被 live operations／prediction 使用，不能直接搬掉。詳見 [Code archive plan](CODE_ARCHIVE_PLAN.md)。

## 6–8 分鐘：怎麼跑與驗證

依 [根 README](../README.md) 建隔離 Python 3.11 venv，用 `tools/run_local.py` 啟動 loopback SQLite，不繼承雲端憑證。依 [Testing](TESTING.md) 跑 Python／JS、staging API／Browser／WSS 檢查。

現有 CI 只涵蓋特定 push／PR base；新分支沒有 check 不代表通過。`/events`／`/tracks` 可能 HTTP 200 + degraded；`/health` 不能單獨證明 DB。舊 smoke 的 node WebSocket 也不是 Dashboard WebSocket。

## 8–10 分鐘：下一步

1. 先 review 這批純文件與兩份 archive plans，不部署。26 個 branch 的 ancestry／unique patches 都已列出，七個未合併 branch 先保留。
2. 另開低風險工程工作，對齊 CI 的 PR base 與過時 Blueprint 宣告；先確認 Render 實際用途，再決定如何改，不把舊宣告直接套用。
3. 與 Wi-SUN vendor 固定 `node_id/event_time_ms/label/confidence`、sequence／session、時間基準、ACK／retry，先在隔離 staging 驗證 test echo 與 adapter。
4. 建立錄音／同步／真值 protocol，循 TDOA → 位置＋品質 → Kalman → prediction → ETA／Approach → alert 做研究驗證。

`POST /api/test-gateway` 只是 token 驗證後的 JSON echo；未持久化、不保證 fusion／track。研究原型存在不表示實地完成，詳見 [API Contract](API_CONTRACT.md)、[Research status](RESEARCH_STATUS.md)。

所有新功能先 feature／fix → 開發 staging → CI／Render 驗證 → PR 至 `staging` → 經授權正式 promotion。本次沒有部署、沒有改 Render，也未刪除或移動任何歷史 code／branch。
