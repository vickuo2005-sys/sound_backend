# Supabase Staging Cutover Report

Date: 2026-10-02  
Branch: `feat/latency-diagnostics-staging`  
Scope: staging-only cutover preflight. No Render setting was changed.

## Decision

**STAGING_CUTOVER = NO-GO**  
**STAGING_RUNNING_ON_SINGAPORE = NO**

The cutover stopped before any Render change because the required staging-only write-freeze mechanism could not be verified. The Tokyo and Singapore databases are currently reconciled and healthy, but changing the Render staging `DATABASE_URL` without a verified write-freeze would allow a moving source snapshot and violate the cutover gate.

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

`STAGING_WRITE_FREEZE_AVAILABLE = NO`.

Repository and deployment documentation describes stopping staging clients/device uploads as a plan step, but no existing executable, reversible, staging-only freeze mechanism was available to verify. `LIVE_AUDIO_ENABLED` controls audio streaming and does not prevent event/database writes. No new maintenance flag, production-affecting control, firewall rule, or client modification was invented.

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

Provide or establish an already-supported, reversible staging-only write-freeze procedure (for example, a documented staging service pause or client stop that can be verified and undone). Then repeat the TLS and final reconciliation immediately before cutover. Do not change Render `DATABASE_URL` until that gate passes.
