# Staging Write-Freeze Runbook

This runbook defines the reversible maintenance gate used before a staging-only database cutover. It never applies to production.

## Purpose and guard

The application reads `APP_ENV` and `STAGING_WRITE_FREEZE` at startup. The freeze is active only when both conditions are true:

```text
APP_ENV=staging
STAGING_WRITE_FREEZE=true
```

Any other `APP_ENV`, including an empty value, keeps the freeze inactive even if the flag is accidentally set. The default is inactive (`STAGING_WRITE_FREEZE=false`). Unfreeze by setting the flag to `false` and restarting/redeploying the staging service using the normal configuration process.

## Behavior while active

Classified mutating HTTP requests receive HTTP 503 with the stable body:

```json
{"detail":"staging_write_freeze_active"}
```

A `Retry-After: 60` header is included. Read-only requests continue to run. `GET /tracks` remains available and skips its normal stale-track cleanup write while frozen. Node WebSocket heartbeats remain available; command acknowledgements/results are rejected with a `write_freeze_active` protocol message. New post-ingest and device-status background jobs are not scheduled. Jobs already running are allowed to finish.

The `/runtime-status` response includes:

- `staging_write_freeze.configured`
- `staging_write_freeze.active`
- `staging_write_freeze.environment`
- `staging_write_freeze.active_write_requests`
- `staging_write_freeze.pending_post_ingest_jobs`
- `staging_write_freeze.pending_device_status_jobs`
- `staging_write_freeze.write_quiescent`

Declare the system quiescent only when `active_write_requests=0`, both tracked pending job counts are zero, and two source metadata observations show no count or latest-timestamp change.

## Route inventory

### READ_ONLY

`GET /`, `/health`, `/runtime-status`, `/database-status`, `/time-sync`, `/target-estimates`, `/event-groups`, `/event-groups/{group_id}`, `/event-groups/{group_id}/localization`, `/event-groups/{group_id}/tracks`, `/localization-results`, `/tracks`, `/tracks/{track_id}`, `/tracks/{track_id}/points`, `/events`, `/events/{event_id}/context`, `/events/export.csv`, `/events/{event_id}/audio-content`, `/events/{event_id}/audio-url`, `/events/{event_id}/tdoa-clip-url`, `/device-status`, `/device-locations`, `/device-locations/{device_id}`, `/nodes/live`, `/audio-streams`, `/dashboard`, `/dashboard/legacy`, and the dashboard WebSocket.

`GET /tracks` has an existing cleanup side effect; that cleanup is explicitly skipped while frozen. `GET /device-command/{device_id}` is classified as a write path because the legacy polling handler upserts device status.

### WRITE_BLOCKED_DURING_FREEZE

`POST /events`, `POST /upload-audio`, `POST /upload-tdoa-clip`, `POST /location-update`, `PUT /device-locations/{device_id}`, `DELETE /device-locations/{device_id}`, `POST /device-command`, `POST /device-command-ack`, `DELETE /device-status/{device_id}`, `DELETE /events/{event_id}`, all admin track rebuild/delete routes, `POST /tracks/{track_id}/close`, `POST /event-groups/{group_id}/localize`, and `POST /localization-results/{result_id}/track`.

`GET /device-command/{device_id}` is also blocked because it performs a device-status upsert. The node WebSocket remains connected for heartbeat visibility, but `command_ack` and `command_result` messages are blocked. The audio upload WebSocket is a mutating upload path and is blocked by the same staging freeze policy at deployment configuration; do not open it during a freeze window.

### EXEMPT_INTERNAL_IF_REQUIRED

`POST /diagnostics/db-latency` is a bounded read-only diagnostic and `POST /observations/shadow` stores only bounded in-memory shadow state. They do not write the application database; keep them disabled or token-protected according to their existing flags.

## Background writer inventory

- `schedule_event_post_ingest` → post-ingest Fusion/Tracking and persistence.
- `schedule_device_event_status_update` → `upsert_device_event_status` and enrichment.
- Node WebSocket `command_ack` / `command_result` → device command status updates.
- `GET /tracks` stale-track cleanup → skipped while frozen.
- Device command polling → classified as a write because it upserts `device_status`.
- Dashboard broadcasts, caches, and read queries do not write application tables.

The freeze does not cancel an in-flight transaction. Wait for `pending_post_ingest_jobs`, `pending_device_status_jobs`, and `active_write_requests` to reach zero before final synchronization.

## Validation procedure

1. Keep Render staging `DATABASE_URL` pointing at Tokyo and confirm production is untouched.
2. Deploy the branch with `APP_ENV=staging` and `STAGING_WRITE_FREEZE=false`; verify normal read/write behavior in staging.
3. Set `STAGING_WRITE_FREEZE=true` and restart staging only.
4. Verify `/health`, `/runtime-status`, dashboard, events, event groups, tracks, device status, and device locations remain readable.
5. Verify representative event, audio upload, location, device-status, command, admin-track, localization, and command-WebSocket mutation paths return the freeze response.
6. Repeat `/runtime-status` and Tokyo aggregate metadata after a short interval. Require no new rows or latest-timestamp changes and `write_quiescent=true`.
7. Set `STAGING_WRITE_FREEZE=false`, restart staging, and verify a documented staging write smoke path before declaring the mechanism reversible.

## Rollback

If the freeze implementation causes a staging regression, set `STAGING_WRITE_FREEZE=false` and restart the staging service. This changes no database schema or data and does not alter production. The Singapore cutover rollback remains a separate operation: restore the staging `DATABASE_URL` to Tokyo only after the write-freeze gate is proven.
