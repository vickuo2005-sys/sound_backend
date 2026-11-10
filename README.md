# Drone Acoustic Monitoring｜無人機聲學監控系統

此 repository 負責 FastAPI Backend、事件融合、節點狀態、PostgreSQL 歷史資料與 Dashboard。MCU、Wi-SUN 韌體與 Gateway implementation 由各自專案負責。這裡也保留 Android 節點介接協定。

**從零重建功能等價系統 → [FROM_SCRATCH_SETUP.md](docs/FROM_SCRATCH_SETUP.md)**。指南提供單一 Git 歸檔 tag、已驗證的 Python 依賴快照和 13 步驗收流程。重建驗收範圍見 [Feature Matrix](docs/FEATURE_REBUILD_MATRIX.md)。

## Architecture

```text
Microphone → Low-power MCU → Feature processing / AI → Wi-SUN
→ Border Router → Industrial PC / Raspberry Pi Gateway → HTTP / WSS
→ FastAPI → PostgreSQL / Event Fusion / Tracking → Dashboard
```

節點位置與多節點覆蓋區域不等於真實無人機座標。責任邊界與既有 Android 路徑見 [Architecture](docs/ARCHITECTURE.md)。

## Local run

建議 Python 3.11。JS 回歸測試使用 Node.js 20。以下使用本機 SQLite。完整命令與 PostgreSQL profile 見 [Local Development](docs/LOCAL_DEVELOPMENT.md)。

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-dev.txt
.\.venv\Scripts\python.exe tools/run_local.py --port 8786
```

開啟 [本機 Dashboard](http://127.0.0.1:8786/dashboard)。`.local-runtime/` 包含本機憑證，不得加入 Git。未配置地圖時可用模擬相對座標圖；SQLite 不代表 PostgreSQL 完整驗證。

## Deployment

先建立自己的空庫與 runtime env，再建立 HTTPS／WSS Web Service。 [Deploy From Scratch](docs/DEPLOY_FROM_SCRATCH.md)

## API

[API Contract](docs/API_CONTRACT.md) 包含事件、節點、固定位置、歷史軌跡與 HTTP／WSS 協定。Gateway 的 `POST /api/test-gateway` 是授權後的 JSON 連通性 echo，**不寫入事件 DB**，不能當作正式 ingest 或持久化 ACK。

## Demo / Research status

正式監控可展示節點、分類結果、事件、可用音訊證據、多節點事件群組、歷史軌跡、據點／警戒圈與 CSV。Simulation Lab 可展示自訂場景、Alpha-Beta、Kalman CV 比較、預測、ETA、警示與回放。

**Simulation 是模擬；Kalman CV 僅作 comparison/shadow。正式 Demo 的 ETA／Approach／Alert 沿用既有 Alpha-Beta 邏輯，未完成實地驗證。** repo 雖有 TDOA 原型，尚未完成硬體同步與真實 acoustic TDOA 定位鏈路。

## Documentation

- [文件入口](docs/README.md)／[10 分鐘交接](docs/HANDOFF.md)
- [Demo baseline](docs/DEMO_BASELINE_2026-11-07.md)／[部署與 rollback](docs/DEPLOYMENT.md)
- [研究狀態](docs/RESEARCH_STATUS.md)／[測試方式](docs/TESTING.md)
- [Repository inventory](docs/REPOSITORY_INVENTORY.md)
- [Branch archive plan](docs/BRANCH_ARCHIVE_PLAN.md)／[Code archive plan](docs/CODE_ARCHIVE_PLAN.md)
- [重建驗證結果](docs/REBUILD_VALIDATION.md)／[系統驗收表](docs/SYSTEM_ACCEPTANCE_CHECKLIST.md)
