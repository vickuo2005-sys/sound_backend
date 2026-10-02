# Supabase Tokyo → Singapore Data Migration Rehearsal Report

Date: 2026-10-02  
Branch: `feat/latency-diagnostics-staging`  
Scope: staging-only data rehearsal; no Render cutover.

## Decision

**DATA_MIGRATION_REHEARSAL = NO-GO**  
**STAGING_CUTOVER_READY = NO**

The run stopped during preflight. Both staging DSN variables were available only in the local process and the PostgreSQL client tools were present, but both Supabase pooler endpoints reset the TLS connection before a SQL session was established. Per the runbook, no source snapshot, data dump, destination load, sequence update, or verification query was attempted.

The previously completed public schema rehearsal remains valid: schema diff PASS at commit `9252607`. This run did not modify Tokyo, Singapore, Render settings, production, or the PR state.

## Preflight

- `TOKYO_STAGING_DSN`: available locally; value not recorded.
- `SINGAPORE_STAGING_DSN`: available locally; value not recorded.
- `pg_dump`: 17.11.
- `pg_restore`: 17.11.
- `psql`: 17.11.
- TCP connectivity to both pooler endpoints: reachable.
- `SELECT 1` on both databases: blocked by remote TLS connection reset.

Because SQL sessions could not be established, the required 12-table count check, schema verifier rerun, source write check, and zero-row destination check were not re-run in this attempt.

## Data migration actions

No Tokyo data backup was created. No data was copied to Singapore. No `setval` was executed. No `DROP`, `TRUNCATE`, or `DELETE` was executed. No application write smoke test was attempted.

The local-only schema dump files remain uncommitted; no row-data dump was created.

## Verification status

| Check | Result |
|---|---|
| Source capture timestamp | Not captured; preflight blocked |
| `SOURCE_WRITES_ACTIVE` | UNKNOWN |
| Tokyo/Singapore row counts | Not run |
| PK/unique integrity | Not run |
| FK orphan counts | Not run |
| Sequence reconciliation | Not run |
| Checksums / aggregate reconciliation | Not run |
| Read-only application smoke | Not run |
| Tokyo unchanged | YES |
| Production touched | NO |
| Render `DATABASE_URL` changed | NO |

Machine-readable status is in `outputs/tokyo_singapore_data_verification.json`; it contains no DSN, password, token, or row contents.

## Required next step

Retry the same preflight after the Supabase pooler accepts PostgreSQL TLS connections. Do not resume from a partial migration: no partial migration occurred. Once both `SELECT 1` checks succeed, capture a fresh Tokyo snapshot, confirm Singapore remains empty, create the local-only custom-format data dump, restore it without sequence setval entries, then run the full count, PK/unique, FK, sequence, checksum, timestamp, and read-only application checks.

## Commit / PR safety

No production deployment, Render cutover, PR merge, or localization/TDOA change was performed.
