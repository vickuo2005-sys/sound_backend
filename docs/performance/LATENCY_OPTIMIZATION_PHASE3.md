# Latency Optimization Phase 3

## Confirmed bottlenecks

The four-node staging run at `a048e2e` showed high aggregate latency, with small sample counts: `event_fusion` P95 about 5.02 s, `active_alert_tracking` P95 about 8.18 s, `post_ingest_pipeline` P95 about 12.41 s, and multi-second queue waits. The breakdown identified PostgreSQL connection acquisition, advisory lock wait, sequential tracking reads, and group saves as the first optimization targets. `node_A03` clock quality (about 3835 ms offset and 216 ms/min drift) is a separate blocker for Timestamp-TDOA and is not changed here.

## Changes made

1. The existing bounded `ThreadedConnectionPool` remains the only PostgreSQL connection source. Each checkout still has an explicit wrapper, rollback on return, pool return on close, bounded semaphore acquisition, and close-on-health failure behavior. The per-checkout `SELECT 1` health query was removed because it added a round trip to every operation and was directly included in the connection-acquisition stage. A `postgres_pool_acquisition` sample is now recorded.
2. Device-status jobs use a separate bounded executor (`DEVICE_STATUS_WORKERS`, default 1). Post-ingest worker count remains unchanged. Pending and peak counters remain separate, and submit/cancel/exception paths retain the existing lifecycle handling.
3. A bounded in-memory `recent_traces` collection records the most recent event id, total post-ingest duration, and stage durations already emitted by the diagnostics sampler. It is exposed through `/runtime-status`; no database or audio data is written.

## Lock and query safety

The PostgreSQL advisory transaction lock is still present and the Fusion mutation sequence is unchanged. No lock removal, SQL semantic change, tracking mathematics change, schema change, or TDOA/localization change was made. Fusion still performs its reads and writes in the same transaction and the same serialized critical section. The next optimization candidate is narrowing that section only after concurrent-group tests and query evidence justify it.

Tracking association calculations are unchanged. The separate executor prevents device-status work from occupying post-ingest worker slots; it does not increase the post-ingest worker count and defaults to one device-status worker to keep connection pressure bounded.

## Before and expected effect

Before Phase 3, connection acquisition P95 was about 1.42 s and device-status/post-ingest queue waits reached about 9.60 s / 11.44 s under four-node load. Removing the extra pool validation query should reduce per-operation acquisition overhead; separating the bounded device-status queue should reduce cross-queue starvation. Exact improvement must be measured after deployment with the same four-node procedure.

## Remaining risks

- The current pool size and database capacity must be checked together with `DEVICE_STATUS_WORKERS`; do not raise either blindly.
- Advisory-lock wait and Fusion group-save P95 can still dominate under concurrent labels.
- `recent_traces` is process-local and resets on deploy/restart; traces are bounded and may not contain every stage when a path exits early.
- TDOA/localization remains unvalidated until localization is enabled and clock quality, especially `node_A03`, is corrected.

## Staging validation procedure

1. Deploy only the Phase 3 branch to `sound-backend-staging` and verify the Render commit in `/runtime-status`.
2. Confirm `/health` is healthy and `pending_jobs` returns to zero.
3. Run the four-node Android procedure with fixed staging locations and the same event conditions used for the Phase 2 baseline.
4. Save `/runtime-status` before and after the run, including `recent_traces`, queue peaks, `postgres_pool_acquisition`, Fusion stages, tracking stages, and event DB stages.
5. Compare P50/P95/P99 by stage; do not add stage percentiles to claim an end-to-end percentile. Review Render logs for exceptions, OOM, or restarts.

## Phase 3.1: wall-time accounting before further optimization

The follow-up four-node run on `8570e63b` confirmed that Fusion's named child
stages explain only part of its wall time. The representative traces show
roughly 0.9–1.2 seconds of named child work inside 2.6–5.0 second
`event_fusion` spans; the remaining time is now exposed as
`fusion_unaccounted_ms` rather than being attributed to a guessed query.
This is an accounting result, not proof of a specific database bottleneck.

Diagnostics now retain bounded per-event `stage_samples`, repeated PostgreSQL
acquisition entries with a purpose/context label, total and maximum pool wait,
connection hold/transaction duration, and pool counters (checked out, idle,
peak checked out, creation failures, and acquire timeouts). The runtime payload
continues to keep these values in process memory only.

Tracking traces similarly retain sequential stage samples and expose
`tracking_unaccounted_ms`. Existing tracking and Fusion SQL, lock scope, and
association math remain unchanged until a larger sample and concurrency-safe
query evidence are available.

The observed 53 sequence gaps are most consistent with state loss on backend
restart while Android process sessions continued their sequence numbers. The
first observation for an unknown `(device_id, process_session_id)` now
establishes a baseline; later sequence jumps still create real gap metrics.
This rule is covered by restart and subsequent-gap tests.

The next optimization should use the new traces to identify the residual
region and connection hold scope. Do not increase pool or worker limits, narrow
the advisory lock, or change tracking/TDOA behavior until that evidence is
collected.
