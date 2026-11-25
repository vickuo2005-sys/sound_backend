# Supabase Tokyo → Singapore Staging Data Migration Rehearsal Report

Date: 2026-10-02  
Branch: `feat/latency-diagnostics-staging`  
Scope: staging data rehearsal only. Render cutover was not performed.

## Decision

**DATA_MIGRATION_REHEARSAL = PASS**
**STAGING_CUTOVER_READY = NO**

The 12 public application tables were copied from Tokyo staging to the already-matched Singapore staging schema and reconciled. Tokyo remains the rollback source. No Render `DATABASE_URL` was changed, no production service was touched, and no localization/TDOA setting was enabled.

## 1. Preflight and source snapshot

- Tokyo TLS with `sslmode=require`: PASS.
- Singapore TLS with `sslmode=require`: PASS.
- psql and psycopg2 `SELECT 1`: PASS for both.
- Schema/catalog verifier: PASS; 12 source tables, 12 destination tables, no missing or extra tables.
- Source capture timestamp: recorded in `outputs/tokyo_source_snapshot_data_rehearsal.json`.
- `SOURCE_WRITES_ACTIVE = NO_OBSERVED_DURING_5S_WINDOW`; row counts and observed maximum timestamps did not change during the five-second observation. This is a rehearsal snapshot, not a maintenance freeze.
- Singapore pre-restore safety check: all 12 application tables had zero rows.

Tokyo snapshot counts:

| table | Tokyo rows | Singapore rows | match |
|---|---:|---:|---|
| audio_stream_sessions | 0 | 0 | yes |
| device_commands | 13 | 13 | yes |
| device_connections | 0 | 0 | yes |
| device_locations | 4 | 4 | yes |
| device_status | 4 | 4 | yes |
| event_group_observations | 372 | 372 | yes |
| event_groups | 183 | 183 | yes |
| events | 375 | 375 | yes |
| localization_pair_results | 0 | 0 | yes |
| localization_results | 0 | 0 | yes |
| target_track_points | 90 | 90 | yes |
| target_tracks | 17 | 17 | yes |

## 2. Backup and restore

A local-only custom-format data dump was created from Tokyo with `--data-only --no-owner --no-privileges`, restricted to the 12 public application tables. It is ignored by `.git/info/exclude` and was not committed:

- path: `outputs/tokyo_staging_data_rehearsal.dump`
- bytes: 185814
- SHA-256: `a070e08035d821cd9fbd798a09c6ea6116dd086ea05fdb861a85c552e073da70`

The restore succeeded in Singapore with 12 table-data entries. The two automatic `SEQUENCE SET` entries were excluded so sequence runtime state could be restored only after row validation. No DROP, TRUNCATE, or DELETE was executed, and provider-managed schemas and GCS objects were not dumped or copied.

## 3. Integrity validation

- Row counts: all 12 match the captured Tokyo snapshot.
- Deterministic row checksums: all 12 match. The checksum is an aggregate of canonical PostgreSQL `jsonb` row text ordered deterministically; no raw row payloads are in the artifact.
- PK integrity: zero NULL PKs and zero duplicate PK groups where PKs exist.
- Unique constraints: no duplicate groups detected.
- FK orphans: Tokyo baseline 0; Singapore 0; no new orphans.
- Relationship aggregates for event-group observations and target-track points match.
- Latest timestamp aggregates for available created/updated/event/group/track columns match.

## 4. Sequence runtime state

Sequence values were read from Tokyo after the row restore and set in Singapore without deriving from row counts:

| sequence | Tokyo | Singapore | next value | above existing max |
|---|---:|---:|---:|---|
| device_commands_id_seq | 13 | 13 | 14 | yes |
| events_id_seq | 532 | 532 | 533 | yes |

The historical difference between `events=375` rows and `events_id_seq=532` was preserved.

## 5. Read-only application smoke

Read-only queries against Singapore succeeded for all 12 application tables, including events, event groups, target tracks, target track points, device status, and device locations. No write smoke test was run. No non-null GCS reference field was present in the captured application snapshot to validate; no GCS object was copied.

## 6. Safety and remaining risks

- Tokyo unchanged and still reachable: yes.
- Singapore runtime data now contains the rehearsal copy: yes.
- Production touched: no.
- Render `DATABASE_URL` changed: no.
- PR merged: no; branch remains Draft.
- TDOA/localization enabled: no.

The previous TLS reset was intermittent. Repeat the TLS preflight immediately before any future cutover. The five-second source-write observation is not a freeze mechanism, so a future cutover would require a separately approved staging maintenance window or an explicit reconciliation plan.

Machine-readable aggregate verification is in `outputs/tokyo_singapore_data_verification.json`. Source and destination snapshots are in `outputs/tokyo_source_snapshot_data_rehearsal.json` and `outputs/singapore_pre_restore_data_rehearsal.json`; they contain metadata and aggregates only.

