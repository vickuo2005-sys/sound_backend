# Future Redis Streams cutover — not authorized/activated by V1

Today: legacy pipeline authoritative; both flags default OFF. EVENT_DRIVEN_PIPELINE_ENABLED
is reserved and cannot route through Redis. EVENT_DRIVEN_SHADOW_ENABLED permits only local/staging
canonical-result projection. EVENT_BUS_BACKEND and REDIS_STREAM_URL are not read by the request
path. Optional adapter can be explicitly constructed in isolated tests only. Default requirements
do not import/install redis-py. Optional installation uses requirements-events-redis.txt.

Future configuration names: EVENT_BUS_BACKEND=memory|redis, REDIS_STREAM_URL (secret),
REDIS_EVENT_STREAM, REDIS_CONSUMER_GROUP, REDIS_CONSUMER_NAME. No credentials committed.
Changing these variables today does not perform a cutover.

| Phase | Prerequisites and action | Rollback criterion and action |
|---|---|---|
| A: shadow only | Local tests and nonmutating projections; compare schema/ordering/payloads | Any mutation, duplicate WS, queue overflow or legacy regression: shadow flag false; preserve legacy path |
| B: Redis persistence shadow | Real Redis crash/reconnect/PEL/DLQ tests pass; publish sanitized copies, never execute a second DB insert | Missing/duplicate IDs, unacceptable queue/resource lag: stop shadow publication/consumers; retain PEL/stream evidence; legacy persists |
| C: Fusion canary | Proven outbox/commit-to-publish boundary; durable observation idempotency, partition fencing and merge/late-event proofs; exclusive event ownership | Group/count/region discrepancy, event loss, PEL buildup: stop canary admission, fence consumers, reconcile committed IDs before restoring exclusive legacy ownership |
| D: Redis first-position path | Correlated 30–50 real events, tested DB/stream crash gap and duplicate WS strategy; same semantics | Latency regression, schema/event loss or ordering issue: stop admission, drain/fence in-flight work, return exclusive IDs to legacy after reconciliation; never dual-write |
| E: Tracking consumer | Durable track-point idempotency/fencing and multi-transaction recovery proof, timestamp/reorder tests | Track/point inconsistency, duplicate telemetry or association change: fence tracking consumer, reconcile states, restore canonical legacy tracking |
| F: legacy removal | Sustained field/load correctness, restart/disaster tests and proven replay/backlog tool | Recoverable release rollback plus stream/DB state reconciliation; retain old code/ownership controls through rollback window |

Each future phase requires separate approval and deployment evidence. Do not ACK/drop pending work
merely to clear backlog. No destructive trimming until pending retention/recovery tests prove it safe.
Redis >=6.2 is needed for XAUTOCLAIM; XCLAIM remains an explicit alternative. Blocking reads <=1000 ms,
bounded reconnect attempts and stop/close let idle workers exit; in-flight handler completion must
precede shutdown ACK. Durable consumer recovery primitives are implemented, not live-verified here.
Single-stream transport does not guarantee partition order with concurrent consumers.

V1 exact rollback: no deploy was performed. On a future V1-only staging deployment, set both
EVENT_DRIVEN_* flags false (do not change DB/workers/resources), restart/redeploy to disable observation,
and if needed deploy 9ba7f800fe30e361b9c07e7dd1c8211dba5a7596. No schema rollback/data restoration needed:
V1 made no schema changes and shadow never writes DB or sends WS. Current staging stays on 9ba7f8.

References: [redis-py optional client](https://redis.io/docs/latest/develop/clients/redis-py/),
[consumer groups](https://redis.io/docs/latest/commands/xreadgroup/),
[pending recovery](https://redis.io/docs/latest/commands/xautoclaim/).
