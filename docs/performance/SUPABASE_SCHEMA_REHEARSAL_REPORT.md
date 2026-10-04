# Supabase Tokyo → Singapore Schema Rehearsal Report

Date: 2026-09-30  
Branch: `feat/latency-diagnostics-staging`  
Scope: staging only; read-only live catalog inspection and repository rehearsal audit.

## Decision

**SCHEMA_REHEARSAL = PASS (public schema-only rehearsal)**

**DATA_MIGRATION / RENDER CUTOVER = NO-GO (intentionally not executed)**

The public schema-only rehearsal was completed against the two staging projects after a local read-only connection preflight. No runtime data, sequence state, Render `DATABASE_URL`, production service, or Tokyo schema was changed.

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

The full Tokyo schema-only dump was produced locally with PostgreSQL 17.11 (server 17.6). The reviewed rehearsal input was restricted to the `public` schema so Supabase-managed `auth`, `storage`, `realtime`, `vault`, and related provider objects were not replayed. The dump SHA-256 is recorded in the latest run section below; the dump itself is local-only and is not committed.

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

Singapore project `sound-detector-staging2` in `ap-southeast-1` now has the reviewed public schema. Therefore:

- MATCH: all 12 application tables and the public catalog sections compared.
- MISSING_IN_SINGAPORE: none in the compared public schema.
- EXTRA_IN_SINGAPORE: none observed.
- Column/PK/FK/index/sequence/function/trigger/RLS equivalence: matched in the aggregate catalog comparison.
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

**SCHEMA READY; DATA NOT READY.** The destination public schema now matches the compared Tokyo public catalog. Runtime rows were deliberately not copied, sequence values were not set, and Render staging was not cut over. A separate data-copy plan still requires row-level reconciliation, a final FK/sequence check, rollback readiness, and an explicit staging-only cutover decision.

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

The initial preflight record above is historical. A follow-up preflight succeeded using local process-only credentials (never written to the repository): both staging DSNs returned `SELECT 1`, PostgreSQL server version was 17.6, `pg_dump` was 17.11, and `psql` was available. The Tokyo dump was created at `outputs/tokyo_schema_only.sql` with SHA-256 `ffff6612dd76441997184467977de6bb5442ace93945fc5a97d3a06ea4e9c8a6`; a public-only reviewed input was generated at `outputs/tokyo_public_schema_rehearsal.sql`. A destructive/DML scan found no DROP, TRUNCATE, DELETE, UPDATE, INSERT, or COPY statements in the rehearsal input. The public-only DDL applied successfully to Singapore with `ON_ERROR_STOP=1`.

Post-rehearsal catalog comparison in `outputs/tokyo_singapore_schema_diff_after_rehearsal.json` reports PASS for schemas, tables, columns, indexes, constraints, sequences, extensions, policies, triggers, and functions. Tokyo retained its existing rows (for example `events=375`, `event_groups=183`, `event_group_observations=372`); Singapore remains empty for those application tables by design. This is a schema validation result, not a data migration or application cutover result.
