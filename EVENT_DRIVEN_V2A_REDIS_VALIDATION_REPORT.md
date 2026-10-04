# Event-Driven V2-A: real Redis Streams validation

Date: 2026-10-04. Branch: `feat/event-driven-redis-validation`, based on V1
`c57c0260ecdaee5f3d514e184a75bd929092ab8a`. V1 was clean before branching.

Transport validation passed on an actual isolated Redis server. The adapter is
ready for preparing a Redis staging **shadow** review. It is not approved as an
ordered, authoritative Fusion/Tracking executor. Stop here; no shadow deployment
or real-traffic cutover was performed.

## Environment and tests (items 1–7)

1. Actual Redis 7.2.10, community Windows Cygwin port, not fakeredis or an official
   Linux build. Docker was absent and WSL had no usable Linux distribution.
   Downloaded publisher release archive SHA256 verified before extraction.
   Isolated 127.0.0.1 ephemeral port, no public exposure, 128 MiB noeviction,
   AOF appendfsync always, no TLS for loopback. Server stopped and temporary data
   directory removed. Runtime binary remains outside Git for repeatability.
2. redis-py 6.4.0 installed from `requirements-events-redis.txt`; default application
   requirements unchanged.
3. Executed baseline `python -m pytest -q --junitxml=../../redis_v2a_baseline.xml`,
   `python tools/run_local_critical_pg_tests.py`, all `node tests/js/test_*.js`,
   two inline Dashboard `node --check`, Python compileall and `git diff --check`.
   Executed `python tools/validate_real_redis.py --server-binary
   ../../redis-v2a-runtime/Redis-7.2.10-Windows-x64-cygwin/redis-server.exe`.
   The harness supplies only its disposable local Redis URL to pytest and runs
   the full suite plus crash/restart/ACK/retention/ordering/DLQ/payload/load trials.
   After refining overload classification, reran full Python/JS/inline/static
   regression against a fresh real Redis, and recalculated classification from
   the original timestamped samples without inventing new measurements.
4. Baseline: 381 Python passed, 16 skipped, 0 failed; local PG 3 passed, 0 skipped;
   JS 21 files passed, inline syntax 2 passed. Initial real-server suite:
   399 passed, 1 skipped. Final: **402 passed, 1 skipped, 0 failed**, 3 existing
   deprecation warnings. All 15 original Redis cases executed; 3 added real-server
   regressions and 3 overload-classification unit cases passed. **0 Redis-unavailable
   skips.** Remaining full-suite skip requires its separate PostgreSQL DSN; the
   isolated local PG run passed all 3 database cases separately. No assertions
   removed/weakened. Final PG 3 passed, JS 21, inline JS 2, syntax/diff passed.
5. PING, INFO, XADD, XGROUP CREATE, XREADGROUP, XACK executed successfully.
6. XPENDING and exact-ID XPENDING range executed successfully.
7. XAUTOCLAIM and XCLAIM executed successfully; no compatibility fallback needed.
   `outputs/redis_environment.json`, `redis_*_regression.json` contain evidence.

## Recovery and processing semantics (items 8–15)

8. A real subprocess consumer received an event and applied the test ledger marker,
   then was killed before ACK. PEL remained 1. Consumer B claimed the same Redis
   message ID, observed the existing marker, ACKed it, and PEL became 0. Stream
   entry remained; no XDEL. Exact UTC and monotonic timestamps are in
   `outputs/redis_crash_recovery.json`.
9. ACK fault injection used real Redis/redis-py, failing before the command and
   after the server ACKed but before the response was delivered. The first case
   recovered from PEL; the latter has no PEL entry and used explicit semantic
   republish. Both recognized duplicate event_id and kept one synthetic effect.
   This does not claim exactly-once delivery or production database idempotency.
10. Forced Redis process kill and restart using the same AOF directory preserved
    both stream and pending state; client resumed publish/consume/ACK. Outage failed
    after approximately 6.07 seconds with sanitized TimeoutError. No infinite retry.
    This proves the tested process-crash scenario, not OS power-loss durability.
    Non-persistent durability was not claimed. Startup/outage harness initially
    caught ConnectionError only; Redis also raises TimeoutError. Corrected the
    harness exception handling and reran. No adapter reconnect behavior changed.
11. One consumer processed same partition 0,1,2 in order. A deterministic two-consumer
    example completed 11 before 10 for the same partition. **PARTIAL**: V1 has no
    partition ownership/fencing dispatcher; consumer groups do not supply that.
