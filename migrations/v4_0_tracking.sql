-- V4.0 Kalman-style Target Tracking
-- Safe to run multiple times in Supabase SQL Editor.

CREATE TABLE IF NOT EXISTS target_tracks (
    id UUID PRIMARY KEY,
    label TEXT,
    status TEXT DEFAULT 'ACTIVE',
    origin_lat DOUBLE PRECISION,
    origin_lng DOUBLE PRECISION,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    first_event_time_ms DOUBLE PRECISION,
    last_event_time_ms DOUBLE PRECISION,
    point_count INTEGER DEFAULT 0,
    last_lat DOUBLE PRECISION,
    last_lng DOUBLE PRECISION,
    last_speed_mps DOUBLE PRECISION,
    last_heading_deg DOUBLE PRECISION,
    last_confidence DOUBLE PRECISION,
    velocity_east_mps DOUBLE PRECISION,
    velocity_north_mps DOUBLE PRECISION,
    closed_at TIMESTAMPTZ
);

ALTER TABLE target_tracks
ADD COLUMN IF NOT EXISTS label TEXT,
ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'ACTIVE',
ADD COLUMN IF NOT EXISTS origin_lat DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS origin_lng DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT now(),
ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT now(),
ADD COLUMN IF NOT EXISTS first_event_time_ms DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS last_event_time_ms DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS point_count INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS last_lat DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS last_lng DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS last_speed_mps DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS last_heading_deg DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS last_confidence DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS velocity_east_mps DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS velocity_north_mps DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS closed_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS target_tracks_status_label_idx
ON target_tracks (status, label, updated_at DESC);

CREATE TABLE IF NOT EXISTS target_track_points (
    id UUID PRIMARY KEY,
    track_id UUID REFERENCES target_tracks(id) ON DELETE CASCADE,
    group_id UUID REFERENCES event_groups(id) ON DELETE SET NULL,
    localization_result_id UUID REFERENCES localization_results(id) ON DELETE SET NULL,
    measurement_time_ms DOUBLE PRECISION,
    measured_lat DOUBLE PRECISION,
    measured_lng DOUBLE PRECISION,
    filtered_lat DOUBLE PRECISION,
    filtered_lng DOUBLE PRECISION,
    predicted_lat DOUBLE PRECISION,
    predicted_lng DOUBLE PRECISION,
    velocity_east_mps DOUBLE PRECISION,
    velocity_north_mps DOUBLE PRECISION,
    speed_mps DOUBLE PRECISION,
    heading_deg DOUBLE PRECISION,
    uncertainty_radius_m DOUBLE PRECISION,
    confidence DOUBLE PRECISION,
    rejected_as_outlier BOOLEAN DEFAULT false,
    innovation_m DOUBLE PRECISION,
    state_json JSONB,
    covariance_json JSONB,
    diagnostics_json JSONB,
    created_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE target_track_points
ADD COLUMN IF NOT EXISTS track_id UUID,
ADD COLUMN IF NOT EXISTS group_id UUID,
ADD COLUMN IF NOT EXISTS localization_result_id UUID,
ADD COLUMN IF NOT EXISTS measurement_time_ms DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS measured_lat DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS measured_lng DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS filtered_lat DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS filtered_lng DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS predicted_lat DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS predicted_lng DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS velocity_east_mps DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS velocity_north_mps DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS speed_mps DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS heading_deg DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS uncertainty_radius_m DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS confidence DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS rejected_as_outlier BOOLEAN DEFAULT false,
ADD COLUMN IF NOT EXISTS innovation_m DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS state_json JSONB,
ADD COLUMN IF NOT EXISTS covariance_json JSONB,
ADD COLUMN IF NOT EXISTS diagnostics_json JSONB,
ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT now();

CREATE INDEX IF NOT EXISTS target_track_points_track_idx
ON target_track_points (track_id, measurement_time_ms);

CREATE INDEX IF NOT EXISTS target_track_points_group_idx
ON target_track_points (group_id);
