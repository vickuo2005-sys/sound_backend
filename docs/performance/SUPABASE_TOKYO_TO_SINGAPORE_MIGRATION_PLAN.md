# Supabase Tokyo to Singapore staging migration plan

Status: **READY TO MIGRATE checkpoint not yet approved**  
Scope: `sound-backend-staging` only  
Repository branch: `feat/latency-diagnostics-staging`

This document is an operator plan. No Supabase project is created, no data is copied, no Render environment variable is changed, and no production resource is touched by this change.

## Current architecture and reason for the migration

Render staging runs in Singapore with one Uvicorn worker and the existing application-side `psycopg2.pool.ThreadedConnectionPool` (configured min 1/max 20). The staging database is a Supabase Shared Session Pooler endpoint on port 5432. The confirmed staging Supabase project is in Tokyo (`ap-northeast-1`).

The measured Tokyo baseline is:

| Metric | P50 | P95 |
|---|---:|---:|
| Pool checkout | 0.013 ms | 0.121 ms |
| Warm `SELECT 1` | 71.203 ms | 73.991 ms |
| TCP connect | 71.016 ms | 72.468 ms |
| Transaction `COMMIT` | 71.113 ms | 71.490 ms |
| Physical connect | 424.865 ms | 456.187 ms |
| Server execution (`SELECT 1`) | 0.020 ms | n/a |

The fixed warm RTT is therefore a network/protocol path candidate rather than pool checkout or PostgreSQL execution. The Singapore project must be measured with the same probe before any performance conclusion is accepted.

## Phase 1: inventory before creating anything

The repository contains versioned SQL under `migrations/`:

`v2_0_events_baseline`, `v2_1_remote_node_management`, `v3_0_event_fusion_tracking`, `v3_1_tdoa_timestamp_localization`, `v3_1a_timing_metadata`, `v3_1b_smart_audio_upload`, `v3_2_time_sync`, `v3_3_localization`, `v3_4_hybrid_localization`, `v4_0_tracking`, `v4_1_tracking_metadata`, `v4_final_localization`, `v4_final_realtime`, `v4_final_tracking`, `v4_region_localization`, `v5_1_device_status_split_upload_status`, `v5_device_fixed_locations`, and `v6_0_bi1_classification`.

The tables explicitly used by these migrations and current code are:

- `events`
- `device_status`, `device_locations`, `device_commands`
- `event_groups`, `event_group_observations`
- `localization_results`, `localization_pair_results`
- `target_tracks`, `target_track_points`
- `device_connections`, `audio_stream_sessions`

The backend also references GCS object keys and signed URL metadata in database columns. Audio binaries are not PostgreSQL rows and must not be copied into the database migration.

The inventory operator must run the read-only verifier against Tokyo and, after schema creation, Singapore:

```powershell
$env:TOKYO_STAGING_DSN = '<set locally; never paste or commit>'
$env:SINGAPORE_STAGING_DSN = '<set locally; never paste or commit>'
python tools/verify_db_migration.py `
  --source-dsn-env TOKYO_STAGING_DSN `
  --target-dsn-env SINGAPORE_STAGING_DSN `
  > outputs/staging_db_migration_verification.json
