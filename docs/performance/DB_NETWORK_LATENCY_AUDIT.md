# PostgreSQL / Network Latency Audit

Date: 2026-09-30  
Branch: `feat/latency-diagnostics-staging`  
Benchmark runtime: `4c6bf7ceea8f58c10598f9d2d87eda7b8e985bed`

This audit is diagnostic only. It does not change SQL semantics, database URLs, pool limits, worker counts, Render plans, production settings, or localization/TDOA.

## Infrastructure

### Render staging

Verified from `render.staging.yaml`:

- Region: Singapore
- Plan: Starter
- Instances: 1
- Start command: Uvicorn with 1 worker
- Application pool: `psycopg2.pool.ThreadedConnectionPool`
- Pool defaults: `POSTGRES_POOL_MIN=1`, `POSTGRES_POOL_MAX=20`
- Pool acquire timeout: `POSTGRES_POOL_ACQUIRE_TIMEOUT_SECONDS`, default 5 seconds
- Probe flag: `STAGING_DB_LATENCY_PROBE_ENABLED=false`

### Supabase

The staging `DATABASE_URL` is not present in this Codex environment. Render masks the value in its UI, and no authorized Supabase CLI or management credential is available here.

- Region: **could not be determined safely**
- Endpoint type: **could not be determined safely**
- Port: **could not be determined safely**
- Direct versus pooler: **could not be determined safely**

No username, password, DSN, token, or credential was printed or committed.

The repository documentation says staging is intended to use an isolated Supabase Session Pooler URI, but that is configuration intent, not runtime evidence.

## Architecture

```text
Android nodes
    -> Render Singapore FastAPI / Uvicorn (1 worker)
    -> application psycopg2 ThreadedConnectionPool (min 1, max 20)
    -> configured Supabase PostgreSQL endpoint (runtime endpoint unknown here)
    -> PostgreSQL
```

`get_postgres_pool()` creates the application pool lazily from `DATABASE_URL`. `get_postgres_connection()` acquires a bounded semaphore, calls `pool.getconn()`, rejects closed connections, performs `rollback()` before reuse, and wraps the connection. `PooledPostgresConnection.close()` rolls back before returning the connection; failed health/checkout paths close the physical connection. There is no `SELECT 1` validation query on every checkout. The only explicit probe query is the disabled `/diagnostics/db-latency` endpoint.

This is application-side pooling. If the runtime URL is a Supabase Session or Transaction Pooler URL, it is therefore a two-layer path (application pool plus Supabase pooler). The double-pooling conclusion is conditional until the redacted runtime host and port are verified.

## Evidence from the latest four-node run

Source: `outputs/phase3_3_final_android_runtime_status_20260930_010913.json`.

The run had four node WebSockets and `localization_enabled=false`.

| Stage | n | P50 ms | P95 ms | P99 ms |
|---|---:|---:|---:|---:|
| `postgres_pool_acquisition` | see runtime traces | see runtime traces | see runtime traces | see runtime traces |
| `event_db_connection_acquisition` | 16 | 534 | 986 | 1193 |
| `event_db_write` | 16 | 1480 | 2147 | 2262 |
| `fusion_transaction_sql_ms` | 8 | 879 | 1335 | 1525 |
| `fusion_transaction_lock_ms` | 8 | 145 | 229 | 264 |
| `fusion_transaction_python_ms` | 8 | 147 | 182 | 197 |
| `fusion_transaction_commit_ms` | 8 | 73 | 75 | 75 |
| `fusion_transaction_idle_ms` | 8 | 347 | 962 | 982 |
| `event_fusion` | 8 | 2258 | 3081 | 3166 |
| `region_tracking` | 8 | 2612 | 6180 | 6525 |
| `post_ingest_queue_wait` | 8 | 6704 | 10122 | 10650 |
| `post_ingest_pipeline` | 8 | 6204 | 13095 | 14869 |

Pool counters in the same run: `max_size=20`, peak checked out 8, acquire timeouts 0, creation failures 0, waiting requests 0. This does not support a pool-at-max explanation.

The corrected aggregate diagnostics now expose the Fusion transaction fields. Commit P95 around 75 ms and Python compute P95 around 182 ms make Python compute and commit unlikely to explain the multi-second wall time. Pool acquisition and transaction idle time remain candidates for network/connection lifecycle or unaccounted synchronous work.

Clock quality must be treated separately: the run reported materially different per-device offsets, including approximately 4354 ms for node A03. This affects cross-device timestamp interpretation, but does not by itself prove database latency.

## Connection lifecycle and checkout count

The latest traces show approximately 4–5 PostgreSQL checkouts per post-ingest event, depending on the tracking path. The observed purposes are:

- Fusion event load / Fusion transaction
- Tracking source load
- Tracking track lookup
- Tracking save or fallback tracking path
- Tracking point/history load

The Fusion event-load connection is reused for the Fusion transaction. Tracking lookup is reused where the current path supports it; fallback paths can still create additional checkouts. There is no evidence of pool exhaustion in the run.

