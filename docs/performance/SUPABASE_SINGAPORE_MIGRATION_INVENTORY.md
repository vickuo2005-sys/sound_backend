# Staging database migration inventory

Date: 2026-09-30  
Scope: Tokyo Supabase staging to a future Singapore Supabase staging project  
Status: repository/static inventory complete; live catalog inventory pending operator DSNs

## Configuration and schema behavior

- Render service: `sound-backend-staging`
- Render region: Singapore
- Current Supabase staging region: Tokyo (`ap-northeast-1`)
- Current endpoint: Supabase Shared Session Pooler, port 5432
- New Singapore project confirmed manually: `sound-detector-staging2`, project ref `jlkjmyhxmwgaalkrpaow`, region `ap-southeast-1`
- New Shared Session Pooler host template: `aws-0-ap-southeast-1.pooler.supabase.com:5432` (password intentionally omitted)
- `DATABASE_URL`: Render secret; not present in this workspace and never printed
- `POSTGRES_SCHEMA_AUTO_INIT`: `false` in staging
- Startup therefore logs that PostgreSQL schema initialization is skipped.
- `main.py` still contains a PostgreSQL auto-init routine with additive `CREATE TABLE IF NOT EXISTS`, `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`, and index statements. It is a compatibility fallback, not a migration ledger.

## Repository migration inventory

The ordered migration family currently checked in is:

1. `v2_0_events_baseline.sql`
2. `v2_1_remote_node_management.sql`
3. `v3_0_event_fusion_tracking.sql`
4. `v3_1_tdoa_timestamp_localization.sql`
5. `v3_1a_timing_metadata.sql`
6. `v3_1b_smart_audio_upload.sql`
7. `v3_2_time_sync.sql`
8. `v3_3_localization.sql`
9. `v3_4_hybrid_localization.sql`
10. `v4_0_tracking.sql`
11. `v4_1_tracking_metadata.sql`
12. `v4_final_localization.sql`
13. `v4_final_realtime.sql`
14. `v4_final_tracking.sql`
15. `v4_region_localization.sql`
16. `v5_1_device_status_split_upload_status.sql`
17. `v5_device_fixed_locations.sql`
18. `v6_0_bi1_classification.sql`

The migration files explicitly create or evolve these public tables:

| Table | Role | Migration/runtime evidence |
|---|---|---|
| `events` | uploaded event and classification/timing metadata | v2 baseline, v3.x/v4.x/v6.x, event ingest in `main.py` |
| `device_status` | node status and last event state | v2.1, device status worker |
| `device_locations` | fixed device coordinates | v5, device location APIs |
| `device_commands` | remote command queue | v2.1, command APIs |
| `event_groups` | Fusion and target region groups | v3.0 and localization/region migrations |
| `event_group_observations` | group membership and observations | v3.0 and timing/audio/TDOA migrations |
| `localization_results` | localization result cache/history | v3.3 and v4 final localization |
| `localization_pair_results` | pairwise localization records | v4 final localization |
| `target_tracks` | active/closed tracks | v4 tracking migrations |
| `target_track_points` | track history points | v4 tracking migrations |
| `device_connections` | realtime connection records | v4 final realtime |
| `audio_stream_sessions` | live audio session records | v4 final realtime |

The exact columns, constraints, indexes, views, functions, triggers, enum types, extensions, RLS policies, grants, and roles must be collected from the live Tokyo catalog or a schema-only dump. This workspace cannot safely infer remote-only objects.

## Objects and data classification

### Must migrate

`events`, `event_groups`, `event_group_observations`, `target_tracks`, `target_track_points`, `localization_results`, `localization_pair_results`, and current `device_status`/`device_locations` rows needed for immediate staging validation. Pending commands require an explicit replay decision before copy.

### Should migrate

Classification persistence columns, timing metadata, approved audit history, sequences/identity state, indexes, constraints, RLS, functions, triggers, and grants. Active realtime session rows should be copied only if their historical meaning is confirmed.

### Can recreate

Process-local latency samples, pool counters, WebSocket sessions, in-memory caches, and derived dashboard snapshots. Devices can reconnect and repopulate live status after cutover if fixed locations are preserved separately.

### Do not copy

Production data or credentials, secret environment variables, upload tokens, active session state, or GCS binary objects. Database columns that hold GCS object keys or signed URL metadata must remain references to the existing staging bucket.

## Source-of-truth assessment

The source is mixed: versioned SQL migrations plus raw schema SQL embedded in `main.py`. There is no repository migration table or evidence of a complete remote SQL Editor history. Duplicate/superseding tracking and localization migrations create ordering and drift risk. Because staging auto-init is disabled, a fresh project cannot be declared complete from application startup behavior alone.

Conclusion: **repo migrations alone are not proven sufficient** to rebuild the exact live schema. The safe method is ordered repo migrations plus a reviewed Tokyo `pg_dump --schema-only` reconciliation and a catalog comparison. The migration plan documents the procedure and the cutover checkpoint.

## Live inventory command

Use only staging DSNs stored in local environment variables:

```powershell
python tools/verify_db_migration.py `
  --source-dsn-env TOKYO_STAGING_DSN `
  --target-dsn-env SINGAPORE_STAGING_DSN `
  > outputs/staging_db_migration_verification.json
```

The tool emits aggregate metadata and orphan-FK counts only. It does not emit secrets or row content. Views, functions, triggers, extensions, enum types, materialized views, RLS, grants, and roles still require a schema-only catalog review before GO.
