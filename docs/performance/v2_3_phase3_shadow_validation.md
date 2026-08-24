# Sound Detector V2.3 Phase 3 shadow validation

Date: 2026-08-25

## Implementation boundary

Observation shadow path is independent from the existing alert path:

```text
valid target AI result
  ├─ observation.v1 -> /observations/shadow -> bounded memory -> shadow fusion/tracking
  └─ EventAdmissionController (unchanged 10 s)
       ├─ admitted -> existing AudioEvent /events / Dashboard alert/audio pipeline
       └─ rejected -> no alert, observation already preserved
```

All new flags default off. No production DB schema, migration, Dashboard handler,
audio upload, `/events` transaction, smoothing, or message broker is involved.

## Deterministic simulator

Configuration: 1.5 s hop, 10 s alert cooldown, no smoothing. Point interval and
gap use measurement event time, never arrival time.

| Scenario | Control points | Shadow points | Shadow late | duplicate | outlier | Shadow max gap | Shadow tracks |
|---|---:|---:|---:|---:|---:|---:|---:|
| sustained drone 30 s | 3 | 20 | 0 | 0 | 0 | 1.5 s | 1 |
| sustained drone 60 s | 6 | 40 | 0 | 0 | 0 | 1.5 s | 1 |
| A01→A02→A03 sequential motion | 3 | 20 | 0 | 0 | 0 | 1.5 s | 1 |
| mild network jitter | 3 | 20 | 0 | 0 | 0 | 1.5 s | 1 |
| heavy network jitter | 3 | 20 | 0 | 0 | 0 | 1.5 s | 1 |
| duplicate upload | 3 | 20 | 0 | 1 | 0 | 1.5 s | 1 |
| delayed observation | 3 | 20 | 0 | 0 | 0 | 1.5 s | 1 |
| missing observation | 3 | 19 | 0 | 0 | 0 | 3.0 s | 1 |
| two simultaneous independent regions | 6 | 40 | 0 | 0 | 0 | 1.5 s | 2 |

Heavy jitter produced 13 gap and 13 out-of-order diagnostics, but the
sequence-aware gate recovered all 20 points. Delayed E2/E3/E1 produced one gap
and one out-of-order diagnostic, with zero tracking late discard. Duplicate
upload was idempotent: 21 attempts, 20 unique observations, 20 points.

## Sustained target density

| Duration | Raw observations | Alert admitted | Cooldown rejected | Control points | Shadow points | Density gain | Max-gap reduction |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 30 s | 20 | 3 | 17 | 3 | 20 | 6.67× | 10.5 s → 1.5 s (−85.71%) |
| 60 s | 40 | 6 | 34 | 6 | 40 | 6.67× | 10.5 s → 1.5 s (−85.71%) |

The missing-observation scenario still retained 19/20 points and reduced the
maximum gap from 10.5 s to 3.0 s. This exposes the missing input rather than
interpolating it.

## Ordering architecture experiment

Arrival timing for E2→E3→E1: 0/100/200 ms. Memory is maximum pending items per
independent key, excluding fixed bookkeeping.

| Input spacing | Option | Recovered | Late | Added p50 | Added max | Max pending |
|---|---|---:|---:|---:|---:|---:|
| 1.0 s | sequence-aware serialized | 3/3 | 0 | 100 ms | 200 ms | 2 |
| 1.0 s | event-time 1500 ms | 3/3 | 0 | 1400 ms | 1500 ms | 2 |
| 1.0 s | event-time 2000 ms | 3/3 | 0 | 1900 ms | 2000 ms | 2 |
| exact 1.5 s hop | sequence-aware serialized | 3/3 | 0 | 100 ms | 200 ms | 2 |
| exact 1.5 s hop | event-time 1500 ms | 2/3 | 1 | 750 ms | 1400 ms | 1 |
| exact 1.5 s hop | event-time 2000 ms | 3/3 | 0 | 1900 ms | 2000 ms | 2 |

The 1500 ms watermark still fails at an exact 1500 ms hop because E2 is
released when `event_time == watermark` before E1 arrives. A 2000 ms buffer
recovers the point but adds close to two seconds of tracking latency. Neither
buffer is on the Dashboard alert path.

## Recommendation

Prefer per-key serialization with bounded late handling:

1. Per device/process sequence gate handles duplicates, gaps, and worker/network
   reordering without replacing event time.
2. Per region/track serialized mailbox applies emitted measurements in event-time
   order; independent regions never share a global queue.
3. A bounded missing-sequence timer advances past genuine gaps and records them.
4. Keep a small event-time late policy after serialization for cross-device
   fusion revisions; do not use a large global watermark.

This has higher bookkeeping complexity than a heap-only buffer but recovered
both tested orders with far lower added latency and the same two-item peak
pending memory in the deterministic experiment.

## Rollback

- Flutter: `OBSERVATION_SHADOW_ENABLED=false`
- Backend ingest: `OBSERVATION_SHADOW_ENABLED=false`
- Backend shadow tracker: `OBSERVATION_TRACKING_ENABLED=false`
- Existing experimental tracker remains off:
  `TRACKING_REORDER_BUFFER_ENABLED=false`

With flags off the App makes no observation request, the Backend route returns
404, no shadow executor work is submitted, and the V2.2 `/events`/Dashboard/audio
path is unchanged.

## Filtering/localization readiness

Not ready for Kalman/particle/filter tuning in production. The shadow path is
ready for real Android staging validation, but field evidence is still required
for sequence gaps, clock quality, node-position semantics, multi-node fusion
revision ordering, bandwidth, and memory. Filtering research should begin only
after those inputs are verified; otherwise it would risk hiding starvation or
ordering faults.
