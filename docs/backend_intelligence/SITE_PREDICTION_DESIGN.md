# Site Prediction Design (Interface Only)

BI-1 does not implement this API, persist Site records, calculate production
ETA, or change alerts.

## Proposed contracts

```text
Site
  site_id: string
  name: string
  latitude: number
  longitude: number
  protected_radius_m: number

SiteAssessment
  site_id: string
  track_id: string
  measurement_event_time_ms: number
  distance_m: number
  closing_speed_mps: number | null
  closest_approach_m: number | null
  time_to_closest_approach_s: number | null
  eta_to_zone_s: number | null
  status: insufficient | stationary | approaching | departing |
          entering_zone | inside_zone | misses_zone
  quality: insufficient | low | medium | high
  source_motion_version: string
```

Assessments must carry the source motion quality and event time. Arrival time
must not be used as motion time.

## Proposed geometry

Convert Site and track position into one local tangent XY frame. Let relative
position from Site to target be `r`, velocity be `v`, protected radius be `R`,
and current distance be `|r|`.

```text
closing_speed = -(r dot v) / |r|
t_cpa = max(0, -(r dot v) / (v dot v))
d_cpa = |r + v t_cpa|
```

For protected-circle entry, solve:

```text
|r + v t|^2 = R^2
(v dot v)t^2 + 2(r dot v)t + (r dot r - R^2) = 0
```

The earliest non-negative real root is `eta_to_zone_s`. A negative
discriminant means the constant-velocity line misses the zone. If already
inside, ETA is zero. Near-zero speed yields stationary status and no ETA.

## Quality and safety gates

- No approaching/departing decision for insufficient motion.
- Low-quality motion may be shown as diagnostic only, never as an Alert trigger.
- Site and track coordinates must share a documented reference frame.
- Long prediction horizons must be capped; constant velocity degrades quickly.
- Outlier, stale point, and excessive time-gap diagnostics propagate into the
  SiteAssessment rather than being smoothed away.
- Closest approach and ETA are conditional projections, not guarantees.

## Future rollout

1. Validate BI-1 raw motion against field tracks.
2. Add read-only Site configuration and an offline assessment evaluator.
3. Run shadow comparisons with no Dashboard or alert effect.
4. Define field acceptance thresholds and rollback.
5. Only then consider an API/WebSocket extension behind a default-off flag.
