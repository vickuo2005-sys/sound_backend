-- V3.4 GCC-PHAT / Hybrid Localization Support
-- This migration is intentionally light: V3.1b already added TDOA clip paths.
-- Safe to run multiple times in Supabase SQL Editor.

ALTER TABLE localization_results
ADD COLUMN IF NOT EXISTS method TEXT,
ADD COLUMN IF NOT EXISTS version TEXT,
ADD COLUMN IF NOT EXISTS diagnostics_json JSONB;

CREATE INDEX IF NOT EXISTS localization_results_method_idx
ON localization_results (method, status, created_at DESC);

CREATE INDEX IF NOT EXISTS event_group_observations_clip_idx
ON event_group_observations (tdoa_clip_path)
WHERE tdoa_clip_path IS NOT NULL;
