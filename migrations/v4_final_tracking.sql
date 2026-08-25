-- V4 Final target tracking schema consolidation.
-- Safe to run multiple times.

CREATE TABLE IF NOT EXISTS target_tracks (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    label text,
    status text DEFAULT 'ACTIVE',
    origin_lat double precision,
    origin_lng double precision,
    created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now(),
    first_event_time_ms double precision,
    last_event_time_ms double precision,
    point_count integer DEFAULT 0,
    last_lat double precision,
    last_lng double precision,
    last_speed_mps double precision,
    last_heading_deg double precision,
    last_confidence double precision,
    velocity_east_mps double precision,
    velocity_north_mps double precision,
    closed_at timestamptz
);

ALTER TABLE target_tracks
ADD COLUMN IF NOT EXISTS label text,
ADD COLUMN IF NOT EXISTS status text DEFAULT 'ACTIVE',
ADD COLUMN IF NOT EXISTS origin_lat double precision,
ADD COLUMN IF NOT EXISTS origin_lng double precision,
ADD COLUMN IF NOT EXISTS created_at timestamptz DEFAULT now(),
ADD COLUMN IF NOT EXISTS updated_at timestamptz DEFAULT now(),
ADD COLUMN IF NOT EXISTS first_event_time_ms double precision,
ADD COLUMN IF NOT EXISTS last_event_time_ms double precision,
ADD COLUMN IF NOT EXISTS point_count integer DEFAULT 0,
ADD COLUMN IF NOT EXISTS last_lat double precision,
ADD COLUMN IF NOT EXISTS last_lng double precision,
ADD COLUMN IF NOT EXISTS last_speed_mps double precision,
ADD COLUMN IF NOT EXISTS last_heading_deg double precision,
ADD COLUMN IF NOT EXISTS last_confidence double precision,
ADD COLUMN IF NOT EXISTS velocity_east_mps double precision,
ADD COLUMN IF NOT EXISTS velocity_north_mps double precision,
ADD COLUMN IF NOT EXISTS closed_at timestamptz;

CREATE INDEX IF NOT EXISTS target_tracks_status_label_idx
ON target_tracks (status, label, updated_at DESC);

CREATE TABLE IF NOT EXISTS target_track_points (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    track_id uuid REFERENCES target_tracks(id) ON DELETE CASCADE,
    group_id uuid REFERENCES event_groups(id) ON DELETE SET NULL,
    localization_result_id uuid REFERENCES localization_results(id) ON DELETE SET NULL,
    measurement_time_ms double precision,
    measured_lat double precision,
    measured_lng double precision,
    filtered_lat double precision,
    filtered_lng double precision,
    predicted_lat double precision,
    predicted_lng double precision,
    velocity_east_mps double precision,
    velocity_north_mps double precision,
    speed_mps double precision,
    heading_deg double precision,
    uncertainty_radius_m double precision,
    confidence double precision,
    rejected_as_outlier boolean DEFAULT false,
    innovation_m double precision,
    state_json jsonb,
    covariance_json jsonb,
    diagnostics_json jsonb,
    created_at timestamptz DEFAULT now()
);

ALTER TABLE target_track_points
ADD COLUMN IF NOT EXISTS track_id uuid,
ADD COLUMN IF NOT EXISTS group_id uuid,
ADD COLUMN IF NOT EXISTS localization_result_id uuid,
ADD COLUMN IF NOT EXISTS measurement_time_ms double precision,
ADD COLUMN IF NOT EXISTS measured_lat double precision,
ADD COLUMN IF NOT EXISTS measured_lng double precision,
ADD COLUMN IF NOT EXISTS filtered_lat double precision,
ADD COLUMN IF NOT EXISTS filtered_lng double precision,
ADD COLUMN IF NOT EXISTS predicted_lat double precision,
ADD COLUMN IF NOT EXISTS predicted_lng double precision,
ADD COLUMN IF NOT EXISTS velocity_east_mps double precision,
ADD COLUMN IF NOT EXISTS velocity_north_mps double precision,
ADD COLUMN IF NOT EXISTS speed_mps double precision,
ADD COLUMN IF NOT EXISTS heading_deg double precision,
ADD COLUMN IF NOT EXISTS uncertainty_radius_m double precision,
ADD COLUMN IF NOT EXISTS confidence double precision,
ADD COLUMN IF NOT EXISTS rejected_as_outlier boolean DEFAULT false,
ADD COLUMN IF NOT EXISTS innovation_m double precision,
ADD COLUMN IF NOT EXISTS state_json jsonb,
ADD COLUMN IF NOT EXISTS covariance_json jsonb,
ADD COLUMN IF NOT EXISTS diagnostics_json jsonb,
ADD COLUMN IF NOT EXISTS created_at timestamptz DEFAULT now();

CREATE INDEX IF NOT EXISTS target_track_points_track_idx
ON target_track_points (track_id, measurement_time_ms);

CREATE INDEX IF NOT EXISTS target_track_points_group_idx
ON target_track_points (group_id);
