# Supabase Session Pooler latency probe

This probe is staging-only and disabled by default. It does not change SQL, pool sizing, worker counts, database schema, localization, TDOA, fusion, tracking, or Render instance settings.

## Probe contract

`POST /diagnostics/db-latency?samples=50` requires the existing `x-upload-token` and `STAGING_DB_LATENCY_PROBE_ENABLED=true`. The endpoint performs, on the staging service:

- up to 30 application checkout cycles, including the existing semaphore, pool checkout, and connection reset path;
- 50 `SELECT 1` calls on one warm connection;
- 30 `BEGIN` + `SELECT 1` + `COMMIT` cycles, with SELECT and COMMIT timed separately;
- up to 10 direct `psycopg2.connect()` calls when the service has a database URL;
- DNS and 20 sequential TCP connects to the redacted endpoint;
- server-side `EXPLAIN (ANALYZE, TIMING, BUFFERS) SELECT 1`.
- no indexed query, because no staging fixture/table was approved for a safe generic query.

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

## Execution status

The probe was executed against the isolated staging service after deploying commit `2757dc889deee1e3bd71271a73d6cc263c729567`. The redacted result is saved as `outputs/staging_rtt_root_cause_probe_20260930.json` locally and was not committed because it is runtime evidence. The endpoint was then disabled again and `/runtime-status` confirmed `staging_db_latency_probe_enabled=false`.

The run returned 50 warm SELECT samples, 30 transaction samples, 30 application checkout samples, 10 physical connection samples, 20 TCP samples, DNS timing, and server-side EXPLAIN timing. The indexed query was intentionally not run because no approved staging primary-key fixture was supplied. The Supabase project region remains unknown because no authorized project metadata was available.

The probe used the existing staging upload token through the Render secret UI. The token was not written to source, command output, or the repository.

The repository does not contain the staging `DATABASE_URL`, so the direct-connect and Supabase region results can only be obtained by the staging service itself. The user-provided architecture is Session Pooler on port 5432; the service-side probe should be used as the authoritative measurement.

## Interpretation

Compare `pool_checkout_ms`, `same_connection_select_1_ms`, `transaction_select_1_ms`, `transaction_commit_ms`, and (when available) `physical_connect_ms`:

- high checkout with low warm SELECT suggests application pool contention, semaphore wait, or connection reset overhead;
- high warm SELECT suggests network, pooler, or database queue latency;
- high COMMIT with low SELECT suggests transaction or synchronous commit latency;
- high direct connect relative to warm SELECT suggests connection establishment or pooler handshake cost.

The existing application runtime samples already show event DB connection acquisition is materially slower than the SQL phase. The new network and server-side timings strongly point to the Render-to-pooler path for the fixed warm-query RTT, while physical connect remains a separate, larger lifecycle cost. This probe does not by itself measure TDOA/localization performance.
