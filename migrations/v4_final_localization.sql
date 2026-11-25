-- V4 Final localization schema consolidation.
-- Safe to run multiple times.

ALTER TABLE event_groups
ADD COLUMN IF NOT EXISTS localization_status text,
ADD COLUMN IF NOT EXISTS estimated_lat double precision,
ADD COLUMN IF NOT EXISTS estimated_lng double precision,
ADD COLUMN IF NOT EXISTS localization_method text,
ADD COLUMN IF NOT EXISTS localization_version text,
ADD COLUMN IF NOT EXISTS confidence double precision,
ADD COLUMN IF NOT EXISTS residual_m double precision,
ADD COLUMN IF NOT EXISTS uncertainty_radius_m double precision,
ADD COLUMN IF NOT EXISTS geometry_quality text,
ADD COLUMN IF NOT EXISTS reference_device_id text,
ADD COLUMN IF NOT EXISTS localization_node_count integer,
ADD COLUMN IF NOT EXISTS localized_at timestamptz;

CREATE TABLE IF NOT EXISTS localization_results (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    group_id uuid REFERENCES event_groups(id) ON DELETE SET NULL,
    method text,
    version text,
    status text,
    label text,
    estimated_lat double precision,
    estimated_lng double precision,
    confidence double precision,
    residual_m double precision,
    uncertainty_radius_m double precision,
    geometry_quality text,
    reference_device_id text,
    node_count integer,
    event_time_ms double precision,
    input_signature text,
    diagnostics_json jsonb,
    created_at timestamptz DEFAULT now()
);

ALTER TABLE localization_results
ADD COLUMN IF NOT EXISTS group_id uuid,
ADD COLUMN IF NOT EXISTS method text,
ADD COLUMN IF NOT EXISTS version text,
ADD COLUMN IF NOT EXISTS status text,
ADD COLUMN IF NOT EXISTS label text,
ADD COLUMN IF NOT EXISTS estimated_lat double precision,
ADD COLUMN IF NOT EXISTS estimated_lng double precision,
ADD COLUMN IF NOT EXISTS confidence double precision,
ADD COLUMN IF NOT EXISTS residual_m double precision,
ADD COLUMN IF NOT EXISTS uncertainty_radius_m double precision,
ADD COLUMN IF NOT EXISTS geometry_quality text,
ADD COLUMN IF NOT EXISTS reference_device_id text,
ADD COLUMN IF NOT EXISTS node_count integer,
ADD COLUMN IF NOT EXISTS event_time_ms double precision,
ADD COLUMN IF NOT EXISTS input_signature text,
ADD COLUMN IF NOT EXISTS diagnostics_json jsonb,
ADD COLUMN IF NOT EXISTS created_at timestamptz DEFAULT now();

CREATE UNIQUE INDEX IF NOT EXISTS localization_results_signature_idx
ON localization_results (input_signature)
WHERE input_signature IS NOT NULL;

CREATE INDEX IF NOT EXISTS localization_results_group_idx
ON localization_results (group_id, created_at DESC);

CREATE TABLE IF NOT EXISTS localization_pair_results (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    localization_result_id uuid REFERENCES localization_results(id) ON DELETE CASCADE,
    group_id uuid REFERENCES event_groups(id) ON DELETE CASCADE,
    device_a text NOT NULL,
    device_b text NOT NULL,
    lag_samples double precision,
    lag_seconds double precision,
    correlation_score double precision,
    accepted boolean DEFAULT false,
    rejection_reason text,
    max_physical_lag_seconds double precision,
    created_at timestamptz DEFAULT now()
);

ALTER TABLE localization_pair_results
ADD COLUMN IF NOT EXISTS localization_result_id uuid,
ADD COLUMN IF NOT EXISTS group_id uuid,
ADD COLUMN IF NOT EXISTS device_a text,
ADD COLUMN IF NOT EXISTS device_b text,
ADD COLUMN IF NOT EXISTS lag_samples double precision,
ADD COLUMN IF NOT EXISTS lag_seconds double precision,
ADD COLUMN IF NOT EXISTS correlation_score double precision,
ADD COLUMN IF NOT EXISTS accepted boolean DEFAULT false,
ADD COLUMN IF NOT EXISTS rejection_reason text,
ADD COLUMN IF NOT EXISTS max_physical_lag_seconds double precision,
ADD COLUMN IF NOT EXISTS created_at timestamptz DEFAULT now();

CREATE INDEX IF NOT EXISTS localization_pair_results_result_idx
ON localization_pair_results (localization_result_id);

CREATE INDEX IF NOT EXISTS localization_pair_results_group_idx
ON localization_pair_results (group_id);

