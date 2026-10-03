# Event to first position critical-path audit

Baseline: 433eff2, 2026-10-04. Read from actual functions in main.py, event_fusion.py, region_localization.py, device_location_service.py and services/tracking/*.py. No production change or enabled localization.

## Actual call graph

`POST /events -> create_event -> asyncio.to_thread(process_event_initial_submission) -> save_event_with_inserted -> fixed-location ingest cache -> event_trigger broadcast schedule -> schedule_event_post_ingest -> executor queue -> run_event_post_ingest_worker -> process_event_post_ingest -> process_event_fusion_for_event -> get_event_by_event_id + location enrichment -> process_event -> advisory label lock -> observation_group_for_event -> find_candidate_group (or create) -> insert_observation -> update_group_rollup -> merge_nearby_groups -> close_stale_groups -> transaction commit -> region tracking -> active alert tracking fallback -> optional localization [disabled] -> with_realtime_alert_timing -> event-loop scheduling -> broadcast_event_post_ingest_result -> safe_dashboard_broadcast(event_group) -> dashboard_manager.broadcast -> socket.send_json -> Dashboard handleWebSocketMessage -> state.groups.set -> renderOverview -> renderTracksView -> renderMap -> renderCommandBar`.

The earlier event_trigger can already render an event/node location. The requested first-position metric is specifically the first **valid event_group position** broadcast for that event, not the earlier raw node marker. The browser synchronous map update return is not Google Maps paint, screen presentation, receipt acknowledgement, or network latency.

## Operations and classifications

| Function / operation | SQL statements / calls | Classification and reason |
| --- | --- | --- |
| save_event_with_inserted | schema cache checks as applicable, INSERT ON CONFLICT RETURNING, duplicate fallback SELECT, commit | REQUIRED_NOW: persistence/idempotency |
| list_device_fixed_locations_for_ingest / effective location enrichment | cache hit or SELECT device_locations | REQUIRED_NOW: fixed overrides raw GPS; refresh CAN_DEFER and already background |
| event_trigger | event/node serialization and scheduled send | REQUIRED_NOW for existing alert transport; separate from group SLA |
| executor enqueue / start | no SQL | REQUIRED_NOW; bounded existing worker count |
| get_event_by_event_id | SELECT event and location enrichment/cache work | REQUIRED_NOW; passing ingestion snapshot would need concurrency contract |
| lock_fusion_label | SELECT pg_advisory_xact_lock(hashtext(label)) | REQUIRED_NOW; transaction-scoped lock preserved |
| observation_group_for_event | SELECT observation JOIN group, then group_payload | lookup REQUIRED_NOW; unused existing payload fields REMOVE_OR_VERIFY |
| find_candidate_group | SELECT candidates then Python interval score | REQUIRED_NOW; windows unchanged |
| create_group / close_stale_groups | INSERT; UPDATE when needed | REQUIRED_NOW for current consistency/order |
| insert_observation | INSERT conflict handling; snapshot updates on resend | REQUIRED_NOW: observation uniqueness |
| update_group_rollup | aggregate MIN/MAX/COUNT DISTINCT; UPDATE bounds/node count | REQUIRED_NOW; SQL combination MERGEABLE after stronger proof |
| group_region_observations | SELECT ordered observations then SELECT fixed locations | REQUIRED_NOW; JOIN MERGEABLE but deferred until location/order equivalence proven |
| estimate_region | deduplication/geometry computation, no SQL | REQUIRED_NOW; math unchanged |
| update_group_region | UPDATE region fields | REQUIRED_NOW; UPDATE RETURNING MERGEABLE with next group reload |
| final group reload | SELECT same group | MERGEABLE on PostgreSQL via returned row; SQLite fallback retained |
| group_payload | SELECT devices plus SELECT per-device minimum timestamps | MERGEABLE via existing group_observation_summaries, including null timestamps |
| merge_nearby_groups | per loop SELECT target, SELECT source; observation move/dedup/update/source close; rollup after merge | REQUIRED_NOW: returning pre-merge group could display stale membership/geometry |
| final close_stale_groups | UPDATE older same-label groups | REQUIRED_NOW under current transaction semantics |
| Fusion commit | same existing transaction | REQUIRED_NOW before broadcast; do not broadcast uncommitted data |
| process_tracking_for_event_group_region | measurement built from group; node/region gating | CAN_DEFER for group marker, retained pending ordering proof |
| process_tracking_for_active_alert_region | SELECT trigger plus recent 100 events and location enrichment; region estimate | CAN_DEFER for group marker; fallback tracking results still required |
| process_tracking_measurement | tracking_update_lock -> close_stale_tracks -> choose_track -> update_track_from_measurement -> save_track_point -> enrich | CAN_DEFER for first group marker, REQUIRED_NOW before track_update |
| find_active_track_for_group | SELECT point JOIN active track when group_id exists | REQUIRED_NOW for tracking association priority |
| active_tracks_for_label | SELECT 25 ordered tracks only after group miss | REQUIRED_NOW for fallback; do not combine casually: priority/tie ordering/limit differ |
| predict_state / innovation gate / alpha-beta / speed / heading / outlier checks | no SQL | REQUIRED_NOW for tracking; untouched |
| save_track_point | INSERT or UPDATE track, INSERT point, SELECT track | writes REQUIRED_NOW; final reload MERGEABLE but retained: triggers and persistence equivalence need PostgreSQL fixture |
| enrich_track_with_points | SELECT recent points | CAN_DEFER for group marker; required by existing track_update/REST contract |
| close_stale_tracks | PG UPDATE RETURNING or SQLite SELECT+UPDATE, then per closed track SELECT points | update REQUIRED_NOW for tracking association; point enrichment REMOVE_OR_VERIFY on ignored-result caller only |
| diagnostics / SQL counts | in-memory counters, no payload SQL logging | DEBUG_ONLY; staging scoped |
| device status worker | DB upsert, cache enrichment, event-loop broadcast | CAN_DEFER and already independent executor |
| history REST / periodic runtime | group/detail/track queries, 30-second snapshot | CAN_DEFER; preserve public schema |

Counts vary by duplicate/new/merge case, cache state, dialect and rejected tracking. Dynamic per-event counts are measured, not inferred from global totals. Cursor execute calls count attempted statements; commit/rollback/autonomous server trigger SQL and protocol messages are not statement counts. No literal SQL or parameters are retained.

## Enrichment equivalence

`group_devices` filters non-null device IDs and sorts lexicographically. `group_device_relative_times` groups by device with MIN(timestamp), drops unparseable/null times and sorts by parsed datetime then device. `group_observation_summaries` already returns both structures with identical filtering and ordering for valid ingestion timestamps, including devices with null timestamps. Empty device IDs differ (summary skips them); restrict optimization to rollup path only after tests covering this edge or preserve legacy fallback. REST bulk list already uses summary overrides. Explicit caller overrides must remain authoritative.

Dashboard consumes region center, region GeoJSON, reporting devices/count, timing/status, and devices/relative times in other views; keep full event_group payload backward compatible. A minimal realtime payload is not applied because state.groups.set replaces full group and could erase details between snapshots.

## Race conditions / retained work

Broadcast before merge could expose two ACTIVE groups or geometry computed before observation reassignment. A later correction needs tombstones/merged_group_ids and sequence ordering across concurrent same-label events, not merely another update. Keep merge, advisory lock, commit and cleanup order. Tracking may process a reorder tail on another thread/timer; do not assign that tail's SQL to the current triggering event. Missing followup milestones must mean not emitted/buffered, not zero latency.

close_stale_tracks callers: process_tracking_measurement ignores its returned list; background tracking cleanup and REST tracks handling consume/enrich/broadcast it. Only the ignored caller is eligible for enrich=False, retaining default enrichment everywhere else.

## Instrumentation and benchmark plan

Correlated monotonic offsets T0–T14, actual successful broadcast completion, valid-position eligibility, per-event attempted SQL counts (total/fusion/tracking), and stage aggregates. Explicit trace handoff from request to worker and broadcast; scope restoration avoids attributing concurrent requests. Diagnostics default off outside staging. Browser performance.now captures synchronous event_group map update duration with 256-sample bound, no API per message. It does not measure paint.

Before benchmark follows instrumentation-only checkpoint; after uses identical seven deterministic local synthetic scenarios, 50 iterations each. Local SQLite lacks network/advisory lock contention and does not establish Render or Android SLA. PostgreSQL-only improvements must be validated separately with isolated disposable schema before live use. Do not sum stage percentiles. Required field decision remains INSUFFICIENT_SAMPLE unless 30–50 real Android events exist.
