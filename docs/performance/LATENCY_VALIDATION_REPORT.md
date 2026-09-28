# PR #5 Latency Diagnostics 驗證報告

日期：2026-09-28。基準：`f35a816d8489f8c1691bbc21d02a6935669dee04`。
分支：`feat/latency-diagnostics-staging`。PR 保持 Draft，禁止 merge／production 部署。

## 結果與範圍

自動化測試、本機合成 smoke test 與 Render staging smoke test 已完成。**Android 實機測試尚未完成。**
已確認 Render staging service `sound-backend-staging`（`srv-da6kdn61egvs7392r92g`）及登入帳號的設定／手動部署權限。DATABASE_URL 值在 Render UI 遮罩，無法確認 DB project／host／role 與 production 隔離；本次依使用者指示仍完成 staging 部署。
不把 repository 中的 staging blueprint 或 UI 的 STAGING 字樣當成隔離證明。
production service 未修改、未部署。

全新 checkout 的 Git 狀態乾淨；沒有覆寫其他工作目錄。另建 detached baseline checkout
重現既有失敗。TDOA／Tracking 演算法檔案 diff 為空，沒有改正式 DB、環境變數或運算資源。

## 實際測試

Python 3.12 本機 venv，依 requirements.txt／requirements-dev.txt 安裝；Node v24.19.0。
套件未鎖版，確切依賴另保存 freeze。pytest.ini 收集 tests 與 tools；沒有 npm package.json
或既有 GitHub Actions workflow，JS 測試為 Node 直接執行 assert／VM harness。

| 執行項目 | 基準結果 | 修復後結果 |
| --- | --- | --- |
| `python -m pytest -q tests/test_latency_diagnostics.py tests/test_latency_integration.py` | 4 passed | **38 passed** |
| `python -m pytest -q tests/test_dashboard_v2_2_parity.py` | 12 passed / 6 failed | **18 passed** |
| `python -m pytest -q` | 264 passed / 7 failed | **312 passed**, 3 deprecation warnings |
| 每個 `tests/js/test_*.js` 用 Node 執行 | 18 檔通過 / 1 檔失敗 | **20 檔全部通過**；不是 20 個獨立 assertion |
| `python tools/test_timestamp_tdoa.py` | 本次未先跑 baseline | 通過，合成資料 |
| `python tools/test_tdoa_solver.py` | 本次未先跑 baseline | 通過，合成資料；不可當作真實定位精度 |
| `python tools/test_localization_pipeline.py` | 首次執行因缺 Response 參數失敗 | 修正 harness 後通過 |
| `node --check` | — | 14 個 static JS 與 13 個渲染後 inline scripts 通過 |
| `python -m compileall -q main.py services app tests tools` | — | 通過 |
| `python -m pip check`、`git diff --check` | — | 通過 |

最早安裝尚未完成時兩次 pytest 啟動回報 `No module named pytest`，沒有收集或執行測試；
安裝完成後重新依指定順序執行。中間擴充套件曾為 30、35 項，最終為上表 38 項；
完整 suite 最終 312 項包含診斷、parity 與 collector 測試，不能將各列再加總。
剩餘 warning 為 Starlette/httpx 與既有 Pydantic `.dict()` 棄用警告，不是失敗。

## 原因與最小修復

1. **Dashboard 異常欄位**：直接 `toFixed()` 會對缺欄位／字串拋例外。
   驗證 count、有限非負 quantiles 與順序；壞樣本顯示尚無樣本，無效 pending 不插入 HTML。
   device-status queue 也納入 warning 判斷。
2. **Worker 相容性與 pending**：device worker 新必填 enqueue 參數破壞既有直接呼叫。
   恢復可省略參數，直接呼叫不消耗其他 job 的 pending。
   Future 在 worker 開始前被取消時新增 callback 清除 pending；submit 失敗原有回復保留。
3. **取樣健全性**：捕捉 float 轉換 OverflowError，避免大有限樣本的平均值溢位；
   queue sample 與 decrement 在同一把鎖內，snapshot 複製後在鎖外排序，縮短 writer 阻塞。
