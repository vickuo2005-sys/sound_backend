# Localization Schema

Migration files:

```text
migrations/v3_3_localization.sql
migrations/v3_4_hybrid_localization.sql
```

Main table:

```text
localization_results
```

Important fields:

- `group_id`
- `method`
- `version`
- `status`
- `estimated_lat`
- `estimated_lng`
- `confidence`
- `residual_m`
- `uncertainty_radius_m`
- `geometry_quality`
- `reference_device_id`
- `node_count`
- `event_time_ms`
- `input_signature`
- `diagnostics_json`

`input_signature` is unique so recomputing the same input remains idempotent.
