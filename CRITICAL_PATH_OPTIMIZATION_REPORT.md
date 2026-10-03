# Critical path optimization report

Date: 2026-10-04. Draft PR #5, branch feat/latency-diagnostics-staging. Instrumentation baseline: f56faae. Validated code commit: 9ba7f800fe30e361b9c07e7dd1c8211dba5a7596. No deployment this round; Singapore staging remains on its previously validated application commit b3ed190. No production/settings/worker/algorithm change.

## Outcome

**SQL reduction is verified; a wall-time improvement is not established. FIRST_POSITION_P95_LT_1S = INSUFFICIENT_SAMPLE. INSUFFICIENT_SAMPLE_FOR_FIELD_SLA = YES.** No real Android events were collected this round.

## Required first-position path

Persist/idempotently ingest event, preserve effective location, enqueue/start worker, acquire label advisory lock, resolve group, persist observation, roll up membership/times, compute/save region, merge consistently, cleanup and commit, then broadcast a valid event_group. Current code additionally runs tracking before broadcasting. Its enrichment can delay first group position, but it remains ordered because moving it requires separate group/track revision and merge consistency proof. Dashboard receive/store/renderMap return is timed separately; it is not visible paint.

## Changes and preserved behavior

- Rollup uses one existing observation summary query instead of separate devices and relative-times queries. Empty IDs and null timestamps preserve the legacy rollup payload; REST defaults remain unchanged.
- PostgreSQL region UPDATE RETURNING replaces immediate group reload. SQLite keeps its old SELECT. Local PostgreSQL execution and Singapore read-only trigger audit passed.
- Tracking skips stale-track points enrichment only where the returned list is unused. Cleanup updates/cache invalidation and all other enriched callers remain.
- Fixed-location JOIN, minimal payload, track save RETURNING, combined candidate query, early broadcast and merge/cleanup deferral were not applied. Locks, transaction boundaries, idempotency, windows, gates, alpha/beta, speeds and worker counts remain.

Per-event traces expose monotonic T0–T14 where executed, first_position_backend, fusion_to_position, existing post_ingest_queue_wait and tracking_followup. SQL counts are event scoped, not global. Independent device status/reorder-tail SQL is explicitly excluded; missing milestones are not zeros. Browser staging timings have 256-sample bound and use the existing throttled panel, with no per-message API fetch. Diagnostics rendering now shares its one-second throttle with renderHealth; a new runtime object still renders immediately.

## Local synthetic benchmark

Seven scenarios, 50 iterations each, 550 measured events per before/after run. Existing ingestion/worker/Fusion/Tracking/persistence/send_json paths execute against temporary SQLite with a memory socket. HTTP/DB/WebSocket network and browser paint are absent. Pool and PostgreSQL advisory-lock measurements are N/A, not zero.

| Scenario | n | SQL total P50 before → after | First backend P50 before → after ms | P95 before → after ms | After max ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| single_event | 50 | 28 → 27 | 54.66 → 65.47 | 104.01 → 86.89 | 134.82 |
| 2_node_burst | 100 | 34 → 33 | 117.13 → 162.51 | 200.53 → 191.10 | 223.68 |
| 4_node_burst | 200 | 27.5 → 26 | 194.56 → 287.22 | 306.16 → 360.32 | 405.86 |
| repeated_same_group | 50 | 26 → 25 | 52.32 → 77.65 | 103.29 → 87.90 | 119.69 |
| new_group | 50 | 28 → 27 | 52.31 → 71.20 | 231.46 → 75.14 | 165.82 |
| merge_case | 50 | 47 → 44 | 51.90 → 81.39 | 124.82 → 88.57 | 103.20 |
| tracking_update | 50 | 26 → 25 | 45.81 → 77.59 | 69.97 → 86.86 | 128.72 |

| Population (measured events) | Before P50 / P95 ms | After P50 / P95 ms | After max ms | n before / after |
| --- | ---: | ---: | ---: | ---: |
| first_position_backend_ms | 104.49 / 268.12 | 149.71 / 340.26 | 405.86 | 550 / 550 |
| fusion_ms | 35.03 / 125.21 | 45.01 / 156.44 | 216.78 | 550 / 550 |
| tracking_ms | 11.33 / 77.02 | 22.51 / 103.03 | 159.53 | 550 / 550 |
| queue_wait_ms | 0.71 / 65.40 | 1.37 / 153.49 | 197.98 | 550 / 550 |
| tracking_followup_ms | 13.64 / 82.70 | 24.87 / 109.20 | 161.05 | 441 / 450 |

