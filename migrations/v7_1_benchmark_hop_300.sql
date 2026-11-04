-- PostgreSQL only. Explicit operator-run upgrade for an existing V7 database.
-- Existing rows are retained; only the benchmark Hop allowlist is expanded.
BEGIN;
ALTER TABLE benchmark_runs DROP CONSTRAINT IF EXISTS benchmark_runs_hop_ms_check;
ALTER TABLE benchmark_runs ADD CONSTRAINT benchmark_runs_hop_ms_check
    CHECK (hop_ms IN (1500,1000,750,500,350,300,250,200,150,100));
COMMIT;
