# Supabase Tokyo → Singapore Schema Rehearsal Report

Date: 2026-09-30  
Branch: `feat/latency-diagnostics-staging`  
Scope: staging only; read-only live catalog inspection and repository rehearsal audit.

## Decision

**SCHEMA_REHEARSAL = NO-GO**

Singapore schema rehearsal was not executed. The destination project is still empty (`public` has 0 base tables), and no staging DSN was present in the local process environment for a controlled migration run. No runtime data, Render `DATABASE_URL`, production service, or Tokyo schema was changed.

## 1. Tokyo live schema inventory

The Tokyo staging project is `sound-detector-staging` in `ap-northeast-1`. The live public base-table inventory contains 12 tables:

`audio_stream_sessions`, `device_commands`, `device_connections`, `device_locations`, `device_status`, `event_group_observations`, `event_groups`, `events`, `localization_pair_results`, `localization_results`, `target_track_points`, and `target_tracks`.

Known live row counts from the read-only catalog pass are:

| table | rows |
|---|---:|
| audio_stream_sessions | 0 |
| device_commands | 13 |
| device_connections | 0 |
| device_locations | 4 |
| device_status | 4 |
| event_group_observations | 372 |
| event_groups | 183 |
| events | 375 |
| localization_pair_results | 0 |
| localization_results | 0 |
| target_track_points | 90 |
| target_tracks | 17 |

`target_tracks` is `public.target_tracks`, a base table (`relkind = r`) with 17 rows. Its primary key is `id` (UUID, default `gen_random_uuid()`). The live columns are `id`, `label`, `status`, `origin_lat`, `origin_lng`, `created_at`, `updated_at`, `first_event_time_ms`, `last_event_time_ms`, `point_count`, `last_lat`, `last_lng`, `last_speed_mps`, `last_heading_deg`, `last_confidence`, `velocity_east_mps`, `velocity_north_mps`, and `closed_at`. Its indexes are `target_tracks_pkey` and `target_tracks_status_label_idx`. The FK `target_track_points.track_id → target_tracks.id` references it.

The previous visible result omitted `target_tracks` because the accessibility output was truncated after the first visible rows; a direct catalog query now returns it. The earlier SQL filter was not excluding the table.

Sequences observed: `device_commands_id_seq` start 1, increment 1, last value 13; `events_id_seq` start 1, increment 1, last value 532. Sequence last values are runtime state and are intentionally not applied to Singapore in this rehearsal.

## 2. Catalog objects

Tokyo has these extensions: `pg_stat_statements` 1.11, `pgcrypto` 1.3, `plpgsql` 1.0, `supabase_vault` 0.3.1, and `uuid-ossp` 1.1. Public function count is 0. Public user-defined trigger count is 0. All inspected public tables have RLS disabled and forced RLS disabled; `pg_policies` returned 0 rows. Relevant table-grant grantees are `anon`, `authenticated`, `postgres`, and `service_role`; grants are broad and must be reviewed before any cutover.

Views, materialized views, enum types, and non-public provider-managed objects require a schema-only dump or a DSN-based catalog export for a complete definition-level comparison. No schema-only dump was produced because `pg_dump` is unavailable in the workspace and no DSN was placed in the local environment.

## 3. Repository migration replay audit

The 18 migration files were inspected in filename order. The static audit is in `outputs/repository_migration_audit.json`.

Findings:

- `v3_0_event_fusion_tracking.sql` contains `UPDATE` statements. Those are not appropriate for a schema-only rehearsal and were not run.
- `v4_0_tracking.sql` and `v4_final_tracking.sql` overlap on tracking objects and require ordered review.
- Localization migrations (`v3_3`, `v3_4`, `v4_final_localization`, `v4_region_localization`) evolve overlapping objects and are not proven replay-equivalent without a catalog diff.
- Most DDL is additive and uses `IF NOT EXISTS`; this does not prove matching defaults, indexes, constraints, grants, triggers, or provider-managed objects.
- No `DROP`, `TRUNCATE`, or destructive `ALTER ... DROP` statement was executed.

Conclusion: repository migrations alone are **not proven sufficient** to reconstruct the exact Tokyo schema.

## 4. Singapore rehearsal and object diff

Singapore project `sound-detector-staging2` in `ap-southeast-1` currently has 0 public base tables. Therefore:

- MATCH: none established.
- MISSING_IN_SINGAPORE: all 12 application tables listed above.
- EXTRA_IN_SINGAPORE: none observed.
- Column/PK/FK/index/sequence/function/trigger/RLS equivalence: not established because the destination schema was not created.
- Destination row counts are expected to remain 0; this is not a schema failure by itself.

The aggregate metadata artifact is [tokyo_singapore_schema_diff.json](../../outputs/tokyo_singapore_schema_diff.json). It contains no credentials or row contents.

## 5. FK dependency graph

Parent-to-child order for a future data copy is:

1. `events` → `event_group_observations`
2. `event_groups` → `event_group_observations`, `localization_results`, `localization_pair_results`, `target_track_points`
3. `localization_results` → `localization_pair_results`, `target_track_points`
4. `target_tracks` → `target_track_points`
5. `device_locations`, `device_status`, and `device_commands` have no application FK edge in the inspected graph.

No data copy was attempted.

## 6. Sequence, RLS, grants, and provider objects

Sequence state was recorded only as metadata; no `setval` was run. RLS is disabled on inspected public tables and no public policies were returned. `anon`, `authenticated`, `postgres`, and `service_role` appear in table grants; role passwords and secrets were not read or copied. `pgcrypto` is required for UUID defaults. `pg_stat_statements`, `supabase_vault`, and `uuid-ossp` are provider/project extensions that require destination review before cutover.

## 7. Read-only verifier

`tools/verify_db_migration.py` was extended to include column definitions, index definitions, and table-constraint metadata in addition to table summaries, PKs, sequences, FKs, and orphan counts. It still emits aggregate metadata only and never emits DSNs or row contents.

## 8. Data migration readiness

**NOT READY.** The destination has no schema, no data was moved, and the live FK/extension/grant catalog still needs a controlled schema-only comparison. The next safe step is to place staging-only DSNs in the operator environment, run `pg_dump --schema-only --no-owner --no-privileges` for Tokyo, apply only reviewed non-DML schema statements to Singapore, then rerun catalog diff. Do not set sequence values or copy runtime rows during that rehearsal.

## 9. Safety record

- Production touched: no.
- Render `DATABASE_URL` changed: no.
- Tokyo schema modified: no.
- Runtime data copied: no.
- Destructive SQL executed: no.
- Localization/TDOA enabled: no.
- PR merged: no.

## Artifacts and validation

- `outputs/tokyo_singapore_schema_diff.json`
- `outputs/repository_migration_audit.json`
- `outputs/staging_region_inventory_20260930.json`
- `python -m py_compile tools/verify_db_migration.py` passed.
- Full repository pytest baseline remains `320 passed, 3 warnings` from the prior validation; this change did not alter application runtime behavior.

## Latest schema-only rehearsal preflight (2026-09-30)

Preflight was executed locally and stopped safely: TOKYO_STAGING_DSN available = no, SINGAPORE_STAGING_DSN available = no, pg_dump version = unavailable, and psql version = unavailable. Per the runbook, no dump, schema replay, Singapore DDL, catalog diff, or verifier run was attempted. The three new JSON artifacts record NOT_COLLECTED/NOT_RUN status without credentials. SCHEMA_REHEARSAL = NO-GO; DATA_MIGRATION_READY = NO.
