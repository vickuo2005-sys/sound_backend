# Staging Latency Diagnostics (V1)

This stage is instrumentation only. It does not change the production
Timestamp-TDOA solver, fusion/tracking decisions, or map coordinates.

## What is measured

The FastAPI process keeps the **most recent 256 samples per stage**, in memory:

| Key | Meaning |
| --- | --- |
| `event_db_write` | Time to save the initial event; excludes waiting to enter the Python thread pool. |
| `event_initial_submission` | Request receive to initial submission complete, including any `asyncio.to_thread` wait. |
| `post_ingest_queue_wait` | Time from submitting a background event job to its worker starting. |
| `device_status_queue_wait` | Same for device-status background jobs (currently the same executor). |
| `post_ingest_worker` / `device_status_worker` | Total worker execution time, including synchronous database/network calls. |
| `event_fusion` | Full event-fusion call; includes DB and PostgreSQL advisory-lock waits. |
| `region_tracking` / `active_alert_tracking` | Corresponding tracking calls when executed. |
| `localization_group_load` | Reload of the fusion group and observations. |
| `localization_compute` | Full localization call; with GCC-PHAT enabled this can include audio retrieval and correlation. |
| `tdoa_solver` | SciPy least-squares multi-start solve only, when eligible geometry reaches the solver. |
| `localization_db_save` | Persisted localization result. |
| `localization_tracking` | Track update performed after localization. |
| `post_ingest_pipeline` / `localization_pipeline` | End-to-end durations inside each named worker stage. |
| `websocket_broadcast` | Server-side broadcast call to all subscribed dashboards, including slow-client waits. |

`/runtime-status` supplies `latency_diagnostics`: per-stage P50/P95/P99,
mean/max/last/count, pending and peak queue counts. It is an **in-process**
rolling window: a restart/deploy resets the samples, and a multi-worker Render
deployment reports only the worker serving the request. The Dashboard's System
view refreshes server diagnostics with its existing 30-second snapshot and
shows a local browser WebSocket **message handler duration**, not the actual
paint or cross-device one-way network latency.

## Run a field check

1. Deploy to **staging**, confirm `/runtime-status` reports the expected
   `build.render_git_commit` and a `latency_diagnostics` object.
2. Wait for fresh samples; trigger at least 30–50 real multi-node episodes under
   representative network conditions, rather than interpreting P99 with only
   a handful of observations.
3. During the test, review both `post_ingest_queue_wait` and
   `device_status_queue_wait` as well as their pending counts. Their
   job types currently share `POST_INGEST_WORKERS` (default 2).
4. Compare `event_fusion` against `tdoa_solver` and
   `localization_db_save`. If the solver shows no samples, check
   `LOCALIZATION_ENABLED`, node eligibility, and the localization result.
5. Compare `websocket_broadcast` and browser handler P95. A slow WebSocket
   broadcast does not prove the client render is slow.
6. Record Render CPU/memory and PostgreSQL connection saturation from their
   service consoles **at the same timestamps**.

Do not add these stage P95 values together to estimate an episode P95: they
are marginal summaries from potentially different event populations. For
accurate end-to-end latency, correlate event/episode identifiers and monotonic
span durations in a later tracing iteration.

## Constraints

- The diagnostics service writes **nothing** to PostgreSQL/GCS and does not
  store personal identifiers or raw audio in the metric samples.
- The existing `POST_INFERENCE_LATENCY_TRACING_ENABLED` flag controls the
  detailed event payload trace; it is not required to collect aggregate
  `Latency Diagnostics` samples.
- No worker, DB, CPU, or retry setting was changed in this first phase.
