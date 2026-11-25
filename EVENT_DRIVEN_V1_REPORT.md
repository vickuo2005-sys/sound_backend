# Event-driven V1 report

Branch: `feat/event-driven-pipeline-v1`, created from clean HEAD
`afe4501f627040ec40295ceb64b81681b3e515d0` (contains deployed/validated `9ba7f8`).
Original checkout, staging latency branch and all untracked field/schema reports preserved.
No staging/production deployment or environment change performed in this task.

## Requested answers

1. **Legacy behavior:** unchanged by default. Both flags default false; API bodies,
   group/track results and WebSocket frames retain the existing shapes. `/runtime-status`
   has no new `event_bus` key when flags are off. Optional diagnostics add that key only
   for local/staging observation. No durable processing switch exists in V1.
2. **Existing functions reused:** canonical calls remain
   `process_event_initial_submission`, `save_event_with_inserted`,
   `process_event_fusion_for_event` -> `services.event_fusion.process_event`,
   `process_tracking_for_event_group_region`, fallback
   `process_tracking_for_active_alert_region`, `process_tracking_measurement` ->
   `tracking_service.update_track_from_measurement`, and
   `broadcast_event_post_ingest_result`/`safe_dashboard_broadcast`. Explicit injected
   handlers adapt these functions for isolated tests; actual Shadow subscribers only
   observe canonical results and never execute the mutation-capable adapters. No algorithm copied.
3. **Types:** acoustic_event_received, event_persisted, event_fused, position_updated,
   track_updated, event_processing_failed (stable string enum).
4. **Envelope:** immutable dataclass with recursive frozen JSON payload/metadata/extensions;
   original event_id, event_type, schema_version=1, correlation_id, trace_id?, device_id?,
   site_id?, partition_key?, event_time_ms, received_at_ms, payload and metadata.
   Canonical JSON sorting/round-trip validation; additive unknown optional fields preserved
   in extensions; unknown schema versions rejected. No invented site IDs. Received timestamp
   comes from existing backend request time; event time uses canonical device milliseconds,
   existing timestamp, or an explicitly labelled wall-clock fallback. Time differences for
   bus instrumentation use monotonic milliseconds. Credential fields/credential URLs and
   binary/base64/raw audio fields rejected; audio references retained.
5. **Idempotency:** bounded memory active/terminal keys `(version,type,event_id)`; atomic
   duplicate publish detection. Existing event/observation unique constraints audited.
   Memory history eviction and restart allow replay. Tracking/WS distributed idempotency
   is not proven; no claims of durable exactly-once execution. Full contracts in docs.
6. **Partition today:** existing normalized label for metadata/parity; label advisory lock retained.
7. **Why temporary:** one same-label hot partition cannot distribute independent sites;
   device-only keys split multi-device groups. Future site/region + episode assignment
   requires ownership/merge proofs, not an algorithm introduced here. Redis adapter has
   no multi-consumer partition fencing; single-dispatcher tests do not prove distributed ordering.
8. **Redis installed:** Redis server/Docker and redis-py unavailable in this environment.
   Optional client requirement is isolated in requirements-events-redis.txt; default dependencies unchanged.
9. **Redis real staging traffic:** **NO**. Adapter is never imported/instantiated by the request path.
   EVENT_BUS_BACKEND/REDIS_* do not switch live processing in V1; they remain future configuration names.
10. **Duplicated DB writes:** **NO** in shadow. Actual local Fusion DB dump is identical
    before/after observation, and observation count stays 1. Runtime shadow modules contain
    no DB access; only explicitly invoked local-test adapters can call existing mutations.
11. **Duplicated WS:** **NO**. Shadow has no socket/broadcast path. Parity tests require
    exactly the original event_group and track_update messages, including reorder suppression.
12. **Crash recovery:** XREADGROUP/PEL, XACK, XPENDING, XCLAIM/XAUTOCLAIM and bounded
    processing/reconnect primitives implemented and unit-tested. A consumer dying before ACK
    leaves work pending conceptually. Actual server crash/recovery behavior is **NOT TESTED**;
    15 real Redis integration cases skip explicitly. Successful ACK never XDELs or trims.
    Destructive retention remains disabled; pending-safe retention needs real tests before activation.
13. **Tests:** baseline 339 passed/1 skipped; final 381 passed/16 skipped with 3 existing
    deprecation warnings. Skips: 15 real Redis cases unavailable; 1 PG-dependent case in the
    default suite. Disposable PostgreSQL 17 loopback run: 3 passed/0 skipped. JS: 21 files
    passed. Two Dashboard inline scripts passed node --check. compileall and git diff --check passed.
