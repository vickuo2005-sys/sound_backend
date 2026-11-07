# Supabase PostgreSQL TLS Root-Cause Isolation Report

Date: 2026-10-02  
Branch: `feat/latency-diagnostics-staging`  
Scope: TLS/session diagnostics only. No data migration was performed.

## Current result

The previous TLS reset is intermittent. On the current local run, both staging Session Pooler endpoints completed verified TLS sessions:

| Environment | TCP 5432 | SSLRequest | TLS handshake | Authentication / query |
|---|---|---|---|---|
| LOCAL_CURRENT_NETWORK / Tokyo | PASS | `S` | PASS, TLS 1.3 | psql `SELECT 1` PASS; psycopg2 PASS |
| LOCAL_CURRENT_NETWORK / Singapore | PASS | `S` | PASS, TLS 1.3 | psql `SELECT 1` PASS; psycopg2 PASS |
| INDEPENDENT_NETWORK | Not available | Not tested | Not tested | Not tested |
| RENDER_STAGING_HOST | No PostgreSQL shell available | Not tested | Not tested | Not tested |

`psql \conninfo` reported TLS 1.3 with `TLS_AES_256_GCM_SHA384` for both regions. The raw PostgreSQL SSLRequest returned `S`, and a credential-free TLS handshake completed when certificate verification was disabled for that diagnostic. Authenticated psql and psycopg2 checks used `sslmode=require` and returned `SELECT 1` successfully.

The earlier `SSL SYSCALL` / connection-reset errors therefore remain an intermittent observation; they did not recur on this retest.

## Independent-environment limitation

No mobile hotspot, second trusted machine, independent cloud shell, or Render shell with `psql`/psycopg2 was available. Render HTTP is not an equivalent PostgreSQL TLS test. The result cannot distinguish a local-network-only fault from an intermittent pooler/client path fault.

`ROOT_CAUSE_DIRECTION = UNRESOLVED`  
`CONFIRMED_ROOT_CAUSE = NO`

## Decision

`TOKYO SELECT 1 = PASS` with `sslmode=require`.  
`SINGAPORE SELECT 1 = PASS` with `sslmode=require`.  
`DATA_MIGRATION_PREFLIGHT_READY = YES` for the TLS prerequisite only.

No migration was resumed because this task is TLS isolation only. The next migration run must repeat the same preflight immediately before creating a dump and stop if either TLS session resets.

No Render `DATABASE_URL`, Tokyo database, Singapore runtime data, production, firewall/security settings, localization/TDOA, or PR state was modified.

Machine-readable results: `outputs/supabase_tls_preflight_20261002.json`.
