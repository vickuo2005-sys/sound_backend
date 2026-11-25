# Post-inference latency baseline (V2.2)

Date: 2026-08-24
Backend baseline: `staging` at `45c342dd5448e9e42acddfdabbca9298ba88a55c`
Flutter baseline: `638bb99` plus the preserved V2.2 dirty working tree

## Baseline critical path

The code-level path before this patch is:

```text
Android PCM sliding window saved
  -> Flutter handleSavedAudioEvent
  -> AI inference completes
  -> AudioEvent constructed
  -> startEventCloudPipeline
  -> SharedPreferences queue load/decode/encode/save
  -> processEventUploadQueue
  -> package:http top-level post (new Client per request)
  -> HTTPS POST /events
  -> token and metadata validation
  -> asyncio.to_thread(process_event_initial_submission)
  -> event UPSERT + commit
  -> fixed-location cache lookup
       -> cache miss/expiry: synchronous device_locations SELECT
  -> fixed-location enrichment
  -> event_trigger task scheduled
  -> device-status and fusion/tracking work scheduled
  -> HTTP 200
  -> Dashboard WebSocket event_trigger handler
  -> event/device state update
  -> marker, alert, timeline, and map render synchronously
```

Corrections to the initial architecture hypothesis:

- GCS upload, MP3 encoding, and TDOA clip creation/upload are not on the first-alert path.
- Fusion, localization, and tracking run in `post_ingest_executor` and do not block `/events`.
- Device-status persistence is submitted to the same background executor and does not block the ACK.
- PostgreSQL event persistence is one `INSERT ... ON CONFLICT ... RETURNING` statement. The transaction commit is still awaited before ACK, preserving durable-before-success semantics.
- A fresh fixed-location cache adds no PostgreSQL statement. An expired or cold cache adds one synchronous `SELECT ... FROM device_locations` before `event_trigger` is scheduled.
- PostgreSQL schema inspection is not used by the event UPSERT. Schema lookups exist in other device-status paths and use a separate TTL cache.
- The active Dashboard already renders an `event_trigger` directly; it does not wait for the five-second `refreshAll()` poll. The unused legacy Dashboard still contains the old refresh behavior but is not routed.

## Modified critical path

With the feature flags enabled, the first-alert path is:

```text
AI confirmed
  -> create AudioEvent + trace_id/event_id
  -> start SharedPreferences persistence (background future)
  -> immediately start metadata POST on a long-lived http.Client
  -> await HTTP and persistence before committing retry/success queue state
  -> Backend validation
  -> one durable event UPSERT + commit
  -> fixed-location lookup
       -> fresh cache: memory
       -> TTL-expired cache: stale value now, refresh in background
       -> cold/explicitly invalidated cache: synchronous DB load
  -> schedule event_trigger WebSocket task
  -> enqueue device status and fusion/tracking work
  -> HTTP 200 + Server-Timing
  -> browser WebSocket state update and immediate render
```

The metadata request no longer waits for SharedPreferences serialization. Audio encode/GCS/TDOA remain behind metadata and never enter this await chain.

## Arrival ordering analysis

`post_ingest_executor` currently has two workers, so event N+1 can finish fusion/tracking before event N. Fusion uses phone-observed event time and supports late attachment, which reduces grouping damage. Tracking is stricter: non-increasing measurement times are rejected, so reversed worker completion can produce a missing point or apparent discontinuity even though the first Dashboard alert is correct.

This branch deliberately does not put an ordering queue in front of `event_trigger`. If staging traces show this reorder in practice, the next safe experiment is a post-ACK, per-region/per-track serial sequencer with a short event-time reorder buffer and bounded timeout. Arrival time should remain diagnostic only. A global queue would unnecessarily couple independent nodes and is not recommended.

## Reproducible pre-change local measurement

Environment: Windows local process, FastAPI `TestClient`, temporary SQLite database, fusion/tracking and device-status workers stubbed so the measurement isolates synchronous `/events` ingest. Each scenario submitted 50 target events sequentially. These numbers are not a production-network or Android-to-browser benchmark.