14. **Before cutover:** real Redis integration + crash/ambiguous reconnect/retention tests,
    durable PG-to-stream publish boundary (outbox or proven equivalent), tracking point
    replay uniqueness/fencing, partition ownership/recovery order, bounded backlog/recovery
    controls, canonical WS duplicate semantics and another correlated real-device canary.
    Handler projections prove serialization/payload parity, not independently recomputed
    numerical output or Redis performance. No live canary enabled here.
15. **Rollback:** current staging stays on 9ba7f8, so no live rollback required. For any later
    V1-only deployment set both EVENT_DRIVEN_* flags false; if needed redeploy exact 9ba7f8.
    No schema/data rollback, DB URL, resource or worker changes needed. New migration branch
    can be abandoned without changing the latency branch. Future ownership cutovers require
    drain/fence/reconcile steps; never run legacy and durable mutating consumers on the same IDs.

## Architecture load evidence

Local synthetic envelopes only; no DB/Fusion/Tracking/Android/network work is included.
Single memory dispatcher, 128 active-capacity bound, 256 terminal-history bound,
explicit drain/backpressure when full. Not a production/field latency or capacity claim.

| Nodes | Synthetic envelopes | Overall events/s | Lag P95 ms | Peak Python allocations bytes |
|---:|---:|---:|---:|---:|
| 4 | 80 | 7,986 | 3.37 | 101,339 |
| 20 | 400 | 16,012 | 9.45 | 235,521 |
| 50 | 1,000 | 19,814 | 7.00 | 328,344 |
| 100 | 2,000 | 20,149 | 6.81 | 489,350 |

All published envelopes consumed, zero terminal failures/order violations, empty final queues.
Peak queue <=128. Larger bursts explicitly reject-at-capacity/retry publication after draining;
these rejections are visible counters, not dropped events. Allocation figures are tracemalloc,
not RSS/Render memory. Throughput varies by machine and trivial handler work; no SLA inference.
Separate concurrency test: 100 simultaneous identical publications -> 1 accepted, 99 duplicates,
exactly 1 consumer effect. Queue, dedupe, context, phase-history and failure buffers are bounded
by count; an envelope's JSON byte size is not separately capped in V1.

## Validation repairs and limits

An API-parity test first failed because its two requests had different existing timing values;
the test now uses identical deterministic clocks and retains an exact full-body assertion.
No existing assertion/test was removed or weakened. Adapter review found that redis-py resets
a Pipeline after execute failure; the DLQ transaction is rebuilt per reconnect attempt and
has a regression test. Payload rejection covers raw/base64 audio, not just Python bytes.
Observation phase-order validation and exception-duration recording have regression tests.

Shadow metrics are event_bus_publish/queue_wait/handler_duration/end_to_end and per-handler
duration summaries (rolling n/P50/P95/P99/max); retry/duplicate counts are counters, not fake
millisecond values. Diagnostics expose enabled/shadow flags, reserved pipeline flag, memory
implementation, queue/peak/publish/consume/retry/failure counters, ordering/errors/evictions,
and sanitized failure inspection. No PostgreSQL metrics table or external telemetry dependency.
Shadow is synchronous observation under bounded locks, adds no worker, and may add overhead
when explicitly enabled; it is not evidence of production throughput or improved first-position SLA.

## Files and evidence

Code: services/events/{types,envelope,bus,memory_bus,partitioning,result,shadow,redis_streams}.py,
handlers/{base,persistence,fusion,tracking,realtime}.py, minimal main.py hooks, optional dependency file.
Tests: test_event_envelope, test_event_memory_bus, test_event_shadow, test_event_bus_load,
test_event_redis_adapter, test_event_redis_integration. Tool: tools/benchmark_event_bus.py.
Docs: current flow audit, partitioning strategy, idempotency contract and Redis cutover plan.
Evidence: outputs/event_driven_{python_tests,postgres_tests,js_tests,syntax,load}.json.

LEGACY_PATH_PRESERVED = YES

EVENT_DRIVEN_ABSTRACTION_READY = YES (local/shadow V1 scaffolding; not durable/live cutover)

REDIS_STREAMS_ADAPTER_READY = NOT_TESTED (unit contracts pass; actual Redis unavailable)

REDIS_REAL_TRAFFIC_ENABLED = NO

PRODUCTION_CHANGED = NO

Consumer-group/recovery semantics follow official [XREADGROUP](https://redis.io/docs/latest/commands/xreadgroup/)
and [XAUTOCLAIM](https://redis.io/docs/latest/commands/xautoclaim/) documentation; source links also appear
in the idempotency and cutover docs. These sources do not replace the skipped live integration evidence.