Every percentile above is computed directly from its own correlated event population; no stage percentile was summed. SQL medians in burst cases are descriptive: concurrent SQLite lacks PostgreSQL advisory locking, so grouping/merge paths and interleavings vary. Different stages have different valid populations.

The initial after run overlapped local tests/PostgreSQL startup. Both initial runs are retained. Before/after were subsequently rerun sequentially from baseline export/current code. A prior sequential after run still had single-event max about 3.65 s and four-node max about 4.88 s (retained as critical_path_after_sequential_review.json). The final after rerun followed the successful-socket milestone correction and retains full timestamps/stages; its maximum is about 406 ms. This does not erase the earlier tails or establish a causal improvement. Query count alone does not explain them. Correlated samples show large Fusion time, and in bursts queue/tracking contributions, with small WebSocket send time. Local SQLite lock/file-I/O or host scheduling is a suspected contributor, not a proven root cause. No faster-only trial or outlier filtering is used.

## Correctness and test execution

- Final python -m pytest -q: **339 passed, 1 skipped, 3 deprecation warnings**. The skipped case requires the optional loopback PostgreSQL fixture.
- tools/run_local_critical_pg_tests.py: **3 passed, 0 skipped**, disposable PostgreSQL 17, loopback only, no cloud writes. These rerun two SQLite cases plus the skipped PostgreSQL case; do not add them as three unique tests to the full-suite count.
- All **21 JavaScript test files passed**, including correlated browser timing, malformed diagnostics and 1000-message throttle checks. Python syntax compilation and git diff --check passed.
- Existing Fusion/device-location/tracking suites cover resend uniqueness, label separation, time/late attach, merge preservation, node counts, fixed precedence, relative times, association, rejection, duplicate points and reorder behavior. New tests verify legacy payload equivalence on SQLite/PostgreSQL, counted query reduction, stale cleanup default/fast paths, real local request→executor→socket correlation, concurrent counters, failed SQL/WS, invalid samples, bounded traces and scope restoration.

Earlier validation failures and fixes: import-string wiring test (1 failed/50 passed) was resolved by retaining the existing import; a new trace-scope test (1 failed/3 passed) exposed a default-sentinel bug and was fixed; two new fixture assertions initially expected empty-device reporting and a points field, but the actual legacy region excludes empty IDs and uses recent_points—the equality assertion remained intact. The first benchmark attempt did not wait for all worker work/SQLite handles; the harness now drains worker completion and collects released handles. Windows pg_ctl pipe capture caused a local harness wait; stdout/stderr redirection and JUnit counts now verify execution/shutdown. No existing test was removed or weakened. Intermediate successful subsets: 51, then 55, then 42, then 49 tests; earlier full suite was 332 passed/1 skipped before further attribution/gating/throttle regression tests were added.

## Next validation and deployment recommendation

The branch is suitable for review and a deliberate staging-only measurement run after reviewing the remaining timing/attribution limits. It is not evidence of a performance improvement or field SLA. No new staging version was deployed this round. Keep localization disabled. Run the same 30–50 real Android events, correlate backend and browser eligibility, capture CPU/memory and connection/pending metrics, and compare before/after under consistent conditions. Buffered tracking followup attribution remains explicitly unavailable. Do not promote or change workers/resources based on these synthetic percentiles.

## Files

Code: main.py, services/event_fusion.py, services/latency_diagnostics.py, templates/dashboard_v2_4.html. Tests: tests/test_critical_path.py, tests/test_critical_path_optimization.py, tests/js/test_critical_path.js, tests/js/test_dashboard_latency.js. Tools: tools/benchmark_critical_path.py, tools/run_local_critical_pg_tests.py. Audit: docs/critical_path_audit.md. Required outputs: outputs/critical_path_before.json, outputs/critical_path_after.json, outputs/sql_round_trip_audit.json, outputs/first_position_benchmark.json. Supporting initial runs, PostgreSQL/JS results and trigger inventory are retained. No DSN/password/token/raw audio is in reports.


The benchmark first-position endpoint is a completed memory-socket send, not acknowledged receipt or visible paint. Baseline collected after manager broadcast returned; with one memory client the final first-success marker measures the same path up to the negligible subsequent manager bookkeeping. Tracking duration includes executed wrapper decisions/skips; tracking_followup uses the separate emitted-track population. Final fixtures also verify production tracing stays disabled even if its diagnostic flag is set, long event IDs remain reversible, a newly connected client cannot produce a false successful-send sample, and all reorder flush contexts are cleared.
