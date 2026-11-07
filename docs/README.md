# 文件入口

更新日期：2026-11-07（Asia/Taipei）。新增的頂層文件描述正式 Demo baseline；舊版架構、release、migration 文件保留原日期作為歷史證據，不自動代表現行部署設定。

| 文件 | 用途 |
|---|---|
| [HANDOFF](HANDOFF.md) | 10 分鐘了解現況、禁區與下一步 |
| [DEMO_BASELINE_2026-11-07](DEMO_BASELINE_2026-11-07.md) | 正式 commit、展示範圍、flags、smoke、回退點 |
| [ARCHITECTURE](ARCHITECTURE.md) | 系統邊界、Backend 模組與資料流 |
| [DEPLOYMENT](DEPLOYMENT.md) | staging-first、promotion、Render 與 rollback |
| [API_CONTRACT](API_CONTRACT.md) | HTTP／WSS、Gateway、冪等、ACK／retry |
| [RESEARCH_STATUS](RESEARCH_STATUS.md) | Implemented／Simulation-only／Not field validated／Future work |
| [TESTING](TESTING.md) | Python／JS／CI、runtime smoke、驗證界限 |
| [REPOSITORY_INVENTORY](REPOSITORY_INVENTORY.md) | baseline、模組、tests、services、歷史脈絡 |
| [BRANCH_ARCHIVE_PLAN](BRANCH_ARCHIVE_PLAN.md) | 全部 26 個既有遠端分支、合併關係與保留／刪除候選 |
| [CODE_ARCHIVE_PLAN](CODE_ARCHIVE_PLAN.md) | KEEP／REVIEW／LIKELY ARCHIVABLE／DO NOT TOUCH |
| [ARCHIVE_VALIDATION_2026-11-07](ARCHIVE_VALIDATION_2026-11-07.md) | 本次檢查結果、證據來源與未執行項目 |

## 閱讀優先順序

1. 以 [Demo baseline](DEMO_BASELINE_2026-11-07.md) 的 immutable commit 與 runtime 核對結果確認版本。
2. 操作與介接從 [Deployment](DEPLOYMENT.md)、[API Contract](API_CONTRACT.md) 開始；遇到矛盾，回看該 commit source，不照抄舊 runbook 執行。
3. [`archive/`](archive/) 與 [`release_notes/`](release_notes/) 是歷史檔案。舊文件中的「final」「validated」只適用當時範圍，不能擴大成真實定位／ETA 實地驗證。

## 既有深入文件

- [監控粗略區域契約](architecture/final_system_architecture.md)
- [Simulation Lab 隔離與 proxy 定位](dashboard/DASHBOARD_MAP_AND_SIMULATION_LAB.md)
- [模擬 ETA 穩定策略](dashboard/SIMULATION_LAB_ETA_STABILITY.md)
- [Classification v1](backend_intelligence/BI1_CLASSIFICATION_CONTRACT.md)
- [Consumer 冪等與跨系統限制](event_consumer_idempotency.md)
- [Observation 離線重送與記憶體冪等限制](architecture/observation_offline_retry.md)

不在文件存放 DB URL、密碼、token、私鑰、signed audio URL 或完整環境匯出。保留舊檔不表示已完成全 Git 歷史 secret audit。
