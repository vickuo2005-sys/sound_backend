# Phase 4 isolated staging schema baseline

This is an execution inventory, not evidence that a database was created or
migrated. Apply SQL only after the Supabase project ref and database host have
both been confirmed as staging and confirmed different from production.

## Fresh-database prerequisite

The historical migration chain assumes `public.events` already exists.
`migrations/v2_0_events_baseline.sql` fills only that prerequisite for a new
staging database. It mirrors the PostgreSQL `events` definition in `main.py`.
It must run before `v3_0_event_fusion_tracking.sql`.

Keep `POSTGRES_SCHEMA_AUTO_INIT=false`; schema changes must be explicit and
auditable through the SQL Editor or an authenticated PostgreSQL client.

## Required extension

- `pgcrypto`, created by `v3_0_event_fusion_tracking.sql`; later UUID tables
  use `gen_random_uuid()`.
- No repository migration defines a custom SQL function or trigger.

## Required tables

- `events`
- `device_status`
- `device_locations`
- `device_commands`
- `event_groups`
- `event_group_observations`
- `localization_results`
- `localization_pair_results`
- `target_tracks`
- `target_track_points`
- `device_connections`
- `audio_stream_sessions`

Observation shadow state itself is in memory in Phase 4 and does not add a
table or require a migration.

## Index and constraint families

- Unique event identity: `events_event_id_key`.
- Device status/location primary keys and location range/source checks.
- Command pending/status/idempotency indexes.
- Fusion lookup, event/device/time, group membership, and one-fusion-row-per-
  event indexes.
- Localization input signature, group, method, and pair-result indexes.
- Track status/label and track-point track/group/time indexes.
- Live connection uniqueness and audio stream device indexes.
- Foreign keys connect observations to events/groups, localization results to
  groups, pair results to localization/groups, and track points to tracks,
  groups, and localization results.

`tools/migration_precheck.sql` inventories exact installed definitions.
`tools/migration_postcheck.sql` verifies the Phase 4 minimum after application.
Neither script writes data or schema.

## Fresh staging application order

1. `v2_0_events_baseline.sql`
2. `v2_1_remote_node_management.sql`
3. `v3_0_event_fusion_tracking.sql`
4. `v3_1a_timing_metadata.sql`
5. `v3_1b_smart_audio_upload.sql`
6. `v3_2_time_sync.sql`
7. `v3_3_localization.sql`
8. `v3_4_hybrid_localization.sql`
9. `v4_final_realtime.sql`
10. `v4_final_localization.sql`
11. `v4_final_tracking.sql`
12. `v4_1_tracking_metadata.sql`
13. `v4_region_localization.sql`
14. `v5_device_fixed_locations.sql`
15. `v5_1_device_status_split_upload_status.sql`

Do not also run superseded `v4_0_tracking.sql`. Do not apply the chain blindly
to an existing database; use the precheck and apply only missing additive
changes.
