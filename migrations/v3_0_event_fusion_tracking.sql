-- V3.0 Event Fusion Layer
-- Safe to run multiple times in Supabase SQL Editor.
--
-- This migration keeps compatibility columns used by the existing dashboard
-- target estimate layer, but V3.0 fusion rows are identified by:
--   event_groups.group_kind = 'fusion'
--   event_group_observations.observation_kind = 'fusion'

create extension if not exists pgcrypto;

create table if not exists event_groups (
    id uuid primary key default gen_random_uuid(),
    group_kind text default 'fusion',
    label text,
    group_label text,
    status text default 'ACTIVE',
    created_at timestamptz default now(),
    updated_at timestamptz default now(),
    first_event_time timestamptz,
    last_event_time timestamptz,
    start_time timestamptz,
    end_time timestamptz,
    node_count integer default 0,
    estimated_lat double precision,
    estimated_lng double precision,
    localization_method text,
    method text,
    confidence double precision,
    uncertainty_radius_m double precision,
    tdoa_residual_rmse_m double precision,
    tdoa_node_count integer,
    time_sync_quality text
);

alter table event_groups
    add column if not exists group_kind text default 'fusion',
    add column if not exists label text,
    add column if not exists group_label text,
    add column if not exists status text default 'ACTIVE',
    add column if not exists created_at timestamptz default now(),
    add column if not exists updated_at timestamptz default now(),
    add column if not exists first_event_time timestamptz,
    add column if not exists last_event_time timestamptz,
    add column if not exists start_time timestamptz,
    add column if not exists end_time timestamptz,
    add column if not exists node_count integer default 0,
    add column if not exists estimated_lat double precision,
    add column if not exists estimated_lng double precision,
    add column if not exists localization_method text,
    add column if not exists method text,
    add column if not exists confidence double precision,
    add column if not exists uncertainty_radius_m double precision,
    add column if not exists tdoa_residual_rmse_m double precision,
    add column if not exists tdoa_node_count integer,
    add column if not exists time_sync_quality text;

create table if not exists event_group_observations (
    id uuid primary key default gen_random_uuid(),
    group_id uuid references event_groups(id) on delete cascade,
    event_db_id bigint references events(id),
    event_id text,
    device_id text,
    label text,
    event_timestamp timestamptz,
    latitude double precision,
    longitude double precision,
    rms_peak double precision,
    ai_probability double precision,
    aircraft_probability double precision,
    audio_path text,
    created_at timestamptz default now(),
    observation_kind text default 'fusion',
    weight double precision,
    corrected_arrival_time_ms double precision,
    time_sync_rtt_ms double precision,
    tdoa_used boolean default false,
    tdoa_residual_m double precision
);

alter table event_group_observations
    add column if not exists group_id uuid,
    add column if not exists event_db_id bigint,
    add column if not exists event_id text,
    add column if not exists device_id text,
    add column if not exists label text,
    add column if not exists event_timestamp timestamptz,
    add column if not exists latitude double precision,
    add column if not exists longitude double precision,
    add column if not exists rms_peak double precision,
    add column if not exists ai_probability double precision,
    add column if not exists aircraft_probability double precision,
    add column if not exists audio_path text,
    add column if not exists created_at timestamptz default now(),
    add column if not exists observation_kind text default 'fusion',
    add column if not exists weight double precision,
    add column if not exists corrected_arrival_time_ms double precision,
    add column if not exists time_sync_rtt_ms double precision,
    add column if not exists tdoa_used boolean default false,
    add column if not exists tdoa_residual_m double precision;

do $$
begin
    if not exists (
        select 1
        from pg_constraint
        where conname = 'event_group_observations_event_db_id_fkey'
    ) then
        alter table event_group_observations
            add constraint event_group_observations_event_db_id_fkey
            foreign key (event_db_id) references events(id);
    end if;
exception
    when duplicate_object then null;
end $$;

update event_groups
set group_kind = 'target_estimate'
where coalesce(group_kind, 'fusion') = 'fusion'
  and (
        estimated_lat is not null
     or estimated_lng is not null
     or uncertainty_radius_m is not null
     or method is not null
     or tdoa_residual_rmse_m is not null
  );

update event_group_observations
set observation_kind = 'target_estimate'
where coalesce(observation_kind, 'fusion') = 'fusion'
  and (
        weight is not null
     or corrected_arrival_time_ms is not null
     or time_sync_rtt_ms is not null
     or tdoa_residual_m is not null
  );

create index if not exists event_groups_label_status_last_time_idx
    on event_groups (label, status, last_event_time);

create index if not exists event_groups_updated_at_idx
    on event_groups (updated_at desc);

create index if not exists event_group_observations_group_idx
    on event_group_observations (group_id);

create index if not exists event_group_observations_event_id_idx
    on event_group_observations (event_id);

create index if not exists event_group_observations_device_idx
    on event_group_observations (device_id);

create index if not exists event_group_observations_timestamp_idx
    on event_group_observations (event_timestamp);

create unique index if not exists event_group_observations_fusion_event_id_key
    on event_group_observations (event_id)
    where observation_kind = 'fusion';
