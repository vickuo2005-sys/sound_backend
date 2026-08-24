# V2.2 latency Phase 2 validation report

Date: 2026-08-25 (Asia/Taipei)

## 1–3. Real staging latency, largest stage, localhost comparison

Real Android + Render staging + Supabase percentiles are **not yet measured**.
The validation host currently has no ADB Android device (`adb devices -l` is
empty). The existing Flutter `config/staging.local.json` is also not a safe
staging config: it declares `APP_ENV=development` and points at the production
host. The shell has no separate staging DB/upload environment variables.

Consequently there are no honest 1/2/4-node × 50 staging p50/p95/p99/max values,
no staging largest-stage conclusion, and no localhost-vs-staging delta. Localhost
or synthetic AI timestamps were not substituted.

The previous localhost browser run's largest measured p95 component was the
Backend DB UPSERT/commit (1/2/4 nodes: 80.56/113.97/71.04 ms), but that is not a
claim about Render ↔ Supabase.

Staging readiness added in this phase:

- Flutter emits the four required same-process monotonic fields and rejects
  cross-restart monotonic traces.
- Backend emits `backend_received`, `db_start`, `db_complete`, `ws_schedule`,
  `response_start`, plus `db`, `server_non_db`, and `ingest` Server-Timing.
- Browser emits `ws_received`, `render_complete`, and local
  `performance.now()` durations.
- Authenticated, default-off `/diagnostics/db-latency` separates pool acquisition
  from Render → Supabase `SELECT 1` query/fetch RTT.
- `tools/analyze_staging_latency.py` reports count/p50/p95/p99/max without
  smoothing and requires real App samples.

## 4–6. Executor out-of-order testcase and reorder effect

Reproducible input:

```text
E1 event_time = 1.0 s
E2 event_time = 2.0 s
E3 event_time = 3.0 s
completion = E2, E3, E1
```

The real SQLite-backed `process_tracking_measurement` testcase uses the same
group/track. Result: E2 and E3 are stored; E1 returns the existing track without
inserting a point. Track point count = 2; newly counted late discard = 1.

The feature-flagged prototype is post-ingest-only:

- `TRACKING_REORDER_BUFFER_ENABLED=false` by default
- `TRACKING_REORDER_WINDOW_MS=500`
- per-group/per-region priority queue ordered by measurement event time
- watermark = `latest_seen_event_time - reorder_window`
- bounded timer flushes the tail
- first `/events` ACK and Dashboard `event_trigger` never enter this buffer

Experiment result (`track points / discarded`):

| Scenario | Disabled | 300 ms | 500 ms |
|---|---:|---:|---:|
| in-order (1.0, 1.2, 1.4) | 3 / 0 | 3 / 0 | 3 / 0 |
| mild OOO (1.2, 1.0, 1.4) | 2 / 1 | 3 / 0 | 3 / 0 |
| heavy OOO (1.4, 1.2, 1.0) | 1 / 2 | 3 / 0 | 3 / 0 |
| late E2, E3, E1 (2.0, 3.0, 1.0) | 2 / 1 | 2 / 1 | 2 / 1 |
| duplicate E1, E1, E2 | 2 / 1 | 2 / 1 duplicate | 2 / 1 duplicate |
| missing E1, E3 | 2 / 0 | 2 / 0 | 2 / 0 |

For the exact requested E2/E3/E1 case, both 300 and 500 ms are too short: E2
is already before the watermark when E3 arrives, so the later E1 is behind an
emitted watermark. The buffer moves the discard from tracker to buffer but does
not restore the point. A 1.5-second production hop has the same structural issue
unless the event-time window exceeds the adjacent observation interval or a
sequence-aware per-key executor is used.

## 7–8. Cooldown starvation and separation design

Target cooldown currently causes starvation. When admission rejects a target,
Flutter deletes the transient audio and returns before creating `event_id`,
`AudioEvent`, or starting the cloud pipeline. The observation never reaches
Backend/fusion/tracking.

At a 1.5-second hop and 10-second alert cooldown, a continuous target produces
about 6–7 valid observations per cooldown interval, while usually only one can
reach Backend. That is a theoretical loss of about 85% before network/Backend;
it is not a measured field rate.

The four-layer schema, ID relationships, DB impact, backward compatibility,
bandwidth estimate, flags, rollout, and rollback are specified in
`docs/architecture/observation_alert_separation.md`. No migration or production
semantic change was made.

## 9. Largest historical-track risk

Observation starvation from the 10-second App cooldown is the largest expected
historical-track risk because it is deterministic and affects every sustained
target. Executor out-of-order loss is real but conditional on worker completion
order. Current production telemetry is insufficient to quantify their field
rates, so this ranking is based on code-path exposure, not smoothed data.

## 10. Recommended next phase

1. Supply a true staging config and attach Android devices; run 1/2/4 × 50 on
   the same Wi-Fi, then optional mobile network. Disable the DB probe afterward.
2. Keep broker work out of scope. Use the resulting Server-Timing and DB probe
   percentiles to determine whether Render ↔ Supabase dominates.
3. Implement observation upload/shadow persistence behind the separation flags,
   while leaving the 10-second alert path unchanged.
4. Keep the 300/500 ms reorder flag off for production because it fails the
   exact 1-second-spaced testcase. Measure real completion skew, then compare a
   sequence-aware per-key executor with event-time windows of at least one hop
   (for example 1.5–2.0 seconds). The first Dashboard alert remains unbuffered.
