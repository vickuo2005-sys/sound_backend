# Event-driven V1: current ownership and migration boundary

Audited from branch HEAD afe4501 (application equivalent to deployed 9ba7f8).
Baseline: 339 Python tests passed, 1 local-PostgreSQL-dependent skip, 3 existing warnings.
The clean verification checkout preserves the original workspace's untracked reports.

## Actual call graph

Android POST /events -> main.create_event -> _create_event (token validation,
classification/timing/audio sanitization) -> asyncio.to_thread(process_event_initial_submission)
-> save_event_with_inserted -> upsert_event_postgres_with_inserted or SQLite equivalent.
The returned inserted boolean gates device-status work, event_trigger, and
schedule_event_post_ingest. Existing/audio-metadata submissions instead send event_audio_update.

schedule_event_post_ingest -> existing post_ingest_executor.submit ->
run_event_post_ingest_worker -> process_event_post_ingest ->
process_event_fusion_for_event -> services.event_fusion.process_event
(imported as process_fusion_event) -> label advisory lock, observation lookup,
candidate/create group, observation insertion, rollup, merge, cleanup.

Then process_tracking_for_event_group_region; if it returns no track,
process_tracking_for_active_alert_region. Both adapt measurements to
process_tracking_measurement -> choose_track_for_measurement ->
services.tracking.tracking_service.update_track_from_measurement -> existing
track/point persistence. Tracking reorder buffering may defer emission.
Localization is a separate optional branch and remains disabled.

Worker result -> loop.call_soon_threadsafe -> broadcast_event_post_ingest_result
-> _broadcast_event_post_ingest_result -> safe_dashboard_broadcast ->
DashboardConnectionManager.broadcast -> WebSocket send_json ->
templates/dashboard_v2_4.html connectWebSocket/handleWebSocketMessage/renderMap.
Initial event_trigger and independent device-status broadcasts are separate paths.

## Ownership and synchronous return assumptions

main.py owns request authentication, initial event insert, pool/transaction lifecycle,
executor scheduling, tracking DB operations, caches, failure logging and realtime scheduling.
event_fusion.py owns grouping SQL and region rollup; tracking_service.py owns numerical
association/update rules. Neither algorithm is moved or duplicated. latency_diagnostics.py
owns bounded in-process rolling samples and ContextVar trace propagation.

process_event_initial_submission must return db_id, inserted/existing status, saved_event,
device_row and cache state before the API can decide subsequent side effects and its response.
process_event_post_ingest synchronously consumes Fusion's group to select region tracking,
uses a missing region_track to decide fallback tracking, and returns the complete bundle.
The worker needs that bundle before scheduling realtime. Realtime requires canonical group,
track and localization payloads and suppresses deferred reorder placeholders. Existing
domain helpers, REST group/detail endpoints and location-region recomputation also consume
synchronous group/track returns; they are not rerouted through the new bus.

## Ordering, retry and transaction boundaries

event_id is the original Android/application ID, not a delivery attempt ID; audio metadata
may arrive under the same ID later. Persistence uses events_event_id_key and UPSERT with
inserted detection; this is not a transactional queue/outbox. Initial event transaction
commits before background work. There is a crash gap between commit and executor submit.
The executor is process-local, has no durable replay, and parallel workers do not guarantee
global event-time order. PostgreSQL Fusion is serialized by pg_advisory_xact_lock(hashtext(label))
inside its existing transaction; group/observation/rollup/merge share that transaction.
The event read uses the same leased connection, but helpers retain their current commit rules.
Tracking has an in-process tracking_update_lock, optional reorder buffering, timestamp
duplicate/late rejection and multiple existing helper transactions; it is not atomic with Fusion.
WebSocket delivery is after DB work and is not atomic with either commit.

Fusion observation uniqueness is a partial unique index on event_id for fusion observations.
target_track_points has a track/time index, not a sufficient durable replay unique key.
Timestamp guards help but do not prove distributed retry safety. Dashboard event-order guards
and state replacement limit duplicates but WebSocket effects are not durably acknowledged.
Exceptions in Fusion/tracking are logged and may return partial bundles; the legacy path has
no generic automatic retry. No transaction, lock, API, payload or worker setting is changed.

## V1 boundary

Both feature flags default false. EVENT_DRIVEN_PIPELINE_ENABLED is reserved: it never replaces
the legacy path in V1. Shadow only accepts local/staging environments and observes already
computed canonical results. It must not invoke mutation-capable domain adapters, even for
"comparison". Explicit adapters may invoke injected existing functions only in isolated tests.
Queue-full, context eviction, invalid envelopes and observer errors are counted, never cause
a failed Android request and never change legacy outputs. Shadow metrics are prefixed event_bus
and must not be mixed with first_position_backend SLA. No Redis request-path activation exists.
