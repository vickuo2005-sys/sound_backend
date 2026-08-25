# Current Database Migration Plan

Date: 2026-07-24  
Target database: existing Supabase development/integration project

## Precheck Status

`tools\migration_precheck.sql` was not executed from this machine because:

- `DATABASE_URL` is not present in the local environment.
- `psql` is not installed or available on PATH.
- Supabase CLI is not installed or available on PATH.

No schema-changing SQL was executed.

Before applying any migration, run `tools\migration_precheck.sql` in Supabase SQL Editor against the existing Supabase project and compare the output with this plan.

## Read-Only Evidence Available

The existing Render API was queried through read-only endpoints:

| Endpoint | Result |
| --- | --- |
| `/events` | 200, returns timing, smart-audio, and time-sync fields |
| `/event-groups` | 200, returns event group rows |
| `/event-groups/{id}` | 200, returns observation snapshot rows |
| `/device-status` | 200, returns node status and time-sync fields |
| `/time-sync` | 200 |
| `/localization-results` | 200, returns localization result rows |
| `/tracks` | 200, returns active tracking rows |
| `/nodes/live` | 200, returns live node connection rows |
| `/audio-streams` | 200, returns live audio stream session rows |

API evidence can show what the deployed backend selects, but it is not a full schema inventory. The final decision must use Supabase precheck output.

## Migrations Already Effectively Represented

Based on read-only API evidence, the following are effectively present:

| Migration | Evidence | Status |
| --- | --- | --- |
| `v2_1_remote_node_management.sql` | `device_status` returns `is_listening`, `upload_mode`, `last_command_id`, status fields | Effectively applied |
| `v3_0_event_fusion_tracking.sql` | `/event-groups` and `/event-groups/{id}` return groups and observations | Effectively applied |
| `v3_1a_timing_metadata.sql` | `/events` and observations return PCM sample timing fields | Effectively applied |
| `v3_1b_smart_audio_upload.sql` | `/events` and observations return `audio_format`, `audio_size_bytes`, `tdoa_clip_*` fields | Effectively applied |
| `v3_2_time_sync.sql` | `/events` and `device_status` return `time_sync_*` and `corrected_arrival_time_ms` fields | Effectively applied for exposed fields |
| `v3_3_localization.sql` | `/localization-results` returns 200 and localization rows | Effectively applied for exposed API surface |
| `v3_4_hybrid_localization.sql` | Localization API and observation clip fields are exposed | Effectively applied for exposed API surface |
| `v4_final_realtime.sql` | `/nodes/live` and `/audio-streams` return 200 | Effectively applied for exposed API surface |
| `v4_final_tracking.sql` | `/tracks` returns 200 and track rows | Effectively applied for exposed API surface |

## Migrations Requiring Precheck Confirmation

| Migration | Why confirmation is required |
| --- | --- |
| `v4_final_localization.sql` | API evidence shows localization is running, but Supabase precheck is still the authoritative way to confirm every final index and optional pairwise table. |
| Any future additive migration | Run precheck first to avoid duplicate tables, duplicate indexes, or incompatible historical columns. |

## Do Not Blindly Run

Do not blindly run older or duplicate migrations just because they appear in chronological order.

| Migration | Reason |
| --- | --- |
| `v4_0_tracking.sql` | Superseded by `v4_final_tracking.sql`. If `target_tracks` does not exist, prefer `v4_final_tracking.sql` so UUID defaults are created correctly. |
| Already represented `v2.1`, `v3.0`, `v3.1a`, `v3.1b`, `v3.2`, `v3.3`, `v3.4`, and V4 realtime/tracking layers | API evidence indicates their exposed fields/tables exist. Re-run only if precheck shows missing columns/indexes. |

## Exact Execution Order After Precheck

Only run the items whose target tables/columns/indexes are missing in the Supabase precheck output.

1. `migrations/v3_3_localization.sql`
   - Affects: `event_groups`, `localization_results`
   - Run if: `localization_results` missing, localization columns missing, or localization indexes missing.
   - Conflict risk: low to medium; additive, but unique index on `input_signature` must not conflict with duplicate non-null values.

2. `migrations/v3_4_hybrid_localization.sql`
   - Affects: `localization_results`, `event_group_observations`
   - Run if: hybrid method/index columns or `event_group_observations_clip_idx` missing.
   - Conflict risk: low; additive/index-only.

3. `migrations/v4_final_realtime.sql`
   - Affects: `device_connections`, `device_commands`, `audio_stream_sessions`
   - Run if: realtime node tables are missing or command lifecycle columns are missing.
   - Conflict risk: medium; depends on existing `device_commands` column names and status semantics.

4. `migrations/v4_final_localization.sql`
   - Affects: `event_groups`, `localization_results`, `localization_pair_results`
   - Run if: final localization columns/table/indexes are missing.
   - Conflict risk: medium; check FK compatibility and whether `localization_results.input_signature` has duplicates before unique index creation.

5. `migrations/v4_final_tracking.sql`
   - Affects: `target_tracks`, `target_track_points`
   - Run if: target tracking tables or columns are missing.
   - Conflict risk: medium; if old `v4_0_tracking.sql` was already applied, verify UUID `id` defaults and add them manually if missing before relying on app inserts.

## Tables And Columns To Inspect In Precheck

Minimum tables:

- `events`
- `device_status`
- `device_commands`
- `event_groups`
- `event_group_observations`
- `localization_results`
- `localization_pair_results`
- `target_tracks`
- `target_track_points`
- `device_connections`
- `audio_stream_sessions`

Key checks:

- `events`: timing fields, smart-audio fields, `time_sync_*`, `corrected_arrival_time_ms`
- `event_group_observations`: timing fields, smart-audio fields, `time_sync_*`, `corrected_arrival_time_ms`, `tdoa_used`, `tdoa_residual_m`
- `device_status`: command/status fields, `time_sync_*`
- `device_commands`: `command_type`, `args_json`, `issued_at_ms`, `expires_at_ms`, `idempotency_key`, `acked_at`, `result_at`, `delivery_channel`, `delivery_attempts`
- `localization_results`: final localization fields and `input_signature` index
- `localization_pair_results`: pairwise GCC-PHAT result fields
- `target_tracks` and `target_track_points`: tracking fields and UUID defaults
- `device_connections` and `audio_stream_sessions`: realtime node/live-audio fields

## Stop Point

Use this document as a future schema-drift checklist. Before executing any additional schema-changing SQL, first run `tools/migration_precheck.sql` in Supabase SQL Editor and compare the output against the API evidence above.
