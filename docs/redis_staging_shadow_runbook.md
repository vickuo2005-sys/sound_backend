# V2-B runbook and rollback

V2A_VALIDATED_SHA=a12a32b8b9dd38a8b3c58c2e9b291f1e508b0af6.
Branch: feat/event-driven-redis-staging-shadow.
Only service: sound-backend-staging / srv-da6kdn61egvs7392r92g, Singapore.
Production and Draft PR #5 are outside deployment scope.

## Code boundary

Legacy initial submission/Fusion/Tracking and existing DB/WS mutations are intact.
After successful legacy initial submission a fixed scalar projection is enqueued
as received/persisted observations; after canonical legacy results it enqueues
position/track (track optional), or a terminal no-Fusion-result observation.
No independent recomputation, DB mutation or WS broadcast occurs in the consumer.
The publisher serializes/checks 64 KiB/publishes outside the request thread.
Queue capacity is 256 jobs (each job has at most two phase observations); rejection
and loss are visible. Shadow is deliberately lossy, never a durable outbox.

One publisher and exactly one audit consumer are additional shadow-only daemon
threads; legacy worker counts and DB pool are unchanged. Bounded retry/backoff;
failed jobs are dropped, not requeued forever. Connection handles, contexts,
timelines, audit keys and evidence are bounded. Shutdown stops these threads.

## Deployment sequence

1. Record prior branch/build command and live build/deploy ID. Preserve all existing
   secrets, start command, instance/worker/pool/localization settings.
2. Only staging: use this branch and build command
   `pip install -r requirements-staging-shadow.txt`.
3. Deploy with APP_ENV=staging, REDIS_SHADOW_ENABLED=false,
   EVENT_DRIVEN_PIPELINE_ENABLED=false, REDIS_REAL_TRAFFIC_ENABLED=false.
   EVENT_DRIVEN_SHADOW_ENABLED also remains false (the V1 memory observer is separate).
4. Require /health healthy, no DB init error, expected full build SHA,
   /runtime-status without redis_shadow, Dashboard HTTP + existing JS/WS health,
   unchanged workers/pool/localization. Do not send synthetic acoustic events and
   label them Android compatibility tests. Actual API contract is covered locally.
5. Use the isolated Key Value instance sound-backend-staging-shadow-v2b,
   red-db0vpj2d0e5s73debji0. Only permit staging egress ranges reported by Render:
   74.220.52.0/24 and 74.220.60.0/24, not 0.0.0.0/0. These ranges are shared among
   Render services; authentication/TLS are still required. Do not edit workspace
   or production networking. Private plaintext Redis is refused by the code;
   use the authenticated external rediss URL with certificate verification.
6. Transfer the provider URL directly into staging REDIS_SHADOW_URL secret; never
   put it in chat, Git or report. Verify TLS/auth/INFO/stream support from the actual
   staging runtime; record provider/version, noeviction and memory/persistence.
7. Set REDIS_SHADOW_STREAM=staging:acoustic-events:v1,
   REDIS_SHADOW_GROUP=staging-shadow-audit-v1,
   REDIS_SHADOW_CONSUMER=staging-shadow-single,
   REDIS_SHADOW_CONSUMERS=1, REDIS_SHADOW_QUEUE_MAX=256,
   REDIS_SHADOW_MAX_EVENT_BYTES=65536. Then enable REDIS_SHADOW_ENABLED=true.
   Keep both authoritative flags false. Require connected=true, queue/PEL/lag=0.

## Real test populations

Require node_A01/A02/A03/A04 online and simultaneously listening, localization
disabled. First collect a nearest comparable 30–50-event shadow-OFF run with the
same devices/network/stimulus and exact version. Keep per-event IDs/time/device
count/network notes; save first_position samples, not sums of stage percentiles.
Historical 9ba data can provide context, not automatically a comparable baseline.

With shadow ON collect 10 unique real event IDs for smoke. Reconcile accepted
legacy traces with received/persisted + canonical position and optional track
observations. Require no loss/rejection/malformed/correlation/order faults, no
duplicated DB/WS effects, queue/PEL/lag drained. On correctness fault disable
REDIS_SHADOW_ENABLED immediately while legacy remains authoritative.

Then collect 30–50 new unique real event IDs (not HTTP retry attempts). Record
monotonic shadow enqueue/publish/ingest-to-publish/consumer-lag/ACK/end-to-end and
legacy first_position P50/P95/P99/max with n. Streams carry references/scalar
canonical fields, no raw audio/base64. Runtime evidence is bounded, so poll and
export during the test rather than relying only on a final rolling snapshot.

Consumer-lag uses T3 (read delivery) minus local T2 (XADD reply completed) only
when both are known and T3>=T2. Redis can deliver before the publisher gets its
reply: those samples are excluded and counted, never fabricated as negative/zero
network latency. Older-process messages lack the current monotonic clock domain;
do not mix their end-to-end latency into new-process samples. ACK duration always
uses local monotonic time. Publish-from-ingest/end-to-end include legacy DB time
because the mirror is observed after successful persistence. They are not legacy
first-position latency or browser/network/render latency.

Flag unsafe if comparable legacy P95 rises >10% OR >100 ms; disable shadow and
diagnose. Small populations do not establish statistical certainty. A missing
comparable OFF run means performance safety is NOT ESTABLISHED.

## Failure tests and rollback

Local tests prove API parity with disabled/unavailable/full/oversized shadow and
real Redis PEL recovery. Managed staging outage/crash tests are separate evidence;
do not pass them on the strength of local tests. Never shut down the primary backend
or real database to simulate Redis failure. A disposable managed test namespace
may be used for controlled transport failure/crash before ACK, without any domain
handler. Do not claim an Android outage test without actual Android traffic.

An opt-in `REDIS_SHADOW_TRANSPORT_PROBE=true` runs once before the primary audit
consumer starts. It creates a separate `staging:shadow-probe:<uuid>` stream/group,
ACKs a synthetic received phase, disconnects after reading a synthetic persisted
phase without ACK, then claims/ACKs with a new consumer connection. It retains both
entries and exposes sanitized results under redis_shadow.transport_probe. It uses
a separate sampler and no Android API/DB/WS. This validates managed abandoned-PEL
recovery, not an OS process kill or Android outage. Disable the flag after exporting
evidence. Failure is recorded without affecting primary startup or legacy traffic.

Use `tools/collect_redis_shadow.py --expected-commit <full-sha> --samples 120
--interval 2 --output outputs/<unique-name>.jsonl` for read-only collection during
each real run. The collector refuses another build/service, connection URLs and
overwriting evidence. It does not generate traffic or claim physical test results.

Primary rollback: set REDIS_SHADOW_ENABLED=false and redeploy the same staging
commit; remove the shadow URL only if needed. Legacy remains the sole system of
record. Code rollback if necessary: restore prior staging branch/build command and
deploy 9ba7f800fe30e361b9c07e7dd1c8211dba5a7596. Never change DATABASE_URL,
worker count, resources or localization as part of this rollback. Preserve Redis
evidence for analysis; do not trim PEL. V2C must not begin automatically.
