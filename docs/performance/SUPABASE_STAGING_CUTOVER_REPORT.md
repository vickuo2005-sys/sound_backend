# Supabase Staging Cutover Report

Date: 2026-10-02  
Branch: `feat/latency-diagnostics-staging`  
Scope: staging-only cutover preflight. Render staging was updated only for deployment and reversible freeze validation; `DATABASE_URL` was not changed.

## Decision

**STAGING_CUTOVER = NO-GO**  
**STAGING_RUNNING_ON_SINGAPORE = NO**

The cutover remains **NO-GO**. Commit `b3ed190738930ca7e9305a4f08cb593120e6912c` was deployed to the identified Render staging service. The reversible write-freeze was activated and reported quiescent, then disabled after the gate failed. The existing Render staging Tokyo connection failed password authentication, so read checks were degraded and Singapore was not assigned.

## Pre-cutover checks

- Tokyo TLS (`sslmode=require`): PASS; psql and psycopg2 `SELECT 1` passed.
- Singapore TLS (`sslmode=require`): PASS; psql and psycopg2 `SELECT 1` passed.
- Schema/catalog diff: PASS; 12 application tables on both sides.
- Fresh source and destination row counts: all 12 match.
- Fresh aggregate checksums: all 12 match.
- Latest timestamp aggregates: match.
- PK/unique integrity: PASS.
- FK orphan counts: Tokyo 0, Singapore 0.
- Sequence runtime values: `device_commands_id_seq=13`, `events_id_seq=532` on both sides.
- `FINAL_SYNC_REQUIRED = NO` for the captured state.
- Source write observation during metadata capture: no observed count/timestamp change; this is not a freeze.
- Render deployment identity: service `sound-backend-staging`, ID `srv-da6kdn61egvs7392r92g`, branch `feat/latency-diagnostics-staging`, commit `b3ed190738930ca7e9305a4f08cb593120e6912c`.

## Write-freeze gate

`STAGING_WRITE_FREEZE_AVAILABLE = YES (implementation and local tests); STAGING_WRITES_FROZEN = YES (Render observed)`.

The branch provides an explicit `APP_ENV=staging` + `STAGING_WRITE_FREEZE=true` guard. Render reported `active_write_requests=0`, both pending job counters zero, and `write_quiescent=true`. The flag was later set false and Render reported normal mode again. `LIVE_AUDIO_ENABLED` remains unrelated to the freeze. Local route, background, production-guard, and unfreeze tests passed.

During the frozen smoke check `/health` and `/runtime-status` returned 200. Read endpoints `/events`, `/tracks`, and `/device-status` returned degraded responses because the existing Tokyo password was rejected; `/event-groups` returned 500 for the same database failure. `/device-locations` returned 200 with an empty result. The representative write request was not allowed to proceed beyond the freeze middleware. No controlled write or latency A/B was run.

## Render and rollback state

- Render staging service: `sound-backend-staging` (previously documented service ID `srv-da6kdn61egvs7392r92g`).
- Database before: Tokyo, based on the previously verified unchanged Render configuration.
- Database after: unchanged; Singapore was not assigned.
- `DATABASE_URL` changed: no.
- Rollback performed: no.
- Rollback readiness: Tokyo remains the unchanged Render target; Singapore was not assigned. A future cutover remains blocked until the staging credential is corrected and all read/TLS/reconciliation gates pass.
- Production touched: no.
- PR merged: no.

## Not run

Post-cutover checks and Singapore latency A/B were not run because the pre-cutover database authentication gate failed. Freeze activation/unfreeze and pre-cutover health/runtime checks were run. No latency improvement is claimed.

Machine-readable status is in `outputs/supabase_staging_cutover_verification.json`. No DSN, password, token, dump, or raw row payload is included.

## Required next step

Correct and verify the Render staging Tokyo database credential without exposing it, then rerun read checks. Repeat TLS and final reconciliation while the freeze is active. Do not change Render `DATABASE_URL` until all gates pass.

