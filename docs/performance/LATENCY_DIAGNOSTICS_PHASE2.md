# Latency Diagnostics Phase 2

This phase adds in-process, monotonic timing only. It does not change SQL statements, transaction boundaries, fusion or tracking calculations, worker counts, database schema, or Render resources.

## Suspected bottlenecks

### Event Fusion

1. **Suspected bottleneck:** the sequential database work inside one fusion event, including advisory lock acquisition, event/group lookup, observation persistence, rollup updates, and stale-group cleanup.
2. **Source:** `services/event_fusion.py::process_event()` and its SQL helpers.
3. **Evidence:** the Phase 1 physical Android staging run measured `event_fusion` mean about 4.84 s and P95 about 5.50 s. Phase 2 now records `fusion_lock_wait`, `fusion_observation_load`, `fusion_group_lookup`, `fusion_compute`, `fusion_group_save`, `fusion_observation_save`, and `fusion_group_cleanup` so the next staging run can separate database wait from Python computation.
4. **Proposed optimization:** inspect the new per-stage P95 values, query plans, lock contention, and transaction duration before considering fewer round trips or narrower transaction scope.
5. **Risk:** changing lock or transaction behavior can change grouping race outcomes and event consistency. No optimization is applied in this phase.

### Active alert tracking

1. **Suspected bottleneck:** source event/group reads and track point enrichment may dominate the association calculation.
2. **Source:** `main.py::process_tracking_for_active_alert_region()`, `process_tracking_measurement()`, and tracking database helpers.
3. **Evidence:** Phase 1 measured `active_alert_tracking` mean about 1.74 s and P95 about 2.38 s. Phase 2 records source load, track lookup, association, DB save, and point-load stages.
4. **Proposed optimization:** compare `active_tracking_source_load`, `active_tracking_track_lookup`, `active_tracking_association`, `active_tracking_db_save`, and `active_tracking_point_load` on 30–50 real multi-node events.
5. **Risk:** changing association or persistence order could alter track identity and history. No optimization is applied.

### Event initial DB write

1. **Suspected bottleneck:** PostgreSQL connection acquisition, the INSERT/UPSERT with `RETURNING`, or commit.
2. **Source:** `main.py::upsert_event_postgres_with_inserted()` and `upsert_event_sqlite_with_inserted()`.
3. **Evidence:** Phase 1 measured `event_db_write` P95 about 1.08 s. Phase 2 records `event_db_connection_acquisition`, `event_db_insert_returning`, and `event_db_commit` while preserving the existing SQL.
4. **Proposed optimization:** use the stage distribution and connection pool/DB server evidence to choose whether connection reuse or query tuning is justified.
5. **Risk:** changing upsert or commit behavior can affect idempotency and event visibility. No optimization is applied.

### Device status worker

1. **Suspected bottleneck:** location enrichment or the device-status upsert/returning query.
2. **Source:** `main.py::upsert_device_event_status()` and `run_device_event_status_worker()`.
3. **Evidence:** Phase 1 device-status worker duration was about 1.3–1.7 s. Phase 2 records `device_status_enrichment`, `device_status_db_upsert`, and `device_status_broadcast_schedule`.
4. **Proposed optimization:** compare enrichment, DB, and scheduling P95 values under staging load.
5. **Risk:** changing status write frequency or cache semantics can make node monitoring stale. No optimization is applied.

## Interpretation limits

Each stage has its own sample population and may execute conditionally. Stage P95 values must not be summed to claim an end-to-end P95. Browser message-handler timing remains client-side handler work and is not network latency or paint time.

The next physical-device run is required before selecting an optimization. The existing evidence is from one Android staging node and does not establish multi-node production behavior.
