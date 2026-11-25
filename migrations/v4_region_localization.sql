-- V4 region localization redesign.
-- This keeps legacy TDOA/GCC-PHAT/tracking tables for compatibility and adds
-- the minimum event_groups fields needed for MCU-friendly region estimation.

ALTER TABLE event_groups
    ADD COLUMN IF NOT EXISTS region_type TEXT;

ALTER TABLE event_groups
    ADD COLUMN IF NOT EXISTS region_center_lat DOUBLE PRECISION;

ALTER TABLE event_groups
    ADD COLUMN IF NOT EXISTS region_center_lng DOUBLE PRECISION;

ALTER TABLE event_groups
    ADD COLUMN IF NOT EXISTS region_geojson JSONB;

ALTER TABLE event_groups
    ADD COLUMN IF NOT EXISTS reporting_node_count INTEGER;

ALTER TABLE event_groups
    ADD COLUMN IF NOT EXISTS reporting_device_ids JSONB;

ALTER TABLE event_groups
    ADD COLUMN IF NOT EXISTS region_updated_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS event_groups_region_updated_at_idx
    ON event_groups (region_updated_at DESC);

CREATE INDEX IF NOT EXISTS event_groups_region_type_idx
    ON event_groups (region_type);
