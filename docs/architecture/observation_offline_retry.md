# Observation offline retry reliability

Status: implementation on `fix/offline-observation-retry`; staging validation
required before the offline-loss blocker can close.

## Scope and root cause

The Phase 4 Android field run created observation sequences 427 through 491
while the phone had no usable network. Every HTTP request failed and the App
kept no durable copy, so none of the 65 observations was replayed. Backend
received and tracking applied only the 145 requests that had succeeded.

This change is limited to Observation persistence/retry and replay admission.
It does not change Alert cooldown, `/events`, audio capture, inference cadence,
fusion, tracking algorithms, localization, Dashboard behavior, or production
database schema.

## Local persistence

Flutter uses a dedicated SQLite database, not the existing whole-list
SharedPreferences event queue. Each observation is inserted transactionally
before its first HTTP attempt. The table stores:

- `observation_id`, `device_id`, `process_session_id`, and `sequence`
- `observed_at` and `event_time_ms`
- exact `payload_json` and `payload_bytes`
- `created_at_ms`, `attempt_count`, `last_attempt_at_ms`, and
  `next_retry_at_ms`
- `status`, `last_error`, `trace_id`, and `schema_version`

No audio bytes, paths, or references are added. `audio_ref` remains `null`.
Indexes cover due-work selection and device/session sequence ordering.

## State machine

```text
PENDING -> IN_FLIGHT -> COMPLETED (row removed)
                    -> RETRY_WAIT -> IN_FLIGHT
                    -> FAILED_PERMANENT
PENDING/RETRY_WAIT/IN_FLIGHT -> EXPIRED (counted, row removed)
```

App startup atomically changes leftover `IN_FLIGHT` rows to `RETRY_WAIT` and
increments `observation_recovered_after_restart_total`. The original payload,
device, process session, sequence, and event time never change. A new App
process may create a new process session while draining records from the old
one.

Phone reboot does not require automatic App launch. The SQLite file survives;
draining resumes the next time the App starts. Automatic boot behavior remains
outside this fix.

## Retry and reconnect

The worker selects oldest due rows first and sends sequentially. Backoff is
1, 2, 4, 8, 15, 30, then capped at 60 seconds with plus/minus 20 percent
jitter. A transport/HTTP failure opens a global retry delay so every newly
created observation does not independently hammer an offline network.

Node WebSocket reconnect and App foreground resume actively make `RETRY_WAIT`
rows due and wake the worker. A permanent client error such as HTTP 400, 401,
403, 404, 413, or 422 marks only that record `FAILED_PERMANENT`; later rows can
continue. Retriable HTTP 408, 409, 425, and 429 remain bounded by backoff and
expiry.

Backend 2xx, including an idempotent duplicate response, completes the local
row. A crash after Backend acceptance but before local deletion therefore
causes a safe duplicate retry.

## Retention and overflow

Default local limits are:

| Limit | Default |
|---|---:|
| Maximum age | 6 hours |
| Maximum active/diagnostic rows | 10,000 |
| Maximum payload bytes | 25 MiB |
| Maximum rows drained per worker pass | 500 |

Expired rows are removed with an explicit counter. Before enforcing storage
bounds, expired rows are cleaned first; failed-permanent and then oldest rows
are removed before newer rows. Every bound-driven removal increments
`observation_overflow_total`. There is no silent drop.

## Backend replay age semantics

Backend computes age from the preserved measurement `event_time_ms`; it never
relabels arrival time as event time.

| Classification | Default age | Registry | Shadow tracking |
|---|---:|---:|---:|
| `live` | up to 5 s | retained | eligible |
| `late-but-recoverable` | over 5 s through 120 s | retained | eligible |
| `historical-only` | over 120 s through 6 h | retained | suppressed |
| `expired` | over 6 h | counted/retained by current bounded shadow registry | suppressed |

The response exposes `received_at`, `observed_at`, `event_time_ms`, `age_ms`,
`age_classification`, `tracking_eligible`, and `tracking_scheduled`.
Historical-only/expired requests cannot overwrite a newer live track because
they never enter the tracking executor.

The thresholds are staging-configurable:

- `OBSERVATION_LIVE_MAX_AGE_MS=5000`
- `OBSERVATION_LIVE_TRACKING_MAX_AGE_MS=120000`
- `OBSERVATION_HISTORICAL_MAX_AGE_MS=21600000`

## Idempotency

The existing `observation_id` uniqueness check remains the logical identity
boundary. A separate bounded in-memory tombstone set now outlives the shorter
shadow-record retention:

- `OBSERVATION_IDEMPOTENCY_TTL_SECONDS=21600`
- `OBSERVATION_IDEMPOTENCY_MAX_IDS=50000`

Sending the same ID one, two, or five times increments request/duplicate
telemetry but creates one unique observation and schedules tracking once.
Because Phase 4 still forbids a production schema change, Backend restart
clears these tombstones. Cross-Backend-restart idempotency remains a documented
risk and must be tested separately before production GO.

## Telemetry

Machine-readable App logs include:

- `observation_queue_depth`, `observation_queue_bytes`
- `observation_queued_total`
- `observation_upload_attempt_total`, `observation_upload_success_total`,
  `observation_upload_failure_total`
- `observation_retry_total`, `observation_retry_success_total`,
  `observation_retry_failure_total`
- `observation_expired_total`, `observation_overflow_total`
- `observation_recovered_after_restart_total`
- `observation_failed_permanent_total`
- `oldest_pending_age_ms`, `retry_delay_ms`

Android field samples use bounded
`[OBSERVATION_SHADOW_FIELD_JSON_B64]` logcat chunks. The analyzer validates,
reassembles, Base64-decodes, and parses a complete JSON record; incomplete or
truncated chunk sets are ignored instead of being counted as evidence.

Backend metrics include replay classification counts, tracking suppression
counts, dedup expiry/eviction, and current idempotency tombstone size.

## Alert-path isolation

The AI result handler calls `unawaited(enqueueTargetObservationShadow(...))`.
Alert admission/cooldown evaluation does not await SQLite or HTTP. Inside the
independent future, SQLite commit is awaited before the retry worker is woken,
which preserves durable-before-send without placing disk/network latency on
the Alert path. Shadow OFF/ON real-device latency comparison remains an
acceptance gate.

## Rollback

No migration or production data rollback exists. To stop the new path:

1. Build Flutter with `OBSERVATION_SHADOW_ENABLED=false`.
2. Set staging `OBSERVATION_TRACKING_ENABLED=false`, then
   `OBSERVATION_SHADOW_ENABLED=false`.
3. Leave the local SQLite file for forensic inspection or uninstall/clear the
   staging App explicitly. Do not silently delete pending rows during runtime.
4. `/events`, Alert cooldown, Dashboard, and audio behavior remain unchanged.

Rollback reopens the offline-loss limitation; it is an emergency isolation
step, not a reliability fix.

## Acceptance

Automated tests cover durable-before-send, retained HTTP failure, reconnect
drain, restart recovery, duplicate enqueue, oldest-first ordering, poison-row
advance, expiry, bounds, overflow metrics, preserved process session, and
non-blocking Alert call placement. Backend tests cover 1/2/5 duplicate sends,
late tracking eligibility, historical-only/expired suppression, old replay
safety, and tombstone retention.

Real Android staging must still pass normal Wi-Fi; 5, 15, 30, and 60 second
offline windows; and offline plus App restart. The original 65-loss case must
show all retained observations delivered as unique Backend observations, with
tracking or explicit historical/expired classification. Closing this blocker
does not imply V2.4 GO.
