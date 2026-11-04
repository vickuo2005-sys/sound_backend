-- Explicit operator-run migration, independent of production application startup.
-- PostgreSQL and SQLite compatible; use a dedicated benchmark database/role.
BEGIN;
CREATE TABLE IF NOT EXISTS benchmark_sessions (
    session_id TEXT PRIMARY KEY,
    credential_hash TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    result_hash TEXT,
    result_json TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS benchmark_runs (
    run_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES benchmark_sessions(session_id),
    hop_ms INTEGER NOT NULL CHECK (hop_ms IN (1500,1000,750,500,350,300,250,200,150,100)),
    phase TEXT NOT NULL CHECK (phase IN ('survey','confirmation')),
    payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS benchmark_runs_session_idx ON benchmark_runs(session_id);
COMMIT;
