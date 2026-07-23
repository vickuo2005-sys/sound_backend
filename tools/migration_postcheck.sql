-- Read-only schema verification after staging migrations.
-- This script does not modify data or schema.

with required_columns(table_name, column_name) as (
  values
    ('events', 'event_id'),
    ('events', 'audio_path'),
    ('events', 'audio_format'),
    ('events', 'tdoa_clip_path'),
    ('events', 'tdoa_clip_start_sample'),
    ('events', 'time_sync_offset_ms'),
    ('events', 'corrected_arrival_time_ms'),
    ('device_status', 'device_id'),
    ('device_status', 'time_sync_offset_ms'),
    ('device_status', 'time_sync_rtt_ms'),
    ('device_status', 'time_sync_quality'),
    ('device_status', 'time_sync_at'),
    ('device_commands', 'device_id'),
    ('device_commands', 'command'),
    ('event_groups', 'id'),
    ('event_groups', 'node_count'),
    ('event_group_observations', 'group_id'),
    ('event_group_observations', 'event_id'),
    ('event_group_observations', 'corrected_arrival_time_ms'),
    ('localization_results', 'group_id'),
    ('target_tracks', 'id'),
    ('target_track_points', 'track_id')
)
select
  rc.table_name,
  rc.column_name,
  case when c.column_name is null then 'missing' else 'ok' end as status,
  c.data_type,
  c.is_nullable,
  c.column_default
from required_columns rc
left join information_schema.columns c
  on c.table_schema = 'public'
  and c.table_name = rc.table_name
  and c.column_name = rc.column_name
order by rc.table_name, rc.column_name;

select
  tc.table_name,
  tc.constraint_name,
  tc.constraint_type,
  string_agg(kcu.column_name, ', ' order by kcu.ordinal_position) as columns
from information_schema.table_constraints tc
left join information_schema.key_column_usage kcu
  on tc.constraint_name = kcu.constraint_name
  and tc.table_schema = kcu.table_schema
where tc.table_schema = 'public'
  and tc.table_name in ('event_group_observations', 'event_groups', 'events')
group by tc.table_name, tc.constraint_name, tc.constraint_type
order by tc.table_name, tc.constraint_name;

select
  schemaname,
  tablename,
  indexname,
  indexdef
from pg_indexes
where schemaname = 'public'
  and tablename in (
    'events',
    'device_status',
    'device_commands',
    'event_groups',
    'event_group_observations',
    'localization_results',
    'target_tracks',
    'target_track_points'
  )
order by tablename, indexname;
