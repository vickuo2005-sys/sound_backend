# V2-A security and isolation

The test harness provisions its own disposable Redis process bound only to
127.0.0.1 on an ephemeral port, with protected-mode enabled, a 128 MiB noeviction
limit, and AOF appendfsync always. It uses no shared Redis or PostgreSQL database.
This loopback instance has no password or TLS. This is not an acceptable remote
configuration: managed/remote Redis must use verified TLS (`rediss`), private
network access and authentication/least-privilege ACLs with secrets outside Git.

The binary is a community Cygwin build of Redis 7.2.10, not an official Redis
Windows distribution. Its downloaded archive was checked against its publisher's
SHA256, recorded in `outputs/redis_environment.json`. Docker and a usable WSL
distribution were absent. Revalidate on the intended Linux/managed Redis version
before any shadow deployment. No Windows service or firewall rule was installed.

Diagnostics record bind address, version and configuration, never a DSN. Child
process arguments contain only an isolated port, random stream and local marker
path. The optional client is redis-py 6.4.0 from the existing optional requirements.
The main app and domain helpers are never imported by the validation harness.
No Render setting, production resource, app worker count or database pool changes.

EventEnvelope validation already rejects credential keys/credential URLs and raw
audio keys/bytes; existing regression tests were retained. Synthetic payloads use
an object reference and padding metadata. DLQ stores only validated event_id,
trace_id, source stream ID and error class; it does not copy arbitrary payloads
or exception messages. Invalid JSON has no validated identity and is recorded
with empty identity fields. Caller-controlled IDs still require normal access
control and untrusted-text handling in future inspection tools.

Neither gitleaks nor trufflehog is installed. A focused credential-URL/private-key
scan of changed/new text files is recorded in `outputs/redis_security_review.json`.
This is not a comprehensive history scan. Runtime binaries, AOF, logs and marker
files stay outside Git; the disposable instance/data directory is stopped/removed
after the run. No Redis consumer is connected to Android, domain DB or Dashboard.

References: [Redis security](https://redis.io/docs/latest/operate/oss_and_stack/management/security/),
[publisher release](https://github.com/redis-windows/redis-windows/releases/tag/7.2.10).
