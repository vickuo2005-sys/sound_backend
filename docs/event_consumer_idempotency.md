# Consumer retry and idempotency contract

No new schema or consumer table is introduced. Memory dedupe is bounded volatile history,
not a durable DB guarantee. Key = (schema_version, event_type, original event_id).
Distinct stages share event_id; repeated metadata under that ID is not another acoustic event.
Future metadata-revision events need their own semantic version/key before durable activation.

| Consumer / input | Existing key and duplicate behavior | Constraints / retry safety | Side effects / failure mode |
|---|---|---|---|
| Persistence / acoustic_event_received | events.event_id UPSERT; inserted=false suppresses new event processing; audio metadata can update existing row | events_event_id_key; replay initial persistence is generally supported, but full request effects need separate audit | DB commit, cache/device updates, trigger/audio WS; crash after commit before queue submit loses background work |
| Fusion / event_persisted | observation_group_for_event returns existing group; insertion conflicts ignored | event_group_observations_fusion_event_id_key partial unique index for fusion; label advisory xact lock retained | Group creation/rollup/merge/region updates in existing transaction; ambiguous commit requires re-read, not blanket retry |
| Tracking / position_updated | measurement timestamp <= last time rejected or enriched existing state; optional rejected-point telemetry writes | target_track_points_track_idx is NON-UNIQUE; no sufficient distributed replay constraint; unsafe to claim durable exactly-once | Track + point writes, caches, reorder emission; crash between helper commits can leave partial state; timestamps alone cannot fence concurrent consumers |
| Realtime / track_updated, event_fused | Dashboard state replacement/event-order guard | No durable WS ACK or sent-marker constraint; cannot guarantee exactly once or delivery after restart | Sends may reach some clients before failure; replay can duplicate presentation; retain canonical builders and explicit client revision semantics |

## Error classification and attempts

SUCCESS includes explicitly handled idempotent replay. RETRYABLE_FAILURE is used for
transport TimeoutError/ConnectionError and known transaction-abort SQLSTATE 40001/40P01.
Other DB/logic exceptions are permanent/unknown here: no automatic replay of ambiguous
Fusion/tracking commits. Validation/malformed schema is permanent. Unknown device metadata
follows the existing location/fallback semantics; it is not automatically a failure.
Consumer-specific retry eligibility must be proven before wiring mutations.

In memory, max_attempts defaults to 3; retry stays at the head, success ACKs logically,
terminal failure increments counters and enters bounded failure inspection. Once terminal
dedupe history is evicted, an old key can be accepted again. Full queue raises QueueFull;
shadow counts the observation failure and continues canonical legacy work. No silent drop
and no claim of durable retention is made.

Redis success XACKs only after handler success. Retryable failures remain in the PEL and
are recovered explicitly by XCLAIM/XAUTOCLAIM. Delivery count caps recovery attempts;
terminal failures atomically append a sanitized DLQ record and XACK within Redis. Original
stream entries are retained; no XDEL/trim is configured. DLQ metadata includes source ID,
event ID and error class; malformed payload/credentials are not copied into DLQ.
XADD reconnect retries can duplicate publication after ambiguous network failure: consumers
must use semantic idempotency keys, not stream IDs. Redis ACK cannot be atomic with PG/WS.
Atomic DLQ transactions also do not remove the cross-store consistency requirement.

References: [XREADGROUP/PEL](https://redis.io/docs/latest/commands/xreadgroup/),
[XAUTOCLAIM](https://redis.io/docs/latest/commands/xautoclaim/).
