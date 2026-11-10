# Branch archive plan｜先盤點，不刪除

快照日期：2026-11-07。盤點原有 **26 個遠端 branches**（不包含本次新 docs branch），讀取完整 462 筆可達 commit 記錄並對所有 branch 執行 ancestry、ahead／behind 與 patch-equivalence 比較。`origin/HEAD` 是 symbolic ref，不計為第 27 個 branch。

比較基準為 production `01f35377bcb1314d9f7f879d015920f79c9297f5`。19 個 heads 可由 production 到達（包含 production 自己），7 個 branch 不在 production ancestry；「合併」是 Git ancestry，不等於對應 PR 已關閉。獨有 patches 為 `git cherry production branch` 的 `+` 筆數，不是檔案數。

**本計畫不刪 branch、不 force push、不 rebase／rewrite history，也不移動 backup refs。**

## 完整 branch inventory

Behind／ahead 是 production...branch 的左右 commit 數。完整 SHA 保留以便維護者重新核對。

| Branch | Head SHA | Behind / ahead | Production ancestor | 獨有 patches | 分類與原因 |
|---|---|---:|---|---:|---|
| `backup/production-pre-demo-20261107` | `5babe2bafaffbb77b48d16a5e1675f202ae7286b` | 264 / 0 | 是 | 0 | KEEP BACKUP：immutable rollback／研究保留點，不移動不刪除 |
| `backup/production-pre-ui-polish-20261107` | `0c162b5cdb452a7e48efd62da94c663b921a3afd` | 11 / 0 | 是 | 0 | KEEP BACKUP：immutable rollback／研究保留點，不移動不刪除 |
| `backup/wisun-gateway-test-20261107` | `1233e58145b86c506e1fb8fb9baffea167033a5d` | 51 / 0 | 是 | 0 | KEEP BACKUP：immutable rollback／研究保留點，不移動不刪除 |
| `demo-stable-v1` | `4a32f01c857981fbc2e8e4f1f93bf63475e5ab19` | 34 / 0 | 是 | 0 | KEEP：Demo 里程碑，CI push 觸發 branch |
| `feat/drone-benchmark-backend-v1` | `f70d030c7306393aec7fc7af95ee0900ce6d1ae4` | 51 / 4 | 否 | 4 | REVIEW / KEEP：尚有獨有 patch；open PR #7 head |
| `feat/drone-benchmark-flutter-v1` | `192dace8121674145f4eff810490cbd75aac9d96` | 386 / 6 | 否 | 6 | REVIEW / KEEP：尚有獨有 patch；open PR #8 head |
| `feat/event-driven-pipeline-v1` | `c57c0260ecdaee5f3d514e184a75bd929092ab8a` | 92 / 0 | 是 | 0 | LIKELY SAFE LATER：已為 production ancestor；完成下方 gates 後才由使用者決定 |
| `feat/event-driven-redis-staging-shadow` | `99a036b453cea9290eed989f19d05c7a5d01658d` | 88 / 0 | 是 | 0 | KEEP REFERENCE：CI pull_request base，且為 open PR #6 base；先保留 |
| `feat/event-driven-redis-validation` | `a12a32b8b9dd38a8b3c58c2e9b291f1e508b0af6` | 91 / 0 | 是 | 0 | LIKELY SAFE LATER：已為 production ancestor；完成下方 gates 後才由使用者決定 |
| `feat/flutter-node-realtime-detection` | `e3cd84929348e8f04b69e7fc9f627765c1fa9369` | 386 / 1 | 否 | 1 | REVIEW / KEEP：尚有獨有 patch；open PR #8 base |
| `feat/latency-diagnostics` | `75ee0d122c555c449faab8d3bdbffd2697eb03c6` | 147 / 1 | 否 | 1 | REVIEW / KEEP：尚有獨有 patch |
| `feat/latency-diagnostics-staging` | `afe4501f627040ec40295ceb64b81681b3e515d0` | 99 / 0 | 是 | 0 | KEEP REFERENCE：render.staging.yaml 宣告來源，且為 open PR #5 head；先保留 |
| `feat/latency-diagnostics-v1` | `6f8de6444e0542c1007ecf0d11bf814ce556557e` | 147 / 5 | 否 | 5 | REVIEW / KEEP：尚有獨有 patch |
| `feat/sim-alpha-beta-tracking` | `be17970c4a793b89d59435f612e07036beaf4868` | 149 / 0 | 是 | 0 | LIKELY SAFE LATER：已為 production ancestor；完成下方 gates 後才由使用者決定 |
| `feat/staging-latency-diagnostics` | `608fab84b2a8787b8c163c13716bd3b8bba37ec8` | 147 / 11 | 否 | 11 | REVIEW / KEEP：尚有獨有 patch |
| `feat/v2-4-dashboard-simulation` | `e7eb351e4ffe9c66c59c7392d39440f98c074885` | 142 / 0 | 是 | 0 | KEEP REFERENCE：open PR #5 base；先保留，不因 ancestry 已合併就刪除 |
| `fix/dashboard-alert-map-latency` | `48705eb4817fa53f97ece896df11fd5d21b4e8ba` | 2 / 0 | 是 | 0 | KEEP：開發 staging branch，open PR #6 head／#7 base |
| `fix/dashboard-snapshot-event-race` | `bf2268c088d0dc22ecb938eb98b7685440ce8cfb` | 148 / 0 | 是 | 0 | LIKELY SAFE LATER：已為 production ancestor；完成下方 gates 後才由使用者決定 |
| `fix/history-replay-context` | `b391914fee59134c5bad64bd16b9cf30e9436886` | 148 / 0 | 是 | 0 | LIKELY SAFE LATER：已為 production ancestor；完成下方 gates 後才由使用者決定 |
| `fix/live-simulation-parity` | `f0cf3b2bc050da290459159cecbd1166a86f51ad` | 143 / 0 | 是 | 0 | LIKELY SAFE LATER：已為 production ancestor；完成下方 gates 後才由使用者決定 |
| `fix/live-site-icon-simulation-parity` | `0866730e0d4765df695f651640677938411eb0db` | 147 / 6 | 否 | 4 | REVIEW / KEEP：尚有獨有 patch |
| `main` | `f547b629fd278314cadb14ca2b50a27d0954d6a6` | 386 / 0 | 是 | 0 | KEEP：GitHub default branch／歷史主線，open PR #1 base |
| `staging` | `01f35377bcb1314d9f7f879d015920f79c9297f5` | 0 / 0 | 是 | 0 | KEEP：production 部署 branch，open PR #1 head |
| `staging-dashboard-v2-4` | `f5fed558353314e813a6781c0ceb107afa93ee91` | 253 / 0 | 是 | 0 | LIKELY SAFE LATER：已為 production ancestor；完成下方 gates 後才由使用者決定 |
| `staging-dashboard-v2-4-1-node-control` | `f92b3c224e178e7a919162a9284be0d37c05c9e2` | 251 / 0 | 是 | 0 | LIKELY SAFE LATER：已為 production ancestor；完成下方 gates 後才由使用者決定 |
| `validate/v2-4-bi1-5-classification-staging` | `d125786ad6ea7870dcd80d21b982f7b7ec472dbe` | 256 / 0 | 是 | 0 | LIKELY SAFE LATER：已為 production ancestor；完成下方 gates 後才由使用者決定 |

