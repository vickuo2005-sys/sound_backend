# Sound Detector V2.3 Phase 4 field shadow validation

Date: 2026-08-25

## Decision

**NO-GO for V2.4 Observation Productionization.**

The implementation and local deterministic validation are ready for a real
field run, but field evidence is unavailable. The Android SDK is healthy, yet
`adb devices -l` returned no physical device. The ignored
`config/staging.local.json` is not trustworthy: it reports
`APP_ENV=development`, points at the production host, has no observation flag,
and was rejected by the new validator. No production or staging traffic was
sent during this work.

This is an evidence NO-GO, not an implementation-test failure.

## Implemented field path

```text
valid target AI result
  |-- fire-and-forget observation.v1 (exact payload byte telemetry)
  |     -> bounded/TTL registry and idempotency
  |     -> (device_id, process_session_id) sequence gate
  |     -> per-region serialized mailbox
  |     -> event-time fusion revision or explicit late drop
  |     -> shadow track only
  |
  `-- unchanged EventAdmissionController (10 seconds)
        -> unchanged /events, audio, Dashboard alert
```

No component uses smoothing, interpolation, Kalman, particle filtering,
production DB writes, audio upload, or a global tracking queue. All observation
flags remain false by default.

## Local deterministic ordering benchmark

Evidence classification: local deterministic, not Android/staging field data.
Completion time advances by 100 ms per arrival. Option B uses a 500 ms bounded
missing-sequence timeout in this benchmark; production configuration remains
explicit and feature-flagged. Memory values are deterministic state estimates,
not process RSS.

| Case | Option | Recovered | Late | Duplicate | Added p50 | p95 | p99 | Max | Max pending |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| E2,E3,E1 at 1 s | A parallel | 2/3 | 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| E2,E3,E1 at 1 s | B sequence/mailbox | 3/3 | 0 | 0 | 100 | 200 | 200 | 200 | 2 |
| E2,E3,E1 at 1 s | C reorder 2000 | 3/3 | 0 | 0 | 2100 | 2200 | 2200 | 2200 | 2 |
| Exact 1.5 s hop | A parallel | 2/3 | 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| Exact 1.5 s hop | B sequence/mailbox | 3/3 | 0 | 0 | 100 | 200 | 200 | 200 | 2 |
| Exact 1.5 s hop | C reorder 2000 | 3/3 | 0 | 0 | 2100 | 2200 | 2200 | 2200 | 2 |
| Mild jitter | B sequence/mailbox | 4/4 | 0 | 0 | 0 | 100 | 100 | 100 | 1 |
| Mild jitter | C reorder 2000 | 4/4 | 0 | 0 | 1050 | 2200 | 2200 | 2200 | 2 |
| Heavy jitter | B sequence/mailbox | 4/4 | 0 | 0 | 150 | 300 | 300 | 300 | 3 |
| Heavy jitter | C reorder 2000 | 3/4 | 1 | 0 | 2200 | 2300 | 2300 | 2300 | 2 |
| Missing sequence | B sequence/mailbox | 2/2 | 0 | 0 | 250 | 500 | 500 | 500 | 1 |
| Missing sequence | C reorder 2000 | 2/2 | 0 | 0 | 1050 | 2000 | 2000 | 2000 | 1 |
| Duplicate | B sequence/mailbox | 2/2 | 0 | 1 | 0 | 0 | 0 | 0 | 0 |
| Two tracks | B sequence/mailbox | 4/4 | 0 | 0 | 0 | 100 | 100 | 100 | 1 |
| Two tracks | C reorder 2000 | 4/4 | 0 | 0 | 2075 | 2150 | 2150 | 2150 | 4 |

Option B recovered at least as many measurements as the 2000 ms control and
added far less latency. Independent-track concurrency is covered separately;
there is no global queue.

## Cross-device fusion and restart semantics

Local tests used A03(1.2), A01(1.0), A02(1.1) reverse arrival in one hop bucket.
The result was one fusion point, three applied measurements, two explicit
revisions/late attaches, and zero silent drops. A late attach beyond the bounded
window produced `fusion_late_drop_count=1` and `late_discard_count=1`.

- App restart creates a new `process_session_id`; sequence may restart at 1.
- Same device/sequence in another process session is not a duplicate.
- Same `observation_id` retry is idempotent while the bounded TTL registry
  retains the ID.
- Backend restart clears all observation registry, dedup, sequence, fusion,
  mailbox, and shadow-track state. Phase 4 shadow reliability is explicitly
  best effort; unprocessed/pending observations and tracks can be lost.

## Bounded state and reconciliation

- Registry: TTL, max observations, max streams, cleanup/expired/max-seen metrics.
- Sequence gate: max keys, key TTL, max pending per key, explicit overflow,
  timeout advance, duplicate, gap, and out-of-order counters.
- Mailbox: per-key depth bound, max keys, TTL cleanup, wait/processing
  p50/p95/p99/max, capacity drops, and independent workers.
- Tracks/fusion: max tracks, max points per track, TTL cleanup, bounded buckets.
- Reconciliation exposes Backend received, unique, sequence gate, fusion,
  tracking measurement, and track point counts. Raw AI/App stages are joined by
  the field analyzer rather than fabricated on the server.

Unit tests demonstrate the configured bounds and reset behavior. Continuous
30-minute/one-hour RSS and plateau evidence remains unavailable without field
traffic.

## Field deliverable status

| Deliverable | Status |
|---|---|
| True staging config | Blocked: local file rejected; real staging host/tokens unavailable |
| Android/scenarios | Blocked: no physical device in adb |
| Delivery/loss/sequence rates | Not measured |
| Control vs Shadow density/gaps | Not measured in field; Phase 3 simulation remains separate |
| Clock offset/drift/jumps | Instrumented, not measured in field |
| Payload/request bandwidth | Exact/estimated telemetry instrumented, no field samples |
| 30-minute/1-hour memory | Bounded implementation tested, no field duration evidence |
| Shadow ON/OFF Alert latency | Comparison harness ready, no samples |
| Render to Supabase DB latency | Existing probe ready, not enabled or measured |
| Backend tests | 110 passed; two pre-existing Pydantic deprecation warnings |
| Flutter tests/analyze | 46 passed; analyze clean |

## Required evidence before GO

Run all ten scenarios in `phase4_field_runbook.md`, including 1/2/4-node
sustained runs, restart/network transitions, 30-minute or longer memory capture,
Shadow OFF/ON Alert latency, and bounded Render-to-Supabase probes. A GO requires
stable delivery, explainable gaps, controlled ordering, bounded memory,
acceptable measured bandwidth, no meaningful Alert regression, and acceptable
clock quality.

Do not start localization filtering while this decision remains NO-GO.