12. Three independent partitions overlapped in execution. Scaling measurements
    below use 1/2/4 real Redis consumers; four showed 2 same-partition completion
    inversions. No domain algorithm was involved.
13. Duplicate delivery was observable and did not duplicate the synthetic effect.
14. The durable test ledger is a Redis SET NX marker. It is deliberately a synthetic
    effect, not a PostgreSQL/domain transaction. Real Fusion/Tracking idempotency,
    outbox and ownership remain prerequisites for an authoritative migration.
15. Malformed JSON, permanent failure, delivery-count retry exhaustion, and injected
    pre-EXEC transaction failure passed. Minimal adapter correction: DLQ now retains
    validated trace_id alongside event_id. Invalid JSON cannot provide validated
    identity and gets empty identity fields. A real-server lost-EXEC-reply test
    showed two DLQ copies with one effective ACK: append+ACK is atomic within each
    Redis transaction, but ambiguous transaction retries are **at least once**.
    No arbitrary payload/exception text/audio/credential copied to DLQ.

## Retention and payload (items 16–17)

16. ACK alone retained stream entries. The isolated single-group exact MINID test
    removed 3 acknowledged entries while preserving/recovering 3 pending entries.
    No automatic retention enabled. Multi-group pending and unread boundaries plus
    replay horizon must gate future trimming. See `docs/redis_retention_strategy.md`.
    [Redis XACK](https://redis.io/docs/latest/commands/xack/) describes ACK/PEL
    semantics; [Redis XTRIM](https://redis.io/docs/latest/commands/xtrim/) documents
    removal and retention boundaries.
17. Envelope JSON sizes: small 409 B, normal 1,433 B, large 65,945 B, oversized
    synthetic 1,048,985 B. Ten oversized entries used about 10.50 MB stream memory
    and raised reported server memory by about 11.52 MB. Recommend a future 64 KiB
    envelope ceiling / 8 KiB metadata budget, subject to actual data inventory.
    No new API size limit imposed. Actual application's max metadata is unknown.
    Audio remains object references; no raw/base64 audio entered Redis.

## Load results (items 18–25)

Synthetic EventEnvelope only, one producer and a 5 ms handler delay, 3 seconds of
production per trial. Node counts are simulated device IDs, not physical Android.
Lag measures publish-to-handler-completion using monotonic time, not network or
first-position latency. Backlog = consumer-group lag + pending; retained ACKed
stream length is separately reported. Every workload drained to lag=0/PEL=0,
all messages processed, no duplicates/retries in these fault-free load trials.

| Nodes | Offered eps | Ingest eps | Consume eps during production | Backlog peak | Lag P95 ms | Drain ms | Overload |
|---|---:|---:|---:|---:|---:|---:|---|
| 4 | 50 | 50.0 | 50.0 | 1 | 7.3 | 1.8 | False |
| 4 | 150 | 150.0 | 147.3 | 8 | 54.5 | 55.8 | False |
| 4 | 400 | 400.0 | 151.0 | 747 | 4777.7 | 5035.4 | True |
| 20 | 50 | 50.0 | 50.0 | 1 | 7.5 | 1.9 | False |
| 20 | 150 | 150.0 | 136.3 | 41 | 282.2 | 284.6 | True |
| 20 | 400 | 400.0 | 142.3 | 773 | 4907.1 | 5169.9 | True |
| 50 | 50 | 50.0 | 50.0 | 1 | 7.0 | 1.0 | False |
| 50 | 150 | 150.0 | 148.3 | 6 | 36.0 | 33.6 | False |
| 50 | 400 | 400.0 | 147.7 | 757 | 4838.0 | 5095.8 | True |
| 100 | 50 | 50.0 | 50.0 | 1 | 7.2 | 1.1 | False |
| 100 | 150 | 150.0 | 149.7 | 2 | 9.4 | 11.6 | False |
| 100 | 400 | 400.0 | 147.0 | 759 | 4830.8 | 5085.0 | True |

18–21. Per-node results and P50/P95/P99, memory/CPU/time-series evidence are in
`outputs/redis_load_{4,20,50,100}_nodes.json`.

22. 50 events/s drained without increasing backlog in every trial. 150 events/s
was marginal: the 20-node run grew about 4.12 backlog entries/s in its latter
observation window. The other 150 runs were flatter. Three-second trials establish
observations, not a long-term sustainable capacity guarantee.
23. Single consumer completed about 142–151 events/s while overloaded at offered
400 events/s. With offered 600, 1/2/4 consumers completed about 154/301/599 events/s
respectively during production. These limits include local AOF/OS/client overhead.
24. All bursts drained: roughly 5.04–5.17 s for the 400 eps single-consumer trials;
9.14/3.10/0.011 s for 1/2/4 consumers at offered 600. Largest tested burst: 1,800
messages per scaling trial, no loss.
25. First observed sustained growth was at 150 eps in the 20-node trial; 400 eps
was overloaded in all four single-consumer trials. Overload uses latter-half ingress
above completion rate and positive continuing backlog growth, with a small noise
floor (>2 net entries and >1 entry/s), not CPU saturation or a 10% rate-gap rule.
A previous draft classifier missed marginal growth; fixed calculation and tested
that regression. No exact saturation threshold determined; longer soak/rate sweep
is needed. Do not extrapolate these results to real Fusion/Tracking capacity.

| Consumers | Ingest eps | Consume eps | Backlog peak | Drain ms | Duplicates | Same-partition completion inversions |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 600.0 | 153.7 | 1339 | 9141.8 | 0 | 0 |
| 2 | 599.9 | 301.3 | 897 | 3100.3 | 0 | 0 |
| 4 | 600.0 | 599.0 | 27 | 11.0 | 0 | 2 |

## Memory, security and next-stage limits (items 26–28)

26. No 128 MiB OOM/eviction observed. INFO memory snapshots and server CPU time
    deltas are saved; CPU percent is normalized to one core, not Render utilization.
    Unbounded ACKed retention and uncapped oversized metadata remain memory risks.
    The tests do not prove behavior at maxmemory; no OOM test was claimed.
27. Loopback-only disposable server, no credentials required or logged. Remote
    Redis requires TLS/authentication/private access. Focused changed-file credential
    URL/private-key scan passed; gitleaks/trufflehog unavailable, so no comprehensive
    history scan claimed. Existing envelope secret/audio rejection tests passed.
    See `docs/redis_security_notes.md` and `outputs/redis_security_review.json`.
28. Ready to review a staging **shadow-only** plan. Before deploying shadow, validate
    the intended Linux/managed Redis version, TLS/ACL, network access and isolation,
    select retention/memory alarms and a rollback gate. Strict per-key ownership,
    domain idempotency/outbox and DB atomicity remain blockers to authoritative
    Fusion/Tracking traffic, not to this isolated transport validation. No staging
    shadow deployment performed in this task.

## Preserved boundaries and flags

Only runtime adapter change is DLQ trace_id retention. main.py, Fusion/Tracking,
PostgreSQL SQL/schema/pool, worker counts, Render resources and PR state unchanged.
No production deployment, staging database writes, real Dashboard broadcast,
localization enablement or Android-to-Redis routing. Optional application flags
remain disabled; Redis harness uses its own isolated URL, not application config.
No V1 refactor. Original checkout/untracked field artifacts were preserved.

```text
EVENT_DRIVEN_PIPELINE_ENABLED=false
REDIS_REAL_TRAFFIC_ENABLED=false
LEGACY_PATH_PRESERVED=YES
REAL_REDIS_INTEGRATION_TESTED=YES
REDIS_STREAMS_ADAPTER_READY=YES
CRASH_RECOVERY_VERIFIED=YES
PENDING_RECOVERY_VERIFIED=YES
AMBIGUOUS_ACK_IDEMPOTENCY_VERIFIED=YES
ORDERING_MODEL_VERIFIED=PARTIAL
OVERLOAD_BEHAVIOR_CHARACTERIZED=YES
REDIS_REAL_TRAFFIC_ENABLED=NO
STAGING_REAL_TRAFFIC_CHANGED=NO
PRODUCTION_CHANGED=NO
READY_FOR_REDIS_STAGING_SHADOW=YES
```

Changed deliverables: `services/events/redis_streams.py`,
`tests/test_event_redis_v2a.py`, `tools/validate_real_redis.py`, the two Redis docs,
this report and `outputs/redis_*.json`. Commit SHA is reported after committing;
the report describes this branch's validated working tree and V1 base.

Final read-only safety check: staging `/runtime-status` returned HTTP 200 and
reported unchanged build `9ba7f800fe30e361b9c07e7dd1c8211dba5a7596` on
`feat/latency-diagnostics-staging`. GitHub PR #5 remained OPEN, Draft, unmerged.
See `outputs/redis_app_safety_snapshot.json`.
