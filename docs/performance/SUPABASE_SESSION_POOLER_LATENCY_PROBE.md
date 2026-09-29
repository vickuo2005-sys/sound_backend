# Supabase Session Pooler latency probe

This probe is staging-only and disabled by default. It does not change SQL, pool sizing, worker counts, database schema, localization, TDOA, fusion, tracking, or Render instance settings.

## Probe contract

`POST /diagnostics/db-latency?samples=50` requires the existing `x-upload-token` and `STAGING_DB_LATENCY_PROBE_ENABLED=true`. The endpoint performs, on the staging service:

- up to 30 application checkout cycles, including the existing semaphore, pool checkout, and connection reset path;
- 50 `SELECT 1` calls on one warm connection;
- 30 `BEGIN` + `SELECT 1` + `COMMIT` cycles, with SELECT and COMMIT timed separately;
- up to 10 direct `psycopg2.connect()` calls when the service has a database URL;
- no indexed query or `EXPLAIN ANALYZE`, because no staging fixture/table was approved for a safe generic query.

All durations use the existing monotonic timer and are returned in milliseconds with count, min, mean, p50, p90, p95, p99, and max. `pool_checkout_ms` is application checkout plus reset, not a raw `pool.getconn()` measurement. `physical_connect_ms.count=0` means the direct-connect series was unavailable or failed and must not be interpreted as zero latency.

The helper sends one bounded request (rather than 50 requests) so the server performs the complete sample set in one controlled run:

```powershell
python tools/measure_staging_db_latency.py `
  --base-url https://<staging-host> `
  --upload-token $env:UPLOAD_TOKEN `
  --samples 50 `
  > outputs/staging_db_latency_probe.json
```

Before running, set the flag only on the isolated staging service, confirm the existing staging database is being used, and restore `STAGING_DB_LATENCY_PROBE_ENABLED=false` immediately after collecting the JSON. Do not use port 6543 and do not run the endpoint against production.

## Execution status for this checkout

The code and helper are validated locally, but the staging request was not executed from this checkout because no `UPLOAD_TOKEN` is present in the local environment. No Render environment variable was changed and no endpoint was enabled. A token must be supplied through the approved staging secret path; it should not be committed, pasted into source, or printed in logs.

The repository does not contain the staging `DATABASE_URL`, so the direct-connect and Supabase region results can only be obtained by the staging service itself. The user-provided architecture is Session Pooler on port 5432; the service-side probe should be used as the authoritative measurement.

## Interpretation

Compare `pool_checkout_ms`, `same_connection_select_1_ms`, `transaction_select_1_ms`, `transaction_commit_ms`, and (when available) `physical_connect_ms`:

- high checkout with low warm SELECT suggests application pool contention, semaphore wait, or connection reset overhead;
- high warm SELECT suggests network, pooler, or database queue latency;
- high COMMIT with low SELECT suggests transaction or synchronous commit latency;
- high direct connect relative to warm SELECT suggests connection establishment or pooler handshake cost.

The existing application runtime samples already show event DB connection acquisition is materially slower than the SQL phase. This probe is needed before attributing that gap to Supabase, Session Pooler, application contention, or transaction behavior. It does not by itself measure TDOA/localization performance.
