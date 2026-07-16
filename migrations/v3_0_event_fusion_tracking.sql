-- V3.0 Event fusion and coarse source localization
-- Safe to run multiple times in Supabase SQL Editor.

create extension if not exists pgcrypto;

create table if not exists event_groups (
    id uuid primary key default gen_random_uuid(),
    group_label text,
    start_time timestamptz,
    end_time timestamptz,
    node_count integer,
    estimated_lat double precision,
    estimated_lng double precision,
    confidence double precision,
    uncertainty_radius_m double precision,
    method text default 'weighted_centroid',
    created_at timestamptz default now(),
    updated_at timestamptz default now()
);

alter table event_groups
    add column if not exists group_label text,
    add column if not exists start_time timestamptz,
    add column if not exists end_time timestamptz,
    add column if not exists node_count integer,
    add column if not exists estimated_lat double precision,
    add column if not exists estimated_lng double precision,
    add column if not exists confidence double precision,
    add column if not exists uncertainty_radius_m double precision,
    add column if not exists method text default 'weighted_centroid',
    add column if not exists created_at timestamptz default now(),
    add column if not exists updated_at timestamptz default now();

create table if not exists event_group_observations (
    id uuid primary key default gen_random_uuid(),
    group_id uuid references event_groups(id) on delete cascade,
    event_id text,
    device_id text,
    latitude double precision,
    longitude double precision,
    rms_peak double precision,
    aircraft_probability double precision,
    event_timestamp timestamptz,
    weight double precision,
    created_at timestamptz default now()
);

alter table event_group_observations
    add column if not exists group_id uuid,
    add column if not exists event_id text,
    add column if not exists device_id text,
    add column if not exists latitude double precision,
    add column if not exists longitude double precision,
    add column if not exists rms_peak double precision,
    add column if not exists aircraft_probability double precision,
    add column if not exists event_timestamp timestamptz,
    add column if not exists weight double precision,
    add column if not exists created_at timestamptz default now();

create index if not exists event_groups_updated_at_idx
    on event_groups (updated_at desc);

create index if not exists event_groups_time_idx
    on event_groups (start_time, end_time);

create index if not exists event_group_observations_group_idx
    on event_group_observations (group_id);

create index if not exists event_group_observations_event_id_idx
    on event_group_observations (event_id);

create index if not exists event_group_observations_device_time_idx
    on event_group_observations (device_id, event_timestamp desc);