## SQL round-trip audit

These are code-level estimates for one event; exact counts depend on whether a group/track exists and which branch is taken.

| Operation | Estimated SQL statements / round trips | Notes |
|---|---:|---|
| Initial event submission | 1 INSERT/UPSERT with `RETURNING` plus transaction commit; connection acquisition is separate | Measured acquisition and insert/commit stages exist. |
| Fusion event load | 1 SELECT | Connection is reused for the Fusion transaction. |
| Fusion lock | 1 `pg_advisory_xact_lock` | Must remain inside the transaction. |
| Fusion candidate/group lookup | 1 SELECT, potentially followed by group payload/history SELECTs | Candidate selection is Python-side after rows are fetched. |
| Fusion observation load | 1 SELECT | Existing query is separately instrumented. |
| Fusion group save | 1 INSERT or UPDATE, with branch-dependent cleanup | Save timing is materially larger than individual lookup/observation saves. |
| Fusion observation save | 1 INSERT/UPSERT | Branch-dependent. |
| Fusion cleanup/final reload | 1 or more UPDATE/SELECT statements | Must not be combined without preserving transaction and advisory-lock semantics. |
| Region/active tracking source load | 1 or more SELECTs | Source and point/history loads are separate paths. |
| Track lookup | 1 SELECT | Existing-track branch only. |
| Track save | 1 INSERT/UPDATE plus possible point/history SELECT | Branch-dependent and may include a commit. |

### Candidate query consolidation

- **High confidence:** keep the existing connection reuse; it removes repeated physical checkout without changing SQL semantics.
- **Medium confidence:** combine read-only candidate/group payload reads into one snapshot query or CTE after confirming row cardinality and lock behavior; this requires staging query-plan evidence first.
- **Medium confidence:** batch independent point/history reads when the caller already has one track id and ordering is preserved.
- **Do not combine:** advisory lock acquisition, group selection, and writes across transaction boundaries. The lock and write ordering are part of Fusion correctness.
- **Do not combine yet:** Fusion/Tracking queries across separate workers or mailboxes; their transaction and event-ordering contracts are different.

## Query-plan and probe status

No `EXPLAIN (ANALYZE, BUFFERS)` was run. The required staging DSN is unavailable here, and no safe SQL console or Supabase metrics credential is present. No missing-index or bad-plan claim can be confirmed from this environment.

The existing staging-only probe is implemented at `main.py:/diagnostics/db-latency` and uses one pooled checkout plus `SELECT 1`; it is protected by the normal upload token and disabled by default in `render.staging.yaml`. The helper `tools/measure_staging_db_latency.py` can collect repeated samples once an operator temporarily enables the flag in staging. It currently does not separate DNS, physical connection establishment, transaction `BEGIN`/`COMMIT`, or warm versus new physical connections, so those measurements remain unavailable.

## Root-cause ranking

### Confirmed

1. The service uses psycopg2 application-side `ThreadedConnectionPool`, with rollback-on-return and a bounded semaphore.
2. The latest run has high queue and wall time while Fusion Python compute and commit are low.
3. The pool was not at its configured max and recorded no acquire timeout or creation failure.
4. Four-node tracking/fusion paths perform multiple sequential database operations and 4–5 checkouts per event in observed traces.

### Strongly suspected

1. Render-to-database round-trip or endpoint/pooler latency contributes to pool acquisition, transaction SQL, and idle hold time.
2. Sequential SQL round trips in Fusion and Tracking amplify per-query network latency.
3. A two-layer application pool plus Supabase pooler may add connection lifecycle overhead if the runtime URL is a pooler endpoint.

### Possible

1. Supabase region mismatch or database compute/I/O pressure.
2. A missing index or poor query plan in tracking history, Fusion group lookup, or observation lookup.
3. Render Starter CPU or CPU throttling. Current Python timings and queue/DB evidence make Render CPU unlikely to be the primary cause, but no Render CPU time-series was exported for the exact benchmark window.

## Recommended next actions

1. From Render staging, record only redacted `DATABASE_URL` host type and port, and confirm the Supabase project region. Compare it with Render Singapore.
2. Temporarily enable the existing staging-only probe for a bounded run and collect 30 warm samples plus a separately controlled new-connection sample. Keep the flag off afterward; do not expose credentials.
3. During the same benchmark window, obtain Supabase CPU, memory, active connections, I/O, cache hit ratio, and slow-query data, then run read-only `EXPLAIN (ANALYZE, BUFFERS)` for the highest-latency tracking/Fusion SELECTs in staging only.

Do not change the pool max, Render plan, worker count, DATABASE_URL, SQL semantics, or localization/TDOA until those three evidence sets distinguish network/connection overhead from database execution time.

## Limitations

- Supabase region, endpoint type, endpoint port, warm `SELECT 1` P50/P95, and physical connection P50/P95 could not be safely obtained from this environment.
- No query plan, Supabase resource metrics, or Render CPU time-series was available.
- The benchmark had localization disabled; it is not evidence about TDOA/localization performance.

