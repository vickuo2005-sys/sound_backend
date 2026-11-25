-- V3.3 Timestamp-based TDOA Localization
-- Safe to run multiple times in Supabase SQL Editor.

ALTER TABLE event_groups
ADD COLUMN IF NOT EXISTS localization_status TEXT,
ADD COLUMN IF NOT EXISTS estimated_lat DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS estimated_lng DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS localization_method TEXT,
ADD COLUMN IF NOT EXISTS localization_version TEXT,
ADD COLUMN IF NOT EXISTS confidence DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS residual_m DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS uncertainty_radius_m DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS geometry_quality TEXT,
ADD COLUMN IF NOT EXISTS reference_device_id TEXT,
ADD COLUMN IF NOT EXISTS localization_node_count INTEGER,
ADD COLUMN IF NOT EXISTS localized_at TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS localization_results (
    id UUID PRIMARY KEY,
    group_id UUID REFERENCES event_groups(id) ON DELETE SET NULL,
    method TEXT,
    version TEXT,
    status TEXT,
    label TEXT,
    estimated_lat DOUBLE PRECISION,
    estimated_lng DOUBLE PRECISION,
    confidence DOUBLE PRECISION,
    residual_m DOUBLE PRECISION,
    uncertainty_radius_m DOUBLE PRECISION,
    geometry_quality TEXT,
    reference_device_id TEXT,
    node_count INTEGER,
    event_time_ms DOUBLE PRECISION,
    input_signature TEXT UNIQUE,
    diagnostics_json JSONB,
    created_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE localization_results
ADD COLUMN IF NOT EXISTS group_id UUID,
ADD COLUMN IF NOT EXISTS method TEXT,
ADD COLUMN IF NOT EXISTS version TEXT,
ADD COLUMN IF NOT EXISTS status TEXT,
ADD COLUMN IF NOT EXISTS label TEXT,
ADD COLUMN IF NOT EXISTS estimated_lat DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS estimated_lng DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS confidence DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS residual_m DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS uncertainty_radius_m DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS geometry_quality TEXT,
ADD COLUMN IF NOT EXISTS reference_device_id TEXT,
ADD COLUMN IF NOT EXISTS node_count INTEGER,
ADD COLUMN IF NOT EXISTS event_time_ms DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS input_signature TEXT,
ADD COLUMN IF NOT EXISTS diagnostics_json JSONB,
ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT now();

CREATE UNIQUE INDEX IF NOT EXISTS localization_results_signature_idx
ON localization_results (input_signature);

CREATE INDEX IF NOT EXISTS localization_results_group_idx
ON localization_results (group_id);

CREATE INDEX IF NOT EXISTS localization_results_created_idx
ON localization_results (created_at DESC);