```

The verifier emits only table names, primary-key metadata, row counts, selected min/max timestamp aggregates, sequence metadata, and foreign-key orphan counts. It does not print DSNs or row contents.

The complete remote inventory must additionally record tables, primary/foreign/unique constraints, indexes, sequences/identity, views, functions, triggers, extensions, enum types, materialized views, RLS policies, grants, roles, and migration history from PostgreSQL catalogs or a schema-only dump. Those objects cannot be inferred safely from the application repository alone.

## Phase 2: schema source of truth

The project uses a mixed approach:

1. Versioned SQL migrations are the intended historical source.
2. `main.py` contains a large PostgreSQL auto-init routine with `CREATE TABLE IF NOT EXISTS`, `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`, and index statements.
3. Staging currently sets `POSTGRES_SCHEMA_AUTO_INIT=false`, so startup does not repair or create the schema.
4. Some migrations overlap or supersede earlier definitions (`v4_0_tracking` and `v4_final_tracking`, and multiple localization revisions). This creates schema drift risk if files are replayed in the wrong order or only a subset is run.

Therefore repo migrations alone are **not proven sufficient** to reconstruct the exact live Tokyo schema. A new project should be built from the ordered repository migrations and then compared against a Tokyo `pg_dump --schema-only` snapshot. Any remote-only object must be reviewed before import. `pg_dump --schema-only` is the safety net for ownership, grants, RLS, extensions, sequences, indexes, triggers, views, and functions that are absent from the repository.

### Data classification

**MUST MIGRATE**

- `events` and `event_group_observations` runtime rows
- `event_groups`
- `target_tracks` and `target_track_points`
- `device_status` and `device_locations` if current device state/fixed positions are needed immediately after cutover
- `device_commands` that are still pending, only after deciding whether replay is safe
- `localization_results` and `localization_pair_results` if historical localization records are part of staging verification

**SHOULD MIGRATE**

- `device_connections` and `audio_stream_sessions` only if they are historical/audit data; active sessions should be allowed to expire
- classification persistence columns in `events` and observations
- sequence/identity current values and all non-sensitive metadata needed for referential integrity

**CAN RECREATE**

- empty caches and process-local diagnostics
- active WebSocket/session state after all devices reconnect
- derived dashboards or aggregates that the application explicitly rebuilds
- fixed device locations only when the operator has a separate authoritative fixture and has verified them

**DO NOT COPY**

- production data, credentials, passwords, tokens, roles, or secret environment variables
- GCS binary audio objects into PostgreSQL
- transient active WebSocket sessions
- process-local latency samples and pending counters

GCS object keys and metadata stay unchanged; after cutover, verify the new backend can read the existing staging bucket without moving the binary objects.

## Phase 3: manual Singapore project checklist

An operator must complete these steps in Supabase Dashboard; Codex must not create the project automatically:

1. Create a new project named clearly as staging-only and choose **Singapore / `ap-southeast-1`**.
2. Use a newly generated database password. Store it only in the password manager/Supabase secret UI.
3. Select a compute plan appropriate for staging and record the plan and project reference.
4. Enable the required PostgreSQL extensions found in the Tokyo schema dump, including `pgcrypto` if the UUID defaults are used.
5. Obtain the **Shared Session Pooler** connection string on port `5432`; do not use transaction pooler port `6543` for this application.
6. Review project settings, database SSL requirements, network restrictions, API settings, Auth/Storage settings, and any staging-only GCS integration.
7. Do not paste the password, pooler URI, `DATABASE_URL`, service-role key, or upload token into chat, source, logs, or commits.
8. Keep the Tokyo project running and retain its credentials until the migration is accepted and the rollback window has expired.

## Phase 4: schema migration method

Use this order:

1. Export Tokyo schema only with `pg_dump --schema-only --no-owner --no-privileges` using a local secret environment variable.
2. Apply the ordered repository migrations to Singapore in a disposable rehearsal database or transaction where possible. Do not run destructive statements.
3. Apply only reviewed schema-only objects from the Tokyo dump that are absent from the repository result. Review ownership, grants, RLS, extensions, views, functions, triggers, and materialized views individually.
4. Compare catalog output with `tools/verify_db_migration.py` and a schema diff. Resolve all missing tables, constraints, indexes, sequences, and remote-only objects before data copy.
5. Record the exact dump hash, migration order, target project reference, and operator time in the private change record; put only aggregate results in the repository report.

This combination is more reproducible than using a manual SQL Editor history alone, while the schema-only dump protects against drift. It deliberately does not run `DROP`, `TRUNCATE`, or `ALTER ... DROP` on either project.

## Phase 5: data copy method

For the current staging scale, use a short maintenance-window `pg_dump`/`pg_restore` data copy rather than logical replication:

1. Freeze staging writes and device uploads. Stop test clients and disable any scheduled test traffic.
2. Take a final Tokyo custom-format dump of the approved staging tables, preserving binary JSON/JSONB and timestamps.
3. Restore parent tables before child tables: `events`/`event_groups`/`target_tracks` first, then observations, track points, localization children, device state, and finally optional command/session history.
4. Restore with constraints enabled where practical; otherwise defer only reviewed constraints and validate them before cutover.
5. Restore sequence/identity values with `setval` based on the copied maximum primary key, then verify next values are greater than existing IDs.
6. Preserve NULLs, arrays, JSON/JSONB, time zones, and duplicate keys. Do not use `ON CONFLICT DO NOTHING` as a silent substitute for a failed restore; stop and investigate duplicates.
7. Leave GCS objects in place and verify object-key references only.

Logical replication is unnecessary for the current staging volume and adds slot/publication permissions and cleanup risk. Table-by-table `COPY` is an acceptable fallback only if `pg_dump` cannot be used and the same parent/child, sequence, and integrity checks are retained.

## Phase 6: cutover for staging only

Estimated staging maintenance window: **10–30 minutes**, dependent on row counts and restore speed; measure it during rehearsal rather than treating this as an SLA.

Before cutover:

- confirm the new project and schema verification are green;
- record Tokyo final row counts, timestamp ranges, sequence values, latest event/track IDs, and GCS reference checks;
- freeze writes, take final backup, run final delta copy, and run all integrity checks;
- keep a tested Tokyo `DATABASE_URL` rollback value outside chat and source control.

Cutover:

1. Edit only `sound-backend-staging` in Render.
2. Change only its `DATABASE_URL` to the Singapore Shared Session Pooler URI on port 5432.
3. Redeploy/restart staging and record the deployed commit and timestamp.

After cutover, verify `/health`, `/runtime-status`, database initialization status, event insert/readback, four-node WebSocket connection, Fusion, Tracking, command API, Dashboard, GCS references, and classification persistence. Localization/TDOA remains disabled for this migration benchmark.

## Phase 7: rollback

Rollback triggers include schema errors, missing indexes/tables, insert/read failures, FK violations, event loss, tracking inconsistency, connection failures, or a material latency regression.

1. Stop or disable staging writes briefly if needed.
2. Restore the previous Tokyo `DATABASE_URL` in the staging Render service only.
3. Redeploy/restart staging and verify health/runtime status.
4. Compare events and track IDs around the cutover timestamp.
5. Preserve the Singapore project for diagnosis. Do not delete it until the migration is accepted and the rollback retention period ends.

If writes occurred on Singapore before rollback, do not silently overwrite Tokyo. Export the affected interval and reconcile it explicitly before any later retry.

## Phase 8: integrity checks

Run before and after cutover:

- row count per table;
- min/max timestamp per table where a timestamp column exists;
- primary-key and unique-key counts;
- orphan foreign-key counts;
- sequence/identity next values;
- latest event IDs and latest track IDs;
- representative JSON/JSONB type and key-shape checks without recording values;
- representative device rows and event-group membership counts;
- deterministic checksums only for approved, non-sensitive aggregate projections.

`tools/verify_db_migration.py` is read-only and emits no row contents or secrets.

## Phase 9: latency A/B

Run the existing staging probe unchanged against Tokyo immediately before migration and Singapore immediately after migration. Required sample counts are 50 warm SELECTs, 30 transaction cycles, 30 pool checkouts, 20 TCP connects, and 10 physical connects, plus server-side `EXPLAIN SELECT 1`. Keep the probe disabled except for the bounded collection window.

Use the comparison helper:

```powershell
python tools/run_region_latency_comparison.py `
  --tokyo outputs/tokyo_probe.json `
  --singapore outputs/singapore_probe.json
