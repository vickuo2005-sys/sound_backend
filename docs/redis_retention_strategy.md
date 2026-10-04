# Redis retention: validation only

V2-A does not change adapter retention or enable automatic trimming. XACK removes
the PEL reference, not the stream entry. Retained stream length is therefore not
consumer backlog. Backlog here means XINFO GROUPS lag + pending.

The disposable test delivered six entries, acknowledged the first three, then
used exact XTRIM MINID at the oldest pending ID. It removed only the acknowledged
prefix; all three pending entries were subsequently claimed and acknowledged.
See `outputs/redis_retention_validation.json` and the real-server regression.

Future retention must inspect every consumer group. Keep entries at/after the
oldest pending ID AND entries not yet delivered to any group. The safe cutoff is
bounded by the lowest required ID across groups, including each group's delivery
cursor; a new group reading from 0 blocks historical removal. Account for races
between inspection and new groups/replay; a coordinated maintenance/ownership
protocol is needed. Our single-group test is not that production protocol.

Approximate MAXLEN alone is unsafe: it can remove an unacknowledged payload while
leaving a PEL reference. MINID based on age must still be clamped to recovery needs.
Approximate MINID may retain extra entries; exact MINID makes the demonstrated
test boundary explicit. Never advance retention merely to make lag look smaller.

Recommended future policy: bounded time horizon plus a globally pending-safe
MINID cutoff, explicit replay horizon, memory/lag alarms, and noeviction with
observable producer backpressure. Unbounded retention grows memory; noeviction
can reject XADD rather than silently evict a transport record. No automatic policy
or production trim was introduced in this task.

References: [XTRIM](https://redis.io/docs/latest/commands/xtrim/),
[XACK](https://redis.io/docs/latest/commands/xack/),
[XINFO GROUPS](https://redis.io/docs/latest/commands/xinfo-groups/).
