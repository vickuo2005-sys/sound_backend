-- V3.1b Smart Audio Upload
-- Adds MP3 primary audio and short WAV TDOA clip metadata.
-- Safe to run multiple times in Supabase SQL Editor.

ALTER TABLE events
ADD COLUMN IF NOT EXISTS audio_format TEXT,
ADD COLUMN IF NOT EXISTS audio_size_bytes BIGINT,
ADD COLUMN IF NOT EXISTS source_pcm_size_bytes BIGINT,
ADD COLUMN IF NOT EXISTS audio_encoding_status TEXT,
ADD COLUMN IF NOT EXISTS tdoa_clip_path TEXT,
ADD COLUMN IF NOT EXISTS tdoa_clip_format TEXT,
ADD COLUMN IF NOT EXISTS tdoa_clip_size_bytes BIGINT,
ADD COLUMN IF NOT EXISTS tdoa_clip_start_sample BIGINT,
ADD COLUMN IF NOT EXISTS tdoa_clip_end_sample BIGINT,
ADD COLUMN IF NOT EXISTS tdoa_clip_peak_sample BIGINT,
ADD COLUMN IF NOT EXISTS tdoa_clip_duration_ms INTEGER,
ADD COLUMN IF NOT EXISTS tdoa_clip_source TEXT;

ALTER TABLE event_group_observations
ADD COLUMN IF NOT EXISTS audio_format TEXT,
ADD COLUMN IF NOT EXISTS audio_size_bytes BIGINT,
ADD COLUMN IF NOT EXISTS source_pcm_size_bytes BIGINT,
ADD COLUMN IF NOT EXISTS audio_encoding_status TEXT,
ADD COLUMN IF NOT EXISTS tdoa_clip_path TEXT,
ADD COLUMN IF NOT EXISTS tdoa_clip_format TEXT,
ADD COLUMN IF NOT EXISTS tdoa_clip_size_bytes BIGINT,
ADD COLUMN IF NOT EXISTS tdoa_clip_start_sample BIGINT,
ADD COLUMN IF NOT EXISTS tdoa_clip_end_sample BIGINT,
ADD COLUMN IF NOT EXISTS tdoa_clip_peak_sample BIGINT,
ADD COLUMN IF NOT EXISTS tdoa_clip_duration_ms INTEGER,
ADD COLUMN IF NOT EXISTS tdoa_clip_source TEXT;