| Nodes | Events | HTTP `/events` p50 | p95 | p99 | max |
|---:|---:|---:|---:|---:|---:|
| 1 | 50 | 9.477 ms | 12.931 ms | 29.852 ms | 29.852 ms |
| 2 | 50 | 11.739 ms | 14.815 ms | 21.048 ms | 21.048 ms |
| 4 | 50 | 12.042 ms | 15.285 ms | 16.851 ms | 16.851 ms |

The local result shows that Python/SQLite ingest is not large enough to explain multi-second alerts. The unmeasured production candidates are Android queue persistence, TCP/TLS setup from top-level `http.post`, mobile network RTT, Render-to-PostgreSQL latency, and browser paint time.

## Post-change local measurement

The same 1/2/4-node, 50-event local SQLite scenario was repeated after tracing and fast-path changes. `FAST_EVENT_INGEST_ENABLED` intentionally does not bypass SQLite fixed-location reads, so this run validates overhead and stage accounting rather than the PostgreSQL stale-cache optimization.

| Nodes | Stage | p50 | p95 | p99 | max |
|---:|---|---:|---:|---:|---:|
| 1 | HTTP total | 10.806 ms | 15.941 ms | 30.060 ms | 30.060 ms |
| 1 | DB commit | 3.740 ms | 8.780 ms | 10.720 ms | 10.720 ms |
| 1 | fixed location | 2.520 ms | 7.210 ms | 8.660 ms | 8.660 ms |
| 1 | backend ingest | 7.760 ms | 13.900 ms | 14.630 ms | 14.630 ms |
| 2 | HTTP total | 10.126 ms | 14.951 ms | 17.650 ms | 17.650 ms |
| 2 | DB commit | 3.060 ms | 7.740 ms | 8.960 ms | 8.960 ms |
| 2 | fixed location | 2.630 ms | 6.750 ms | 7.050 ms | 7.050 ms |
| 2 | backend ingest | 7.890 ms | 13.290 ms | 16.570 ms | 16.570 ms |
| 4 | HTTP total | 9.760 ms | 14.868 ms | 25.946 ms | 25.946 ms |
| 4 | DB commit | 2.820 ms | 7.600 ms | 10.580 ms | 10.580 ms |
| 4 | fixed location | 2.510 ms | 7.320 ms | 15.340 ms | 15.340 ms |
| 4 | backend ingest | 7.150 ms | 13.300 ms | 23.170 ms | 23.170 ms |

The tracing overhead stayed in the low-millisecond range and did not create a multi-second tail. No Android device, mobile network, staging PostgreSQL, or real browser was available in this local run, so queue, TCP/TLS reuse, WebSocket transit, browser render, and full AI-finished-to-render percentiles remain explicitly unmeasured rather than estimated.

## Live local HTTP + WebSocket + browser benchmark

A second run kept a real Chromium Dashboard connected to a local Uvicorn process. Each 1/2/4-node scenario submitted 50 target events through a persistent `httpx.Client`; the backend performed real SQLite durability plus background fusion/tracking, and the browser performed the production `event_trigger` handler and double-`requestAnimationFrame` render measurement.