```

The report must show P50/P95/P99 and change for TCP, warm SELECT, transaction SELECT, COMMIT, and physical connect. Do not add P95 values from different stages together.

For sequential-call amplification, use the measured RTT only as a lower-bound estimate:

```text
serial_lower_bound(N) = N * warm_select_p50_ms
```

Report N = 5, 10, and 15 for each region. This is not an end-to-end prediction.

## Phase 10: real application validation

After Singapore cutover, run the same four-node Android workload used for Tokyo, with localization/TDOA still disabled. Collect at least 30 events, preferably 30–50, and save the process-local `/runtime-status` snapshot after the run. Compare:

`event_db_connection_acquisition`, `event_db_write`, `event_fusion`, `fusion_transaction_sql_ms`, `fusion_transaction_idle_ms`, `region_tracking`, `post_ingest_pipeline`, `post_ingest_queue_wait`, `postgres_pool_acquisition`, `postgres_connection_hold`, and `recent_traces`.

Do not call a small-sample P99 stable. Look for lower Fusion SQL, lower Tracking time, reduced queue wait, lower post-ingest latency, and lower connection-establishment tails.

## Risks and go/no-go

Risks are schema drift, missing remote-only objects, sequence collisions, FK/order errors, GCS reference mistakes, pending command replay, and a region change that does not reduce RTT. The project region and Supabase plan must be confirmed manually; no assumption about provider topology is sufficient.

**GO** only when schema and data checks pass, no orphan FKs exist, sequences are safe, staging smoke tests pass, Tokyo rollback credentials are tested, and Singapore warm/TCP measurements are materially lower than the Tokyo baseline.

**NO-GO** if any table/object is unexplained, restore reports duplicate or missing rows, GCS references fail, the application cannot complete four-node smoke traffic, or the latency improvement is absent. Keep Tokyo active and do not change the staging `DATABASE_URL`.

## Current checkpoint

The Singapore project is now confirmed manually as `sound-detector-staging2` (`jlkjmyhxmwgaalkrpaow`, `ap-southeast-1`). Its Session Pooler host template is `aws-0-ap-southeast-1.pooler.supabase.com:5432`; the password is not viewable from Supabase after creation and has not been handled here. The repository is still at **READY TO MIGRATE: NO** because staging-only DSNs have not been placed in local environment variables, `pg_dump`/`psql` are not installed in this workspace, and the live Tokyo/Singapore catalog inventory is therefore pending. Until those are available, no schema, data, or Render `DATABASE_URL` change is safe.
