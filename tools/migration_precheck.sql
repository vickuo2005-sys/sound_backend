-- Read-only schema inventory for staging migration preparation.
-- Run this in Supabase SQL Editor before applying release migrations.

select current_database() as database_name, version() as postgres_version;

select table_schema, table_name
from information_schema.tables
where table_schema = 'public'
order by table_name;

select table_name, column_name, data_type, is_nullable, column_default
from information_schema.columns
where table_schema = 'public'
  and table_name in (
    'events',
    'device_status',
    'device_commands',
    'event_groups',
    'event_group_observations',
    'localization_results',
    'target_tracks',
    'target_track_points'
  )
order by table_name, ordinal_position;

select
  t.relname as table_name,
  i.relname as index_name,
  pg_get_indexdef(ix.indexrelid) as index_definition
from pg_class t
join pg_index ix on t.oid = ix.indrelid
join pg_class i on i.oid = ix.indexrelid
join pg_namespace n on n.oid = t.relnamespace
where n.nspname = 'public'
  and t.relname in (
    'events',
    'device_status',
    'device_commands',
    'event_groups',
    'event_group_observations',
    'localization_results',
    'target_tracks',
    'target_track_points'
  )
order by t.relname, i.relname;

select
  tc.table_name,
  tc.constraint_name,
  tc.constraint_type,
  kcu.column_name,
  ccu.table_name as foreign_table_name,
  ccu.column_name as foreign_column_name
from information_schema.table_constraints tc
left join information_schema.key_column_usage kcu
  on tc.constraint_name = kcu.constraint_name
  and tc.table_schema = kcu.table_schema
left join information_schema.constraint_column_usage ccu
  on tc.constraint_name = ccu.constraint_name
  and tc.table_schema = ccu.table_schema
where tc.table_schema = 'public'
  and tc.table_name in (
    'events',
    'device_status',
    'device_commands',
    'event_groups',
    'event_group_observations',
    'localization_results',
    'target_tracks',
    'target_track_points'
  )
order by tc.table_name, tc.constraint_name, kcu.ordinal_position;

select extname as extension_name, extversion
from pg_extension
order by extname;
