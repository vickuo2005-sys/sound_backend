# Staging PostgreSQL RTT root-cause investigation

Date: 2026-09-30  
Branch: `feat/latency-diagnostics-staging`  
Measured commit: `2757dc889deee1e3bd71271a73d6cc263c729567`

This is a staging-only diagnostic. It did not change `DATABASE_URL`, SQL behavior, pool sizing, worker counts, Render resources, production, localization, TDOA, Fusion, or Tracking.

## What was measured

The isolated Render service is `sound-backend-staging`, in Render Singapore, with one Uvicorn worker and the existing psycopg2 application pool. The bounded endpoint was enabled only for this run and then disabled again. The raw redacted result is [staging_rtt_root_cause_probe_20260930.json](../../outputs/staging_rtt_root_cause_probe_20260930.json).

| Measurement | n | P50 ms | P95 ms | P99 ms |
|---|---:|---:|---:|---:|
| Application pool checkout | 30 | 0.013 | 0.121 | 0.361 |
| Warm same-connection `SELECT 1` | 50 | 71.203 | 73.991 | 142.345 |
| Transaction `SELECT 1` | 30 | 71.205 | 71.678 | 73.225 |
| Transaction `COMMIT` | 30 | 71.113 | 71.490 | 72.730 |
| Physical `psycopg2.connect()` | 10 | 424.865 | 456.187 | 456.187 |
| TCP connect to the redacted endpoint, port 5432 | 20 | 71.016 | 72.468 | 72.584 |

DNS resolution was 1.841 ms and returned three IPv4 addresses. The endpoint suffix was `pooler.supabase.com` and the observed port was 5432. The TLS versus PostgreSQL startup split was not available in this probe. No indexed query was run because no approved staging primary-key fixture was supplied.

The server-side probe `EXPLAIN (ANALYZE, TIMING, BUFFERS) SELECT 1` reported planning 0.018 ms and execution 0.020 ms. Its client wall time was 147.568 ms; that value includes client/protocol result handling and is not server execution time. It is consistent with the approximately 71–73 ms per protocol round trip, but does not prove the exact number of wire exchanges.

## Evidence and interpretation

**Confirmed:** the fixed ~73 ms is present in direct TCP connection establishment to the resolved port-5432 endpoint, while application pool checkout is near zero. The same magnitude appears in warm query, transaction SELECT, and COMMIT timings. Server execution for `SELECT 1` is approximately 0.02 ms. This rules out Python computation, pool acquisition, and the database executor as the primary source of the fixed interval for this probe.

**Strongly suspected:** the dominant cost is the Render Singapore to the configured Supabase pooler network/protocol path. Sequential SQL calls amplify it: five serial round trips have a lower-bound network component of about 355–365 ms, ten about 710–730 ms, and fifteen about 1.07–1.10 s. These are lower bounds for serial calls, not end-to-end P95 estimates.

**Still unknown:** the Supabase project region was not available through authorized project metadata or the staging secret. The pooler host suffix and DNS addresses do not identify the project region. A region mismatch therefore remains a plausible explanation, but cannot be claimed as fact. Render documents Singapore as a service region and separate private networks per region; the database endpoint is external to that private network. Supabase documents shared Session Pooler on port 5432 and shared Transaction Pooler on 6543; this run observed 5432 and did not test 6543.

**Separate finding:** physical connection setup is much slower (P95 about 456 ms) than warm query RTT. The existing application pool avoids that cost for normal reuse, but connection creation or replacement can explain occasional long checkout samples after failures or restarts. This is not evidence that every warm query pays 456 ms.

The earlier four-node staging traces showed multiple sequential Fusion/Tracking database operations and 4–5 checkouts per event, with low Python compute and commit spans. That code structure can magnify a fixed RTT. This phase intentionally does not consolidate queries or alter transaction/lock ordering.

## Actions and limits

1. Confirm the Supabase project region from the Supabase dashboard or authorized management metadata, then compare it with Render Singapore.
2. Obtain Supabase database CPU, I/O, active connections, and slow-query evidence for the same staging window. This probe cannot distinguish pooler queueing from an overloaded database when server execution is not measured for the real application queries.
3. Capture read-only `EXPLAIN (ANALYZE, BUFFERS)` for the highest-latency existing Fusion/Tracking SELECTs using an approved staging fixture. Do not use a guessed table or production data.
4. If region and database health are normal, profile the existing sequential query spans before proposing any query batching. Preserve advisory-lock and event-ordering semantics.

No optimization is applied by this document. The evidence is not a TDOA/localization benchmark; localization was disabled.

## References

- Supabase connection modes: https://supabase.com/docs/guides/database/connecting-to-postgres
- Render regions and private networks: https://render.com/docs/regions
- Render outbound IP ranges: https://render.com/docs/outbound-ip-addresses
