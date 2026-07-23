# Staging Migration Runbook

Do not run this against production.

1. Confirm staging database URL is selected.
2. Take a staging backup or snapshot.
3. Run schema inventory SQL:

```sql
select table_name from information_schema.tables where table_schema = 'public' order by table_name;
select table_name, column_name, data_type
from information_schema.columns
where table_schema = 'public'
order by table_name, ordinal_position;
```

4. Apply migrations in order:
   - `v2_1_remote_node_management.sql`
   - `v3_0_event_fusion_tracking.sql`
   - `v3_1a_timing_metadata.sql`
   - `v3_1b_smart_audio_upload.sql`
   - `v3_2_time_sync.sql`
   - `v3_3_localization.sql`
   - `v3_4_hybrid_localization.sql`
   - `v4_0_tracking.sql`
   - `v4_final_realtime.sql`
   - `v4_final_localization.sql`
   - `v4_final_tracking.sql`
5. Re-run safe migrations once in staging if the file is documented idempotent.
6. Run post-check SQL:

```sql
select count(*) from device_status;
select count(*) from device_commands;
select count(*) from event_groups;
select count(*) from event_group_observations;
select count(*) from localization_results;
select count(*) from target_tracks;
```

7. Deploy staging backend.
8. Run `tools/post_deploy_smoke.py --base-url <staging-url> --allow-websocket`.
9. If a migration fails, stop and forward-fix with an incremental migration. Do not destructively roll back schema objects.

