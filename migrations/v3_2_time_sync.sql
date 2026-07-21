-- V3.2 Time Sync
-- Stores per-device clock offset and RTT quality for dashboard monitoring.
-- Safe to run multiple times in Supabase SQL Editor.

ALTER TABLE device_status
ADD COLUMN IF NOT EXISTS time_sync_offset_ms DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS time_sync_rtt_ms DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS time_sync_quality TEXT,
ADD COLUMN IF NOT EXISTS time_sync_at TIMESTAMPTZ,
ADD COLUMN IF NOT EXISTS last_time_sync_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS device_status_time_sync_quality_idx
ON device_status (time_sync_quality);
