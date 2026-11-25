-- V5 fixed node location management.
-- Safe to run repeatedly. This does not modify historical event GPS,
-- legacy localization tables, TDOA tables, or tracking tables.

CREATE TABLE IF NOT EXISTS device_locations (
    device_id TEXT PRIMARY KEY,
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    location_source TEXT NOT NULL,
    accuracy_m DOUBLE PRECISION NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT device_locations_latitude_range
        CHECK (latitude >= -90 AND latitude <= 90),
    CONSTRAINT device_locations_longitude_range
        CHECK (longitude >= -180 AND longitude <= 180),
    CONSTRAINT device_locations_source_check
        CHECK (location_source IN ('manual_map', 'current_gps')),
    CONSTRAINT device_locations_accuracy_check
        CHECK (accuracy_m IS NULL OR accuracy_m >= 0)
);

CREATE INDEX IF NOT EXISTS device_locations_updated_at_idx
    ON device_locations (updated_at DESC);