4. **DB sample 邊界**：成功 save 後立即記錄，後續位置查詢失敗不再丟掉已完成 DB 計時。
   沒有新增 DB 寫入或改動存取／融合／定位／追蹤決策。
5. **既有 parity 測試過期**：六個失敗涉及空白敏感字串、marker ownership 移到主地圖、
   回放顯示 path 命名與動畫 function 定義被誤判成每幀呼叫。更新為目前實作的明確斷言，
   保留 UAV icon、真實座標、optional uncertainty、節點形狀、overlay persistence 與無虛構觀測要求。
   回放本來已有可選平滑顯示；檢查它有「示意」標籤且不修改 recorded path／point。
   沒有刪除測試、加入跳過、弱化成永遠成立的斷言，或為舊字串重新加入重複 marker。
6. **既有 JS fixture**：兩節點案例同時宣告四節點 backend membership，與已存在的
   backend-authoritative 行為衝突。分開驗證 membership 與未關聯 event evidence，
   保留 line／point／polygon、stale／invalid、cleanup 斷言。顏色轉小寫再比值；
   RAF harness 執行前消耗 callback，符合瀏覽器語意；另真正計數 callback 呼叫以驗證無 flicker。
7. **獨立定位測試 harness**：`create_event` 已要求 Response，補傳 Response，不改任何定位斷言。
8. **staging blueprint**：branch 改成本 PR 分支，補 `DASHBOARD_V2_ENABLED=true`。
   只改檔案，未套用外部環境，CPU／記憶體／workers／pool 設定不變。
9. **30 秒更新飢餓問題**：本機瀏覽器確認 5 秒 device poll 與 30 秒完整 snapshot 的
   timer 重疊，完整 snapshot 持續被 guard 丟棄，API 已新增樣本但面板仍顯示舊數值。
   改為合併一個延後的 periodic refresh，於 device poll 完成或失敗後執行。
   新增成功／失敗／重複 tick 回歸，並重跑事件與位置同步測試，確保競態保護保留。

新增測試涵蓋精確 P50/P95/P99、256 筆 rolling、8 threads、無效值／reset、成功／例外／
closed loop／真實 executor 排隊／submit failure／pre-start cancellation、實際 HTTP API、
各計時邊界與單位、solver success/failure、broadcast payload 保留，以及 browser 空資料、
異常欄位、API 成功／失敗、1,000 則訊息 burst 和 1 秒診斷面板更新節流。

## 量測正確性與限制

逐項審查 event_db_write、event_initial_submission、兩種 queue_wait、event_fusion、
localization_group_load／compute／db_save／tracking、tdoa_solver、post_ingest_pipeline、
websocket_broadcast。server 均為 monotonic 差值 × 1000，browser performance.now 已為毫秒。
完整邊界、例外路徑與母體列在 LATENCY_DIAGNOSTICS.md。

部分階段只含成功呼叫，solver／fusion／broadcast 則含 finally 的失敗樣本；pending 只表示
尚未開始的 job。不能相加階段 P95、相減不同母體的 quantiles，或把相鄰 rolling snapshot
視為獨立資料。Browser message handler 排除 JSON parsing、診斷面板更新、非同步工作、
網路及真正 paint 時間。snapshot 仍是有限的同步 CPU 工作；沒有宣稱 production 負載下零影響。

## 本機 smoke test（不是 staging）

只在 `127.0.0.1:8766`、本機 SQLite、task-local token 執行。`/health`、`/runtime-status`、
`/dashboard` 均回 200。空資料的 256/stages/pending/peak 結構正常，合成 HTTP 事件可產生
DB／initial-submission／fusion／queue／pipeline／broadcast 樣本，背景 pending 回到 0。
瀏覽器確認 P50/P95/P99、count、queue 與 Browser message handler P95，WebSocket 可重連；
修復排程後，不 reload 頁面，觀察 DB count 從 5 增至 6、fusion／queue count 從 2 增至 3、
broadcast count 從 4 增至 6，兩類 pending 均為 0，確認 periodic runtime refresh 恢復。
console 檢查未見 error/warn。Google Maps 未配置，僅驗證 fallback 與地圖模組的自動化 tests，
未聲稱完成外部 Maps 實景／真節點／警報實機驗證。版本欄位本機為 null，不假造 Render commit。

