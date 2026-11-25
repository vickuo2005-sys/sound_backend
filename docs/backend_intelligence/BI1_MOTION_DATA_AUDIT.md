# BI-1 Motion Data Audit

## Actual production inputs

The production tracker does not consume raw Observation Shadow records. Its
normal paths are:

1. Event → Event Fusion → Event Group region estimate → track measurement.
2. Recent alert Events → active multi-node region estimate → track measurement
   when no usable Event Group region was produced.
3. Event Group → Localization Result → track measurement when localization is
   enabled and meets the configured quality gate.

Observation Shadow has a separate feature-flagged, bounded in-memory sequence,
fusion, and tracking pipeline. It does not write `target_tracks` or
`target_track_points`.

## Stored Track Point evidence

`target_track_points` contains:

- identity: `id`, `track_id`, `group_id`, `localization_result_id`
- event time: `measurement_time_ms`
- raw measurement: `measured_lat`, `measured_lng`
- derived state: filtered/predicted lat/lng, east/north velocity, speed, heading
- quality: `uncertainty_radius_m`, `confidence`, outlier flag, innovation
- diagnostics: state, covariance, source, region type, reporting node count and
  reporting device ids
- backend bookkeeping: `created_at`

Source and node evidence are nested in `diagnostics_json`, not dedicated
columns. Localization method is indirectly available through
`localization_result_id` or the source diagnostics; it is not directly stored
on each point.

Velocity dt is based on `measurement_time_ms`, which is derived from Event
Group or Localization event time. It is not based on HTTP receipt time or DB
`created_at`. This is the correct temporal basis.

## Ordering

The post-ingest executor has two workers, so completion order alone is unsafe.
The production post-ingest tracking path has an optional per-key event-time
reorder buffer. The final DB tracker is serialized by a global update lock; it
does not have a production per-track mailbox. The Observation Shadow pipeline
separately has a per-device/session sequence gate and a per-region serialized
mailbox.

Any offline estimator must sort by `measurement_time_ms`, deduplicate identical
event times, and never substitute arrival order. The BI-1 simulator verifies
that arrival order E2/E3/E1 produces the same result as E1/E2/E3.

## Sufficiency decision

| Question | Result | Reason |
| --- | --- | --- |
| Can two valid points produce a raw 2D velocity? | YES | Event time and measured lat/lng are present. |
| Can current field data produce reliable speed/heading? | PARTIAL | Point cadence, uncertainty, source consistency, cooldown starvation, localization quality, and outliers vary. |
| Can it classify approaching/departing from a protected site? | NO | No Site contract or production-relative-motion assessment exists yet. |
| Can it safely drive production prediction now? | NO | Offline quality evidence has not yet been collected from representative field tracks. |

The existing tracker already computes alpha-beta speed and heading, but that is
an implementation prototype rather than proof that its measurements are
reliable. Event cooldown can make the production Event-derived path sparse;
high-frequency Observation data is not yet the production tracker input.

## Evidence needed next

- representative per-point measurement source and node count
- event-time interval distribution and missing/duplicate counts
- uncertainty distribution by localization method
- measured position residual and segment-speed distributions
- side-by-side raw baseline versus existing tracker estimates
- field truth or a controlled moving acoustic source for error measurement

Until those exist, speed/heading may be displayed only with explicit quality
and source context. Smoothing must not conceal timestamp, ordering, or data
starvation defects.
