# 文件入口

更新於 2026-11-10（Asia/Taipei）。

**從零重建功能等價系統 → [FROM_SCRATCH_SETUP.md](FROM_SCRATCH_SETUP.md)**。從公開 repository checkout 一個 Git 歸檔 tag，即可取得 Demo 原始碼、重建文件和依賴快照。重建時使用自己建立的資源。正式 Demo 的帳號與部署座標見歷史參考。

## Rebuild Instructions

| 文件 | 用途 |
|---|---|
| [FROM_SCRATCH_SETUP](FROM_SCRATCH_SETUP.md) | 歸檔 tag、安裝依賴和 13 步重建流程 |
| [ENVIRONMENT_REFERENCE](ENVIRONMENT_REFERENCE.md) | 原始碼掃描的 runtime 設定、預設與故障行為 |
| [DATABASE_SETUP](DATABASE_SETUP.md) | 空 PostgreSQL／Supabase、migration 順序與 schema 驗證 |
| [STORAGE_SETUP](STORAGE_SETUP.md) | 新 GCS／IAM／Maps 與降級行為 |
| [LOCAL_DEVELOPMENT](LOCAL_DEVELOPMENT.md) | Windows／Linux／macOS 本機指令 |
| [DEPLOY_FROM_SCRATCH](DEPLOY_FROM_SCRATCH.md) | 新 Render／generic HTTPS 與 WSS hosting |
| [FIRST_NODE_GUIDE](FIRST_NODE_GUIDE.md) | 第一個節點 hello、heartbeat 與 Dashboard WS |
| [FIRST_EVENT_GUIDE](FIRST_EVENT_GUIDE.md) | 最小 HTTP event、DB／Dashboard、融合及軌跡 |
| [SYSTEM_ACCEPTANCE_CHECKLIST](SYSTEM_ACCEPTANCE_CHECKLIST.md) | Core／Simulation／選用／研究驗收 |
| [FEATURE_REBUILD_MATRIX](FEATURE_REBUILD_MATRIX.md) | 每個功能的依賴與測法 |
| [REBUILD_VALIDATION](REBUILD_VALIDATION.md) | 從零驗收證據、外部資源及待驗收缺口 |
| [requirements-rebuild-2026-11-09.txt](../requirements-rebuild-2026-11-09.txt) | Windows Python 3.11.9 的 baseline reproducibility snapshot |

## Current Baseline / Historical Reference

| 文件 | 用途 |
|---|---|
| [HANDOFF](HANDOFF.md) | 10 分鐘了解現況、禁區與下一步 |
| [DEMO_BASELINE_2026-11-07](DEMO_BASELINE_2026-11-07.md) | 正式 commit、展示範圍、flags、smoke、回退點 |
| [ARCHITECTURE](ARCHITECTURE.md) | 系統邊界、Backend 模組與資料流 |
| [DEPLOYMENT](DEPLOYMENT.md) | 既有 Demo 的 staging-first、promotion、Render 與 rollback 參考 |
| [API_CONTRACT](API_CONTRACT.md) | HTTP／WSS、Gateway、冪等、ACK／retry |
| [RESEARCH_STATUS](RESEARCH_STATUS.md) | Implemented／Simulation-only／Not field validated／Future work |
| [TESTING](TESTING.md) | Python／JS／CI、runtime smoke、驗證界限 |
| [REPOSITORY_INVENTORY](REPOSITORY_INVENTORY.md) | baseline、模組、tests、services、歷史脈絡 |
| [BRANCH_ARCHIVE_PLAN](BRANCH_ARCHIVE_PLAN.md) | 全部 26 個既有遠端分支、合併關係與保留／刪除候選 |
| [CODE_ARCHIVE_PLAN](CODE_ARCHIVE_PLAN.md) | KEEP／REVIEW／LIKELY ARCHIVABLE／DO NOT TOUCH |
| [ARCHIVE_VALIDATION_2026-11-07](ARCHIVE_VALIDATION_2026-11-07.md) | 本次檢查結果、證據來源與未執行項目 |

## Research Status

研究原型、Simulation-only、真實定位／ETA 待驗證項目以 [Research Status](RESEARCH_STATUS.md) 為準。[`archive/`](archive/) 與 [`release_notes/`](release_notes/) 保留當時證據與適用範圍。

## 既有深入文件

- [監控粗略區域契約](architecture/final_system_architecture.md)
- [Simulation Lab 隔離與 proxy 定位](dashboard/DASHBOARD_MAP_AND_SIMULATION_LAB.md)
- [模擬 ETA 穩定策略](dashboard/SIMULATION_LAB_ETA_STABILITY.md)
- [Classification v1](backend_intelligence/BI1_CLASSIFICATION_CONTRACT.md)
- [Consumer 冪等與跨系統限制](event_consumer_idempotency.md)
- [Observation 離線重送與記憶體冪等限制](architecture/observation_offline_retry.md)

不在文件存放 DB URL、密碼、token、私鑰、signed audio URL 或完整環境匯出。保留舊檔不表示已完成全 Git 歷史 secret audit。
