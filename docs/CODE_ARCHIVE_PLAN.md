# Code archive plan｜僅盤點、不移動、不刪除

依 2026-11-07 baseline 的 tracked tree、import／renderer／test references 及 Git history 分類。「LIKELY ARCHIVABLE」只是後續人工審查候選；沒有把缺少字串引用當作 unused 的充分證據。

## KEEP

| 路徑 | 原因 |
|---|---|
| [`../services/dashboard_v2_4.py`](../services/dashboard_v2_4.py)、[`../templates/dashboard_v2_4.html`](../templates/dashboard_v2_4.html)、[`../static/`](../static/) | 現行正式 Demo renderer／UI；不能因檔名含 v2_4 而當舊版 |
| [`../static/dashboard_simulation_lab.js`](../static/dashboard_simulation_lab.js)、[`../static/dashboard_simulation_kalman.js`](../static/dashboard_simulation_kalman.js) | 現行獨立 Lab 與比較軌跡；reset／clear／replay 行為受 tests 保護 |
| [`../static/dashboard_simulation_tracker.js`](../static/dashboard_simulation_tracker.js)、[`../static/dashboard_simulation_eta.js`](../static/dashboard_simulation_eta.js) | 不只模擬，live operations／prediction 也共用；不可合併成未驗證的新演算法 |
| [`../services/event_fusion.py`](../services/event_fusion.py)、[`../services/region_localization.py`](../services/region_localization.py)、[`../services/tracking/`](../services/tracking/) | 正式 canonical fusion／region／tracking 與排序保護 |
| [`../services/realtime/`](../services/realtime/)、[`../app/protocol/`](../app/protocol/) | node／command／audio 契約與 in-memory managers |
| [`../tests/`](../tests/)、[`../tests/test_gateway_test_api.py`](../tests/test_gateway_test_api.py) | 保留既有回歸測試與 Gateway connectivity contract tests |
| [`../tools/run_local.py`](../tools/run_local.py)、[`../tools/smoke_local.py`](../tools/smoke_local.py) | 明確本機隔離啟動與 synthetic integration，可重現交接環境 |

## REVIEW

| 項目 | 為何需要審查／下一步 |
|---|---|
| `main.py` 的 `/dashboard/legacy`／`dashboard_v4_clean()` | 大型 inline legacy HTML，看似可拆，但 `/dashboard` flag 關閉時仍 fallback，且多個 tests 直接呼叫；本次不拆、不搬 |
| [`../static/dashboard_simulation_scenarios.js`](../static/dashboard_simulation_scenarios.js)、[`../static/dashboard_simulation_prediction.js`](../static/dashboard_simulation_prediction.js) | 舊 overlay／scenarios 與新 Lab 併存，但仍被 renderer 在 simulation 開啟時注入，且有 tests；不能判為重複死碼 |
| [`../services/localization/`](../services/localization/)、[`../tools/test_tdoa_solver.py`](../tools/test_tdoa_solver.py) | 原型 solver 與合成 tests 仍有研究價值；標明非實地完成，不當作廢棄程式刪除 |
| [`../services/events/`](../services/events/)、shadow／ordering／latency modules | 可選研究路徑，存在 import、flags、tests 與證據；未啟用不等於 unused |
| [`../render.staging.yaml`](../render.staging.yaml) | 宣告 branch／plan 與當前交接狀態不完全一致；應另案對齊，禁止本次套用或修改 Render |
| [`../tools/post_deploy_smoke.py`](../tools/post_deploy_smoke.py) | 舊 acceptance 對部分 4xx 寬鬆，node WS 不是 Dashboard WS；另案改善，不能當完全通過的憑據 |
| [`archive/v2_4/DEPLOYMENT_AND_CREDENTIALS.md`](archive/v2_4/DEPLOYMENT_AND_CREDENTIALS.md)、舊 env／migration reports | 需單獨做敏感資訊與有效性審閱；本次不複製任何值、不重寫 Git history，也不宣稱舊檔已通過全歷史 secret audit |

## LIKELY ARCHIVABLE（未執行）

| 候選 | 條件與理由 |
|---|---|
| [`../START_V2.6.md`](../START_V2.6.md) | 2026-09-16 會議版本入口，與目前 baseline 不同；新索引完成後可提議移入 dated archive，先更新反向連結 |
| [`../CRITICAL_PATH_OPTIMIZATION_REPORT.md`](../CRITICAL_PATH_OPTIMIZATION_REPORT.md)、[`../EVENT_DRIVEN_V1_REPORT.md`](../EVENT_DRIVEN_V1_REPORT.md)、[`../EVENT_DRIVEN_V2A_REDIS_VALIDATION_REPORT.md`](../EVENT_DRIVEN_V2A_REDIS_VALIDATION_REPORT.md)、[`../EVENT_DRIVEN_V2B_REDIS_STAGING_SHADOW_REPORT.md`](../EVENT_DRIVEN_V2B_REDIS_STAGING_SHADOW_REPORT.md) | 已完成階段的頂層報告，可在另一次 docs-only PR 依日期歸檔；保留原 SHA／證據，不刪研究結果 |
| [`../outputs/`](../outputs/) 中舊 migration rehearsal／latency／Redis shadow JSON 與 PNG | 保留 checksum、來源 SHA、日期、links 後，可討論移往有索引的 immutable evidence archive；不是 runtime code，也不是可以隨意清掉的暫存 |
| [`../verification/`](../verification/) 中較早執行紀錄 | 可按日期歸入 testing evidence，必須保留當時環境與範圍，不把舊通過數當新測試結果 |
| [`../tools/measure_staging_db_latency.py`](../tools/measure_staging_db_latency.py)、[`../tools/run_region_latency_comparison.py`](../tools/run_region_latency_comparison.py) 等一次性 probe | 先核對 runbook 引用與使用者需求；只能提議分組，不宣告 deprecated、也不在 production 執行 |

尚未找到可在不做進一步引用／runtime 覆蓋審查下直接刪除的「已證明 unused」程式。兩份計畫的完成不依賴刪除任何東西。

## DO NOT TOUCH

- [`../main.py`](../main.py) 的 ingest／DB pool／auth／alert／WebSocket／legacy fallback 行為及目前核心服務。
- [`../migrations/`](../migrations/)、migration precheck／postcheck／schema verifier：schema 歷史不是廢檔，不能靠搬檔改 migration 順序。
- secrets 產生／env 準備工具：[`../tools/generate_staging_secrets.ps1`](../tools/generate_staging_secrets.ps1)、[`../tools/staging/`](../tools/staging/)。只審查說明，不執行、不匯出憑證。
- 本機／雲端 DB、音訊 bucket、production Render settings、deployment branches、三個 `backup/*` refs。

## 後續歸檔 gate

每一候選需有 owner、引用清單、保留位置／SHA、連結更新與 rollback 方法；先在獨立 branch 做純搬移或文件 PR，重跑對應 tests／links，再由維護者決定。不要把歸檔與大型 refactor、演算法替換或資料清除混在同一變更。
