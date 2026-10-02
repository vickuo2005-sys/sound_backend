# Supabase PostgreSQL TLS Preflight Report

Date: 2026-10-02  
Branch: `feat/latency-diagnostics-staging`  
Scope: TLS/session diagnostics only. No migration or database writes were performed.

## Result

- Tokyo TCP 5432: **PASS**
- Singapore TCP 5432: **PASS**
- Tokyo PostgreSQL TLS/session: **FAIL** during TLS handshake
- Singapore PostgreSQL TLS/session: **FAIL** during TLS handshake
- Default PostgreSQL connection (`sslmode` omitted): **PASS** for both; `SELECT 1` succeeded with `pg_stat_ssl.ssl = false`.
- `sslmode=require`: **FAIL** for both.
- `TOKYO SELECT 1` using default fallback: **PASS**.
- `SINGAPORE SELECT 1` using default fallback: **PASS**.
- `DATA_MIGRATION_PREFLIGHT_READY`: **NO** because a verified encrypted PostgreSQL session is not available.

## Sanitized DSN inspection

Both tested DSNs are `postgresql` URIs using port `5432`, include a database path and username, and use Supabase Session Pooler hostnames matching `*.pooler.supabase.com`. The original DSN form had no `sslmode` query parameter; `sslmode=require` was tested only as a temporary process argument and was not persisted.

No password, full DSN, token, or project identifier was written to the report or artifact.

## psql and psycopg2 behavior

`psql` with the original/default DSN completed `SELECT 1` for Tokyo and Singapore. The same connections with temporary `sslmode=require` failed with a libpq `SSL SYSCALL` / connection-reset error before authentication.

Minimal psycopg2 tests matched this behavior. Default connections succeeded in approximately 2.4 s (Tokyo) and 1.2 s (Singapore); `sslmode=require` failed in approximately 0.6 s and 0.3 s. Durations are diagnostic only and are not application latency measurements.

## TLS handshake diagnostic

A raw PostgreSQL SSLRequest was sent without credentials to each endpoint. Both returned `S`, which means the endpoint accepted the request to start TLS. The subsequent TLS handshake was reset by the peer for every tested resolved IPv4 address:

- Tokyo: 4 A records tested; all reset.
- Singapore: 3 A records tested; all reset.
- TLS 1.2, TLS 1.3, and Python default TLS negotiation all reset.
- OpenSSL CLI was not installed; Python used OpenSSL 3.0.18.

This confirms the failure layer is **after PostgreSQL SSLRequest acceptance and before authentication**, specifically during TLS negotiation. It does not identify a single root cause.

## Common-path observations

- HTTP proxy environment: not set.
- HTTPS proxy environment: not set.
- WinHTTP proxy: direct access.
- Windows firewall profiles: enabled; no settings were changed.
- IPv4 DNS resolution and TCP reachability: correct, but all tested addresses reset TLS.
- No firewall, antivirus, VPN, or security setting was modified.

Because both regions show the same behavior and all IPv4 addresses reproduce it, a common-path network/security inspection issue or a pooler-side TLS path issue remains possible. A root cause is **not confirmed** from this host alone.

## Safe conclusion

Do not resume data migration yet. The current default connection succeeds only through non-TLS fallback, so it is not sufficient for the migration preflight. The safe next diagnostic is to repeat the same `sslmode=require` handshake from an independent network or trusted host, or use a Supabase-supported direct/session-pooler client path where TLS is verified. Do not use `sslmode=disable` as a migration workaround.

Machine-readable results are in `outputs/supabase_tls_preflight_20261002.json`.

No Render `DATABASE_URL`, production service, Tokyo schema/data, or Singapore runtime data was changed.
