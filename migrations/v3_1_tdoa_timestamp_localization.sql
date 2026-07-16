-- V3.1 coarse TDOA timestamp localization
-- Safe to run more than once in Supabase SQL Editor.

alter table events
  add column if not exists device_event_time_ms double precision,
  add column if not exists event_start_time_ms double precision,
  add column if not exists event_end_time_ms double precision,
  add column if not exists rms_peak_offset_ms double precision,
  add column if not exists sample_rate integer,
  add column if not exists audio_duration_ms double precision,
  add column if not exists time_sync_offset_ms double precision,
  add column if not exists time_sync_rtt_ms double precision,
  add column if not exists corrected_arrival_time_ms double precision,
  add column if not exists timing_quality text;

alter table event_group_observations
  add column if not exists corrected_arrival_time_ms double precision,
  add column if not exists time_sync_rtt_ms double precision,
  add column if not exists tdoa_used boolean default false,
  add column if not exists tdoa_residual_m double precision;

alter table event_groups
  add column if not exists tdoa_residual_rmse_m double precision,
  add column if not exists tdoa_node_count integer,
  add column if not exists time_sync_quality text;

create index if not exists events_corrected_arrival_time_idx
  on events (corrected_arrival_time_ms);

create index if not exists events_timing_quality_idx
  on events (timing_quality);

create index if not exists event_group_observations_tdoa_used_idx
  on event_group_observations (tdoa_used);
