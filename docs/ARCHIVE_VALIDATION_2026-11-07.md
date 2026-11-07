# 專案歸檔驗證紀錄｜2026-11-07

此為純文件整理的範圍與證據，不是新的功能 release 或全量 Browser E2E 報告。

## 基準核對

- GitHub metadata：repository 為 `vickuo2005-sys/sound_backend`，default branch `main`。
- Production ref／runtime：`staging`、`01f35377bcb1314d9f7f879d015920f79c9297f5`。
- 開發 staging ref／runtime：`fix/dashboard-alert-map-latency`、`48705eb4817fa53f97ece896df11fd5d21b4e8ba`。
- 兩個 baseline tree 相同：`2b6bd564379d8823d0e6a7760bc09923cac386ee`。
- 盤點原有 26 branches、三個 tags、462 筆可達 commit 記錄、476 個 baseline tracked files。Branches 的 ancestry、ahead／behind、patch-equivalence 與五個既有 open PR 已核對；清理候選仍需使用者另行決定。

## 文件與變更驗證

| 檢查 | 結果與界限 |
|---|---|
| 修改範圍 | 根 README＋12 份 docs Markdown；沒有 source／tests／config／migration 變更 |
| `git diff --check` | 通過；納入新檔後亦檢查 staged／commit diff，避免只檢查已追蹤 README |
| 文件連結 | 本次 13 份新增／修改文件的相對檔案／目錄與 anchor links 通過；舊 docs 全站及外部 URL 不在此保證範圍 |
| API／branch 表 | 52 個自訂 routes、26 個既有 branch rows／完整 SHA 與 baseline inventory 一致 |
| JSON examples | 三個 JSON fences 可解析；示例為合成資料，沒有執行 ingest |
| Secret review | 新增／修改文字未發現所掃描 connection URL、API／GitHub token、JWT、private key、literal secret assignment patterns；人工確認只記設定名稱／非 secret flags／synthetic examples |
| Runtime 行為保留 | 與 production tree 比較，`main.py`、app／services／static／templates／tests／tools／migrations／workflow／requirements／Render manifest 的內容均未變更 |
| Git refs | 原有 branch／backup／tag 未刪除、未移動；不 force push、不 rewrite history；新 docs branch 不更新部署分支 |

Secret check 是本次 diff 的檢查，不是對整個既有 Git 歷史或舊 credential handoff 文件的零 secret 保證。沒有讀取／輸出雲端 DB URL、密碼、token 或憑證，也沒有把 raw API event、audio URL 或完整 runtime snapshot 加入 Git。

## Runtime smoke（本次執行）

2026-11-07 22:51:43 +08:00 開始，兩站各八個 GET endpoints 均為 200，JSON 無 degraded／所篩查 DB connection error pattern，Dashboard HTML 有 V2 workspace；兩站 `/ws/dashboard` handshake 成功。逐 endpoint 結果見 [Demo baseline](DEMO_BASELINE_2026-11-07.md)。

僅做正常 Dashboard 讀取與短暫 Dashboard WSS 連線，沒有 node hello／command／test event／upload／admin／migration。`/tracks` 自帶 stale-track close 維護語義已於 API／Testing 文件說明；沒有額外執行 cleanup 或刪除 API。

本次未做長時間 production logs 審計、全部 Browser 控制操作或真實 Wi-SUN／聲學場域驗證。既有使用者交接的展示結果與本次重新執行的 smoke 已在文件中分開標明。

## Tests／CI 證據

開發 baseline `48705eb` 既有 [push CI](https://github.com/vickuo2005-sys/sound_backend/actions/runs/42382252510)、[PR CI](https://github.com/vickuo2005-sys/sound_backend/actions/runs/42382256973) 均 success。本次沒有重新執行完整 Python／JS suite，也沒有把過去 test totals 當作本次測試數。

因 source／tests 未改，本次重點是文件靜態驗證、API／branch 表一致性、runtime smoke 與 diff scope。新 docs branch／目標開發 branch 不符合既有 workflow 自動觸發條件；未觸發 CI 不能寫成通過。

## 未執行且需另案處理

- 不修改 Render env／settings／branch／build／start／region，不重新部署任何服務。
- 不修改 DB URL／schema／資料，不重新開啟 TDOA 或其他研究旗標。
- 不 merge／close／retarget 既有 PR，不刪任何 branch、檔案或歷史證據。
- 不搬 legacy Dashboard、重複 simulation modules 或 migration tools；只提交 [Code archive plan](CODE_ARCHIVE_PLAN.md)。
- CI 與 Blueprint 的引用落差、七個未合併研究／client branches、場域研究 acceptance 都留作明確的下一步，見 [Handoff](HANDOFF.md)。
