# BI-1 Classification Contract

## Audited source

The Flutter `v1_1_0_flower_drone_audio.tflite` model has one float32 output
tensor with shape `[1, 1, 1, 5]`. Its final graph operator is `SOFTMAX`.
Flutter defines the index order; the model has no separate label asset:

| Index | Canonical label |
| --- | --- |
| 0 | `Airplane` |
| 1 | `Car` |
| 2 | `Drone` |
| 3 | `Electric_saw` |
| 4 | `Rainfall` |

These spellings are the transport canonical values. Translation belongs only
in UI presentation.

## `classification.v1`

```json
{
  "schema_version": "classification.v1",
  "model_id": "v1_1_0_flower_drone_audio",
  "model_version": "1.1.0",
  "model_label": "Drone",
  "confidence": 0.92,
  "class_scores": {
    "Airplane": 0.03,
    "Car": 0.02,
    "Drone": 0.92,
    "Electric_saw": 0.01,
    "Rainfall": 0.02
  },
  "operational_class": "drone",
  "aircraft_probability": 0.95,
  "is_target": true,
  "drone_subtype": null
}
```

`model_label` is the highest-scoring canonical class. `confidence` is that
class's model score. The scores are the output of the audited softmax model,
but are not claimed to be statistically calibrated real-world probabilities.
All five `class_scores` keys are required exactly once.

`drone_subtype` is reserved and must be null in BI-1. No subtype is inferred
from the five-class model.

## Operational compatibility policy

BI-1 preserves the existing threshold and admission behavior:

```text
aircraft_probability = class_scores.Airplane + class_scores.Drone
is_target = aircraft_probability > 0.5

if is_target:
    operational_class =
        drone when Drone score > Airplane score
        aircraft otherwise
else:
    operational_class = non_aircraft
```

This is intentionally not redefined as simply “top label is a target.” For an
edge case where `Car` is the top class but the two target scores sum above 0.5,
the canonical label remains `Car` while the legacy target decision remains
true. That preserves the current runtime policy.

The Backend validates the canonical label and confidence against the five
scores, then rebuilds `aircraft_probability`, `is_target`, and
`operational_class`. App-supplied policy fields are diagnostics, not trusted
authorization inputs.

## Observation and Event extensions

`observation.v1` retains its identity and ordering fields unchanged and adds an
optional nested `classification` object. The Android SQLite retry queue stores
the complete enqueue-time JSON; retries preserve `observation_id`, sequence,
event time, and classification without another inference.

`/events` retains the legacy top-level `label` and adds the same optional nested
object. Old clients omit it and remain valid. The Alert, cooldown, collection,
audio upload, fusion, and tracking decisions continue to use the legacy label.

## Persistence and compatibility

Migration `migrations/v6_0_bi1_classification.sql` adds queryable Event columns:

- `classification_schema_version`
- `model_id`, `model_version`, `model_label`, `model_confidence`
- `operational_class`, `aircraft_probability`, `drone_subtype`
- `class_scores_json` (`JSONB` in PostgreSQL, JSON text in SQLite)

The Backend's Observation Shadow remains bounded in-memory storage. BI-1 does
not turn the high-frequency shadow endpoint into a production DB write path.
Event rows retain classification history; duplicate Event upserts use the
existing `event_id` identity.

No group-level score aggregation is introduced. Fusion continues to group on
the operational legacy label; the source Event preserves the canonical label
and scores for later BI phases.

## Feature flags and rollout

- `CLASSIFICATION_V1_ENABLED=false`: master response extension default.
- `CLASSIFICATION_V1_PERSISTENCE_ENABLED`: defaults to the master flag.
- `CLASSIFICATION_V1_WEBSOCKET_ENABLED`: defaults to the master flag.

Parsing and server validation are always backward compatible. Persistence must
not be enabled before the additive migration exists in the target environment.
BI-1 neither applies that migration nor deploys these flags.

Rollback is to disable all three flags. Legacy `label` remains present, so no
client or dashboard rollback requires deleting the additive columns.
