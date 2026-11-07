# Repository inventory｜2026-11-07

## 範圍與基準

本次新建獨立 checkout，盤點原有 26 個遠端分支、三個 tags、全部 462 筆可達 commit 記錄與 baseline 的 476 個 tracked files。沒有改既有 checkout、merge／delete branch 或部署。

| 用途 | Ref／SHA | 現況來源 |
|---|---|---|
| Production | `staging` → `01f35377bcb1314d9f7f879d015920f79c9297f5` | Git refs、使用者交接、production runtime build 一致 |
| 開發 staging | `fix/dashboard-alert-map-latency` → `48705eb4817fa53f97ece896df11fd5d21b4e8ba` | Git refs 與 staging runtime build 一致 |
| GitHub default | `main` → `f547b629fd278314cadb14ca2b50a27d0954d6a6` | GitHub repository metadata；舊版本，不是 production |
| 本次 docs branch | `docs/demo-baseline-handoff-20261107` | 基於開發 staging，只有 root README／docs |

Production／開發 staging tree 同為 `2b6bd564379d8823d0e6a7760bc09923cac386ee`。Production 比開發 ref 多兩個可達 commits，但不多檔案變更。此次歸檔不把 docs commit 當新 Demo baseline。

## Branches／tags

完整 26 branches、SHA、merged／unique patches、open PR 與清理建議見 [Branch archive plan](BRANCH_ARCHIVE_PLAN.md)。19 個 heads 是 production ancestor（包含 production），7 個未合併 branch 保留；僅列 9 個日後刪除候選，不執行刪除。

Rollback refs：

| Branch | SHA |
|---|---|
| backup/production-pre-demo-20261107 | `5babe2bafaffbb77b48d16a5e1675f202ae7286b` |
| backup/production-pre-ui-polish-20261107 | `0c162b5cdb452a7e48efd62da94c663b921a3afd` |
| backup/wisun-gateway-test-20261107 | `1233e58145b86c506e1fb8fb9baffea167033a5d` |

既有 tags：`v2.4`、`v3.1a.0`、`v3.1b.0`，均保留，不自動改指向 2026-11-07。

## Major modules／tests／API

- FastAPI 與 legacy Dashboard：`main.py`，目前約 17,845 行，是低風險文件整理以外的獨立 refactor 範圍。
- Protocol／node／command／audio：`app/protocol/`、`services/realtime/`。
- Events／fusion／region／tracking：`services/event_fusion.py`、`services/region_localization.py`、`services/tracking/`。
- Research localization／shadow／latency：`services/localization/`、`services/events/`、`services/observation_shadow.py` 與 diagnostics modules。
- V2 frontend：`services/dashboard_v2_4.py`、`templates/dashboard_v2_4.html`、`static/dashboard_*`。
- DB schema／運維／證據：`migrations/`、`tools/`、`docs/`、`outputs/`、`verification/`。
- Tests：56 個 `tests/test_*.py`、10 個 `tools/test_*.py`、28 個 JS files；這是檔案數，非本次重跑結果或 case 數。
- API：48 HTTP＋4 WSS 自訂 decorators。完整列表、schema／ACK／retry 見 [API Contract](API_CONTRACT.md)。

責任邊界見 [Architecture](ARCHITECTURE.md)，候選 legacy／duplicate／experimental 檔案見 [Code archive plan](CODE_ARCHIVE_PLAN.md)。

## Render services／環境 flags

| 資源 | 用途／識別 | 來源與限制 |
|---|---|---|
| `sound_backend` | production，`https://sound-backend.onrender.com` | 使用者交接及 runtime build；branch staging |
| `sound-backend-staging` | 開發 staging，`https://sound-backend-staging.onrender.com` | 使用者交接及 runtime build；branch fix/dashboard-alert-map-latency |
| `sound-backend-staging-shadow-v2b` | 既有 Render Key Value／Valkey staging shadow 資源 | 本次既有對話的 Dashboard 盤點；非正式 authoritative queue，不在本次重新讀取或調整其設定 |

本次沒有登入 Render 讀 secrets 或修改 settings。Region／plan／auto-deploy 不從舊 Blueprint 推定為即時事實。核心 Demo flags、DB 與 auth 設定名稱見 [Deployment](DEPLOYMENT.md)。Production APP_ENV 是 DEMO（runtime `demo`），staging 為 `staging`，兩者 V2／Simulation／Demo Stable 開、experimental motion／localization 關。

## Git history 的主要脈絡

| 時期／commit | 演進與現在應如何解讀 |
|---|---|
| 2026-06 `6de0580`、`906b004`、`1e6dbfb` | Render 起點、PostgreSQL、Dashboard WSS |
| 2026-07 `bcb76b6`、`fb8a152`、`f547b62` | Event Fusion、timestamp-TDOA 原型、time-sync metadata；不是實地完成證明 |
| 2026-07 `004aaf8` | 監控改用多節點 region estimation；不要把節點幾何解讀為 UAV 真值 |
| 2026-08 `5babe2b`、`2031e63` | staging isolation、observation replay／shadow reliability |
| 2026-09 `8d501d4`、`b27d82a`、`bf2268c`、`b391914` | 獨立 Lab、Alpha-Beta、snapshot race 與 replay context |
| 2026-10 `c57c026`、`a12a32b`、`99a036b` | event-driven／Redis validation／shadow；未宣稱正式全面 cutover |
| 2026-11 `9d9a5a1`、`7c4c872`、`ae437bb` | Gateway test、simulation Kalman、Kalman clear 修復 |
| 2026-11 `23410a5` | 修復 nested style 導致 Dashboard CSS 顯示問題，保留回歸 |
| 2026-11 `48705eb`、`01f3537` | 正式展示文案／工程控制收斂與 production UI polish baseline |

原 root README 仍以早期 SQLite-only 簡介為主，已換成精簡入口；歷史版本可由 Git 查看，未重寫歷史。細部歷史文件保留原範圍與日期，不覆寫它們的研究結論。
