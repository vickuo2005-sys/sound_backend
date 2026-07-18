-- V3.1a PCM Timing Metadata
-- Safe to run multiple times in Supabase SQL Editor.

ALTER TABLE events ADD COLUMN IF NOT EXISTS timing_version INTEGER;
ALTER TABLE events ADD COLUMN IF NOT EXISTS timing_source TEXT;
ALTER TABLE events ADD COLUMN IF NOT EXISTS capture_start_time_ms BIGINT;
ALTER TABLE events ADD COLUMN IF NOT EXISTS event_start_sample BIGINT;
ALTER TABLE events ADD COLUMN IF NOT EXISTS event_end_sample BIGINT;
ALTER TABLE events ADD COLUMN IF NOT EXISTS rms_peak_sample BIGINT;
ALTER TABLE events ADD COLUMN IF NOT EXISTS sample_rate_hz INTEGER;
ALTER TABLE events ADD COLUMN IF NOT EXISTS channel_count INTEGER;
ALTER TABLE events ADD COLUMN IF NOT EXISTS audio_duration_ms BIGINT;
ALTER TABLE events ADD COLUMN IF NOT EXISTS device_event_time_ms BIGINT;
ALTER TABLE events ADD COLUMN IF NOT EXISTS event_end_time_ms BIGINT;
ALTER TABLE events ADD COLUMN IF NOT EXISTS rms_peak_time_ms BIGINT;

ALTER TABLE event_group_observations ADD COLUMN IF NOT EXISTS timing_version INTEGER;
ALTER TABLE event_group_observations ADD COLUMN IF NOT EXISTS timing_source TEXT;
ALTER TABLE event_group_observations ADD COLUMN IF NOT EXISTS capture_start_time_ms BIGINT;
ALTER TABLE event_group_observations ADD COLUMN IF NOT EXISTS event_start_sample BIGINT;
ALTER TABLE event_group_observations ADD COLUMN IF NOT EXISTS event_end_sample BIGINT;
ALTER TABLE event_group_observations ADD COLUMN IF NOT EXISTS rms_peak_sample BIGINT;
ALTER TABLE event_group_observations ADD COLUMN IF NOT EXISTS sample_rate_hz INTEGER;
ALTER TABLE event_group_observations ADD COLUMN IF NOT EXISTS channel_count INTEGER;
ALTER TABLE event_group_observations ADD COLUMN IF NOT EXISTS audio_duration_ms BIGINT;
ALTER TABLE event_group_observations ADD COLUMN IF NOT EXISTS device_event_time_ms BIGINT;
ALTER TABLE event_group_observations ADD COLUMN IF NOT EXISTS event_end_time_ms BIGINT;
ALTER TABLE event_group_observations ADD COLUMN IF NOT EXISTS rms_peak_time_ms BIGINT;

CREATE INDEX IF NOT EXISTS events_device_event_time_ms_idx
ON events (device_event_time_ms);

CREATE INDEX IF NOT EXISTS events_timing_source_idx
ON events (timing_source);

CREATE INDEX IF NOT EXISTS event_group_observations_device_event_time_ms_idx
ON event_group_observations (device_event_time_ms);

CREATE INDEX IF NOT EXISTS event_group_observations_timing_source_idx
ON event_group_observations (timing_source);