## 分類結論

- **持續保留**：`staging`、`fix/dashboard-alert-map-latency`、`main`、`demo-stable-v1` 及三個 `backup/*`。backup 不因已被合併就變成可刪。
- **被工具／PR 引用，先保留**：`feat/event-driven-redis-staging-shadow`、`feat/latency-diagnostics-staging`、`feat/v2-4-dashboard-simulation`。
- **未合併／實驗，保留並 review**：兩個 `feat/drone-benchmark-*-v1`、`feat/flutter-node-realtime-detection`、`feat/latency-diagnostics`、`feat/latency-diagnostics-v1`、`feat/staging-latency-diagnostics`、`fix/live-site-icon-simulation-parity`。其中最後一個 ahead 6 commits、仍有 4 個獨有 patches，不能只看名稱或畫面類似就認定已合併。
- **obsolete／superseded 候選，共 9 個**：`feat/event-driven-pipeline-v1`、`feat/event-driven-redis-validation`、`feat/sim-alpha-beta-tracking`、`fix/dashboard-snapshot-event-race`、`fix/history-replay-context`、`fix/live-simulation-parity`、`staging-dashboard-v2-4`、`staging-dashboard-v2-4-1-node-control`、`validate/v2-4-bi1-5-classification-staging`。這些已進 production ancestry、沒有獨有 patches，目前未出現在本次查到的 open PR head／base；仍需外部引用與 owner 確認。

所有「likely safe」都只表示程式歷史已包含，不保證外部 Render／CI／人員工作流程不再使用。實際 inactive 狀態未由 branch 年齡推定。

## Open PR 與設定引用快照

| PR | Head → base | 對清理的影響 |
|---|---|---|
| [#1](https://github.com/vickuo2005-sys/sound_backend/pull/1) | staging → main | 不在本次 merge／close／改 base |
| [#5](https://github.com/vickuo2005-sys/sound_backend/pull/5) | feat/latency-diagnostics-staging → feat/v2-4-dashboard-simulation | 兩端即使已為 production ancestor，先保留 |
| [#6](https://github.com/vickuo2005-sys/sound_backend/pull/6) | fix/dashboard-alert-map-latency → feat/event-driven-redis-staging-shadow | 現行 workflow 的 PR target，不是 production promotion 目標 |
| [#7](https://github.com/vickuo2005-sys/sound_backend/pull/7) | feat/drone-benchmark-backend-v1 → fix/dashboard-alert-map-latency | 未合併 Backend benchmark 功能，保留 |
| [#8](https://github.com/vickuo2005-sys/sound_backend/pull/8) | feat/drone-benchmark-flutter-v1 → feat/flutter-node-realtime-detection | 外部 client／Flutter 功能歷史，保留 |

[`../.github/workflows/dashboard-fix-validation.yml`](../.github/workflows/dashboard-fix-validation.yml) 還引用兩個 push branch 與舊 PR base；[`../render.staging.yaml`](../render.staging.yaml) 還宣告舊 latency branch。這是獨立待整理工作，不在本次改 CI／Render／PR 狀態。

## 使用者日後決定刪除前的 gates

1. 重新 fetch、記錄 SHA，再核對 ancestry／patch-equivalence；branch 可能已前進。
2. 檢查是否為 default／protected／部署／rollback／open PR head 或 base，以及 GitHub Actions、Render、外部 scripts 與文件引用。
3. 取得 owner 確認，保留可恢復的 immutable SHA／對照表與所需證據；本次不得另行刪除 refs。
4. 只有使用者另行選定並授權後，才做獨立 branch cleanup。不要把本文件當成刪除指令。

可重現的唯讀盤點命令：

```text
git for-each-ref --format="%(refname:short) %(objectname)" refs/remotes/origin
git rev-list --left-right --count origin/staging...origin/<branch>
git merge-base --is-ancestor origin/<branch> origin/staging
git cherry origin/staging origin/<branch>
```

部署與研究狀態見 [Deployment](DEPLOYMENT.md)、[Research status](RESEARCH_STATUS.md)。
