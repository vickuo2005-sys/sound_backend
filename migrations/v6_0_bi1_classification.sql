-- V6.0 BI-1 versioned five-class event metadata.
--
-- Additive and idempotent. Do not apply to production as part of BI-1.
-- Apply only to an approved isolated environment before enabling
-- CLASSIFICATION_V1_PERSISTENCE_ENABLED.

ALTER TABLE events
ADD COLUMN IF NOT EXISTS classification_schema_version TEXT,
ADD COLUMN IF NOT EXISTS model_id TEXT,
ADD COLUMN IF NOT EXISTS model_version TEXT,
ADD COLUMN IF NOT EXISTS model_label TEXT,
ADD COLUMN IF NOT EXISTS model_confidence DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS operational_class TEXT,
ADD COLUMN IF NOT EXISTS aircraft_probability DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS drone_subtype TEXT,
ADD COLUMN IF NOT EXISTS class_scores_json JSONB;

CREATE INDEX IF NOT EXISTS events_model_label_idx
ON events (model_label, id DESC)
WHERE model_label IS NOT NULL;

CREATE INDEX IF NOT EXISTS events_operational_class_idx
ON events (operational_class, id DESC)
WHERE operational_class IS NOT NULL;
