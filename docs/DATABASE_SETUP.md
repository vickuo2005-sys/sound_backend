# 空白 PostgreSQL／Supabase 建庫

本次空庫驗證使用 PostgreSQL 18.6。其他 PostgreSQL／Supabase 版本用同一 migration 與驗收表核對。需要可執行 migration 的 owner／DDL role、`public` schema 和 `pgcrypto`。安裝 `psql` 可直接做建庫與 schema 檢查。雲端選擇自己的 PostgreSQL 或新 Supabase project。Supabase 可依網路選 direct 或 session pooler，使用 Connect 視窗提供的完整 username、host、port 與 TLS 設定。先用同一帳號驗證 `SELECT current_database(), current_user, version();`。 [Supabase 連線方式](https://supabase.com/docs/guides/database/connecting-to-postgres)

## 建立空白資料庫

本機安裝 PostgreSQL server 與 client，啟動本機服務，從 `psql -U postgres -d postgres -W` 登入自己的管理帳號。以下名稱用於隔離重建。`\password` 是 psql 互動命令。

```sql
CREATE ROLE sound_rebuild LOGIN;
\password sound_rebuild
CREATE DATABASE sound_rebuild OWNER sound_rebuild;
```

雲端可以用新專案內預設空 DB 和它的 DDL role。若採分離角色，在 migration 後另配置 app role 的連線、public schema usage、相關 tables 的讀寫及 sequences 權限，並以實際 runtime role 跑 smoke。至少要能建立 `pgcrypto` 或由自己的 DBA 先建立。App 以 libpq／psycopg2 連 SQL，Supabase HTTP anon／service-role key 用不到。

## 在 repo 根目錄套用 migrations

下例存為本機暫存的 `apply_schema.py`，在 repo 根目錄以已安裝 requirements 的 venv 執行。用自己新建空庫的 DSN。設定 `DATABASE_URL` 時沿用該值，否則由 prompt 讀取。程式先檢查應用表是否已存在，再按順序執行。每檔失敗即停止，`v5_1` 保留自己的交易邊界。

```python
import os
from contextlib import closing
from getpass import getpass
from pathlib import Path

import psycopg2

migrations = [
    "v2_0_events_baseline.sql",
    "v2_1_remote_node_management.sql",
    "v3_0_event_fusion_tracking.sql",
    "v3_1a_timing_metadata.sql",
    "v3_1b_smart_audio_upload.sql",
    "v3_2_time_sync.sql",
    "v3_3_localization.sql",
    "v3_4_hybrid_localization.sql",
    "v4_final_realtime.sql",
    "v4_final_localization.sql",
    "v4_final_tracking.sql",
    "v4_1_tracking_metadata.sql",
    "v4_region_localization.sql",
    "v5_device_fixed_locations.sql",
    "v5_1_device_status_split_upload_status.sql",
    "v6_0_bi1_classification.sql",
]
tables = [
    "events", "device_status", "device_locations", "device_commands",
    "event_groups", "event_group_observations", "localization_results",
    "localization_pair_results", "target_tracks", "target_track_points",
    "device_connections", "audio_stream_sessions",
]
dsn = os.environ.get("DATABASE_URL") or getpass("Your new PostgreSQL DSN: ")
if not dsn:
    raise SystemExit("Set the DSN for your new test database")
with closing(psycopg2.connect(dsn)) as connection:
    connection.autocommit = True
    with connection.cursor() as cursor:
        cursor.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename = ANY(%s)", (tables,))
        if cursor.fetchone():
            raise SystemExit("Application tables already exist. Use a new empty database.")
        for name in migrations:
            cursor.execute((Path("migrations") / name).read_text(encoding="utf-8-sig"))
            print("Applied", name)
```

Supabase SQL Editor 也可以逐檔執行同一順序，確認每檔成功後再繼續。這條鏈從 [Phase 4 空庫清單](database/phase4_staging_schema_baseline.md) 加上後續分類 migration。`v3_1_tdoa_timestamp_localization.sql` 是較早的 timestamp 方案，`v4_0_tracking.sql` 為早期 tracking 方案，兩者留作歷史參考。repo 沒有 migration ledger 或自動升級工具。既有 DB 升級要先盤點差異與備份，空庫順序只用於新 DB。

## Schema 驗證

`tools/migration_postcheck.sql` 為唯讀清單。可貼到自己 Supabase SQL Editor，或設定 `PGHOST`、`PGPORT`、`PGDATABASE`、`PGUSER`、`PGSSLMODE` 為新庫，再執行 `psql -X -W -v ON_ERROR_STOP=1 -f tools/migration_postcheck.sql`。逐列檢查 `status` 為 `ok` 及 `pgcrypto_status=ok`。後來的分類欄位要另查。

```sql
SELECT count(*) AS required_tables_present
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_type = 'BASE TABLE'
  AND table_name IN (
    'events', 'device_status', 'device_locations', 'device_commands',
    'event_groups', 'event_group_observations', 'localization_results',
    'localization_pair_results', 'target_tracks', 'target_track_points',
    'device_connections', 'audio_stream_sessions'
  );

SELECT column_name
FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'events'
  AND column_name IN (
    'classification_schema_version', 'model_id', 'model_version',
    'model_label', 'model_confidence', 'operational_class',
    'aircraft_probability', 'drone_subtype', 'class_scores_json'
  )
ORDER BY column_name;

SELECT indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'public'
  AND tablename IN ('events', 'event_group_observations', 'target_track_points');
```

第一個查詢應為 12。第二個與 [分類 migration](../migrations/v6_0_bi1_classification.sql) 對照。第三個確認 event ID 唯一、fusion observation 的部分唯一限制及 track-point 關聯索引。postcheck 也列出 group、device、定位 signature、命令及 live session 索引。資料庫角色驗證後，啟動 app，確認 `/runtime-status.database=postgres`，讀取 events／groups／tracks 並以自己的測試事件驗證 SQL 寫入。

## 啟動行為與重跑

- `DATABASE_URL` 空白時使用工作目錄的 `sound_events.db`（SQLite）。適用於本機快速驗證。
- `DATABASE_URL` 非空時使用 PostgreSQL。連線失敗會留在 PostgreSQL 路徑。程式會為沒有 `sslmode` 的 URL 補上 `require`。
- `POSTGRES_SCHEMA_AUTO_INIT` 預設 `false`。`true` 會在 import `main` 時嘗試內建 DDL，初始化失敗可能被記下後繼續提供 `/health`。本文用顯式 migration，因內建 DDL 與 SQL 清單的表／索引範圍不同。
- 要清空自己的測試環境，先停止測試 app，建立另一個同樣隔離的空 DB 並重跑本頁，或以不同 `--data-dir` 重新建立 SQLite。保留原測試資料庫可供比較。任何刪除都需要另行確認它是可拋棄的測試 DB。
- 既有 production 禁止套空庫順序、開 startup DDL、清除／drop tables、重跑會修補既有資料的 migration，或呼叫測試寫入／admin cleanup／rebuild。
