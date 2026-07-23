# Migration Matrix

| Object | First Created In | Modified In | Duplicate Risk | Final Action |
|---|---|---|---|---|
| `event_groups` | `v3_0_event_fusion_tracking.sql` | `v3_3_localization.sql`, `v4_final_localization.sql` | localization columns overlap | use `ADD COLUMN IF NOT EXISTS` |
| `event_group_observations` | `v3_0_event_fusion_tracking.sql` | `v3_1a_timing_metadata.sql`, `v3_1b_smart_audio_upload.sql` | timing/audio columns overlap | preserve legacy columns |
| `localization_results` | `v3_3_localization.sql` | `v3_4_hybrid_localization.sql`, `v4_final_localization.sql` | table can already exist | `CREATE TABLE IF NOT EXISTS` + safe alter |
| `localization_pair_results` | `v4_final_localization.sql` | none | new object | safe create |
| `target_tracks` | `v4_0_tracking.sql` | `v4_final_tracking.sql` | table can already exist | safe alter |
| `target_track_points` | `v4_0_tracking.sql` | `v4_final_tracking.sql` | table can already exist | safe alter |
| `device_commands` | `v2_1_remote_node_management.sql` | `v4_final_realtime.sql` | lifecycle columns overlap possible | safe alter |
| `device_connections` | `v4_final_realtime.sql` | none | new object | safe create |
| `audio_stream_sessions` | `v4_final_realtime.sql` | none | new object | safe create |

## Checks

- UUID foreign keys must reference UUID primary keys.
- Existing legacy rows remain valid because new columns are nullable.
- Index names are unique.
- Final migrations are additive only.

