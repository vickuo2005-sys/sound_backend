# Supabase Staging Cutover Report

Date: 2026-10-02  
Branch: `feat/latency-diagnostics-staging`  
Scope: staging-only cutover preflight. No Render setting was changed.

## Decision

**STAGING_CUTOVER = NO-GO**  
**STAGING_RUNNING_ON_SINGAPORE = NO**

The cutover remains stopped before any Render change. A fail-closed, reversible staging-only write-freeze mechanism is now implemented and locally validated, but it has not yet been activated and observed on the Render staging service. The Tokyo and Singapore databases are currently reconciled and healthy, but changing the Render staging `DATABASE_URL` before staging activation/quiescence evidence would allow a moving source snapshot and violate the cutover gate.

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

## Write-freeze gate

`STAGING_WRITE_FREEZE_AVAILABLE = YES (implementation and local tests); STAGING_WRITES_FROZEN = NOT YET TESTED ON RENDER`.

The branch now provides an explicit `APP_ENV=staging` + `STAGING_WRITE_FREEZE=true` guard. It blocks classified HTTP/database mutation paths, command WebSocket writes, audio upload WebSocket writes, and new post-ingest/device-status jobs while preserving reads. `LIVE_AUDIO_ENABLED` remains unrelated to the freeze. Local route, background, production-guard, and unfreeze tests passed; Render activation and quiescence observation are still pending.

Per the runbook, the process stopped before rollback-state confirmation, Render mutation, health checks, controlled writes, unfreeze, and latency A/B.

## Render and rollback state

- Render staging service: `sound-backend-staging` (previously documented service ID `srv-da6kdn61egvs7392r92g`).
- Database before: Tokyo, based on the previously verified unchanged Render configuration.
- Database after: unchanged; Singapore was not assigned.
- `DATABASE_URL` changed: no.
- Rollback performed: no.
- Rollback readiness: not assessed because no cutover occurred.
- Production touched: no.
- PR merged: no.

## Not run

Post-cutover `/health`, `/runtime-status`, dashboard/WebSocket checks, controlled write smoke, staging unfreeze, and Singapore latency A/B were not run because the cutover gate failed. No latency improvement is claimed.

Machine-readable status is in `outputs/supabase_staging_cutover_verification.json`. No DSN, password, token, dump, or raw row payload is included.

## Required next step

Activate `APP_ENV=staging` and `STAGING_WRITE_FREEZE=true` on the Render staging service, verify `/runtime-status` reports `write_quiescent=true`, and observe Tokyo metadata twice without changes. Then repeat TLS and final reconciliation immediately before any cutover. Do not change Render `DATABASE_URL` until that gate passes.