| Nodes | Stage | p50 | p95 | p99 | max |
|---:|---|---:|---:|---:|---:|
| 1 | metadata HTTP | 33.98 ms | 101.51 ms | 171.44 ms | 171.44 ms |
| 1 | backend DB | 23.00 ms | 80.56 ms | 163.28 ms | 163.28 ms |
| 1 | fixed location | 3.34 ms | 10.75 ms | 20.22 ms | 20.22 ms |
| 1 | backend ingest | 30.14 ms | 89.38 ms | 165.53 ms | 165.53 ms |
| 1 | backend WS -> browser | 1.00 ms | 21.00 ms | 45.00 ms | 45.00 ms |
| 1 | WS receive -> render | 22.40 ms | 43.10 ms | 58.40 ms | 58.40 ms |
| 1 | synthetic AI finish -> render | 71.00 ms | 125.00 ms | 190.00 ms | 190.00 ms |
| 2 | metadata HTTP | 45.72 ms | 146.09 ms | 301.16 ms | 301.16 ms |
| 2 | backend DB | 27.38 ms | 113.97 ms | 287.79 ms | 287.79 ms |
| 2 | fixed location | 3.80 ms | 13.89 ms | 16.60 ms | 16.60 ms |
| 2 | backend ingest | 35.05 ms | 139.22 ms | 293.42 ms | 293.42 ms |
| 2 | backend WS -> browser | 2.00 ms | 24.00 ms | 34.00 ms | 34.00 ms |
| 2 | WS receive -> render | 29.10 ms | 45.60 ms | 65.70 ms | 65.70 ms |
| 2 | synthetic AI finish -> render | 80.00 ms | 185.00 ms | 313.00 ms | 313.00 ms |
| 4 | metadata HTTP | 42.76 ms | 79.10 ms | 120.26 ms | 120.26 ms |
| 4 | backend DB | 22.87 ms | 71.04 ms | 88.22 ms | 88.22 ms |
| 4 | fixed location | 4.09 ms | 31.67 ms | 36.23 ms | 36.23 ms |
| 4 | backend ingest | 38.45 ms | 73.60 ms | 105.86 ms | 105.86 ms |
| 4 | backend WS -> browser | 1.00 ms | 17.00 ms | 35.00 ms | 35.00 ms |
| 4 | WS receive -> render | 25.70 ms | 38.70 ms | 45.60 ms | 45.60 ms |
| 4 | synthetic AI finish -> render | 71.00 ms | 113.00 ms | 151.00 ms | 151.00 ms |

All 150 browser samples rendered through the direct WebSocket path. The benchmark creates the synthetic `ai_finished_at` immediately before starting HTTP, so `AI -> HTTP start` is intentionally 0 ms and does not claim to measure the Android queue improvement. The local end-to-end p50/p95 values are well below the provisional 500/1500 ms targets, but staging PostgreSQL, Render network distance, mobile radio behavior, and real Flutter timestamps still require the same 50-event device run before production conclusions.

## Measurement contract added by this branch

Correlation uses `event_id` and `trace_id`. Cross-process timestamps are UTC epoch milliseconds. Monotonic clocks are used only for durations inside one process.

- Flutter emits native-window, Flutter receipt, AI, queue, HTTP-start, and HTTP-response timestamps.
- Backend adds receive, DB-start/commit, WebSocket schedule, post-ingest enqueue, and response-start timestamps.
- `Server-Timing` exposes `db`, `fixed_location`, and total `ingest` durations.
- Dashboard adds WebSocket receipt, state-update, render-start, and render-finish timestamps. The latest 500 samples and p50/p95/p99/max aggregates are available as `window.__postInferenceLatencySamples` and `window.__postInferenceLatencyStats`.

## Local synthetic ingest benchmark

Run only against a local service. It deliberately refuses remote hosts because
its `ai_finished_at` marker is synthetic and cannot be used as staging evidence:

```powershell
python tools/benchmark_post_inference_latency.py `
  --base-url http://127.0.0.1:8000 `
  --upload-token <local-token> `
  --nodes 1,2,4 `
  --events 50
```

For true post-inference-to-render numbers, follow
`docs/performance/real_staging_latency_runbook.md`, run the Flutter node, and
keep the Dashboard open. Export the two `window.__postInferenceLatency*`
values after at least 50 real target AI completions per scenario.

## Rollback flags

- Backend tracing: `POST_INFERENCE_LATENCY_TRACING_ENABLED=false`
- Backend stale-while-refresh ingest cache: `FAST_EVENT_INGEST_ENABLED=false`
- Dashboard stale-event ordering guard: `DASHBOARD_EVENT_ORDER_GUARD_ENABLED=false`
- Flutter immediate metadata lane: `--dart-define=FAST_METADATA_UPLOAD_ENABLED=false`
- Flutter persistent HTTP transport: `--dart-define=PERSISTENT_METADATA_HTTP_CLIENT_ENABLED=false`
- Flutter tracing: `--dart-define=POST_INFERENCE_LATENCY_TRACING_ENABLED=false`
