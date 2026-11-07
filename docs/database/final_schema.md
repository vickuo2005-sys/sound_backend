# Final Database Schema

Final migration files:

- `migrations/v4_final_realtime.sql`
- `migrations/v4_final_localization.sql`
- `migrations/v4_final_tracking.sql`

## Core Tables

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

## Compatibility

Existing rows remain valid. New columns are nullable unless needed for newly created rows.

## Migration Safety

The final migrations use:

- `CREATE TABLE IF NOT EXISTS`
- `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`
- `CREATE INDEX IF NOT EXISTS`
- partial unique indexes where appropriate

