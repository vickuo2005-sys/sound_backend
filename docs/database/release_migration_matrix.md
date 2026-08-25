# Release Migration Matrix

No migration was executed during this freeze pass.

| Object | First migration | Later migrations | Conflict risk | Required order |
|---|---|---|---|---|
| `device_status` | `v2_1_remote_node_management.sql` | `v3_2_time_sync.sql`, `v4_final_realtime.sql` | Medium: repeated column additions must use `IF NOT EXISTS` | v2.1 before v3.2 before v4 final |
| `device_commands` | `v2_1_remote_node_management.sql` | `v4_final_realtime.sql` | Medium: command state/ack fields must remain compatible | v2.1 before v4 final realtime |
| `events` timing fields | `v3_1a_timing_metadata.sql` | `v3_1b_smart_audio_upload.sql`, `v3_2_time_sync.sql` | Medium: nullable additions only | v3.1a before v3.1b and v3.2 |
| `event_groups` | `v3_0_event_fusion_tracking.sql` | `v3_3_localization.sql`, `v4_final_localization.sql` | Medium: FK dependencies | v3.0 before localization |
| `event_group_observations` | `v3_0_event_fusion_tracking.sql` | `v3_1a_timing_metadata.sql`, `v3_1b_smart_audio_upload.sql`, `v3_2_time_sync.sql` | High: snapshot columns must match app payload | v3.0 before v3.1a/b/v3.2 |
| `localization_results` | `v3_3_localization.sql` | `v4_final_localization.sql` | Medium: duplicate table/index definitions must be idempotent | v3.3 before v4 final localization |
| `localization_pair_results` | `v3_4_hybrid_localization.sql` | `v4_final_localization.sql` | Medium | v3.4 before v4 final localization |
| `target_tracks` | `v4_0_tracking.sql` | `v4_final_tracking.sql` | Medium | v4.0 before v4 final tracking |
| `target_track_points` | `v4_0_tracking.sql` | `v4_final_tracking.sql` | Medium | v4.0 before v4 final tracking |

## Audit Notes

- Migration files should be applied to staging in chronological order.
- Prefer safe `ADD COLUMN IF NOT EXISTS` and `CREATE INDEX IF NOT EXISTS`.
- Do not run production migrations before a staging schema inventory and backup.
- Existing production data should not be deleted by any release migration.