本機少量 SQLite 合成樣本有 0 ms 與約 15–16 ms 離散值；這組資料不能用來定位 Render／
PostgreSQL／Android 瓶頸或宣稱生產效能。後續應優先同步觀察 queue＋CPU、fusion＋DB waits、
compute＋solver、broadcast＋client handler，詳見 runbook 的假設與判讀限制。


## 最新 staging smoke test

2026-09-28 已將 staging service 切換至 `feat/latency-diagnostics-staging` 並手動部署成功。Render deploy `dep-dat0ienpn0mc73adjthg` 顯示 `Deploy succeeded | Live`，來源 commit `9480807aeea1c3662c2287e695c6c5373d3ad521`。`/health` 與 `/runtime-status` 回 200；`build.render_git_commit`、branch 與 service name 均對應本次 staging；`latency_diagnostics` 結構存在且 `sample_window=256`，初始 stages／pending maps 為空。`/dashboard` 回 200，Render logs 顯示 Uvicorn startup complete、WebSocket accepted、runtime-status／health／dashboard／events／device-status／tracks 均成功，未見 exception、OOM 或 restart。

本次部署依使用者後續指示執行；staging DB 與 production DB 的隔離仍未獨立確認。未送入真實事件流量，故尚無 staging latency percentiles 或效能瓶頸結論。
## 未完成與交付

- Render staging：已部署並完成 smoke test。服務為 `https://sound-backend-staging.onrender.com`，service `sound-backend-staging`，service ID `srv-da6kdn61egvs7392r92g`。部署 `dep-dat0ienpn0mc73adjthg` 使用 commit `9480807aeea1c3662c2287e695c6c5373d3ad521`、branch `feat/latency-diagnostics-staging`；`/health`、`/runtime-status`、`/dashboard` 與 WebSocket 均正常，`latency_diagnostics` 存在且 sample window 為 256。Render logs 未見 exception、OOM 或 restart。staging DB 與 production DB 隔離仍未獨立確認。
- Android：已找到 `C:\Users\vicku\sound_detector_clean`、staging config 與 `app-staging-release.apk`（186,369,035 bytes，2026-09-04 建置）；config validator 確認 host 是 `sound-backend-staging.onrender.com`、upload/device token 已設定（值未輸出）。Flutter 3.38.5 `flutter test` 為 **93 passed**。本機沒有 `adb`，沒有連線 Android 裝置；30–50 次真實多節點測試未執行，沒有實測效能結論。
- `LATENCY_FIELD_RUNBOOK.md` 提供可執行 staging 步驟、40 episode 計畫、收集格式、
  版本／隔離門檻與分析限制。`tools/collect_latency_diagnostics.py` 只做 GET，
  檢查 full SHA 與 schema、拒絕 redirect、保護既有輸出；CPU／記憶體／DB connection 另由
  Console 或唯讀監控同步記錄，不假裝 collector 已取得這些資料。

修改檔案：

- `main.py`
- `services/latency_diagnostics.py`
- `templates/dashboard_v2_4.html`
- `render.staging.yaml`
- `tests/test_latency_diagnostics.py`
- `tests/test_latency_integration.py`
- `tests/test_latency_collection.py`
- `tests/test_dashboard_v2_2_parity.py`
- `tests/js/test_dashboard_latency.js`
- `tests/js/test_dashboard_node_geometry.js`
- `tools/test_localization_pipeline.py`
- `tools/collect_latency_diagnostics.py`
- `docs/performance/LATENCY_DIAGNOSTICS.md`
- `docs/performance/LATENCY_FIELD_RUNBOOK.md`
- `docs/performance/LATENCY_VALIDATION_REPORT.md`

本報告隨修復 commit 提交。最終完整 SHA 與推送確認列於外部交付報告，避免文件引用自身 hash。




