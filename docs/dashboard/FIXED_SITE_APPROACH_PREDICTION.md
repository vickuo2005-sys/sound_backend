# Fixed-site approach prediction

## Product goal and current validation level

This staging-only V2.4.2 simulation answers a narrow operational question:
given the current simulated position and motion vector, is the target closing
on a fixed site, will the constant-velocity path intersect the protected
radius, and when is the first predicted entry?

The result is **SIMULATED ETA**, not an evacuation instruction, threat level,
or production ETA. Motion field accuracy remains unvalidated. Therefore:

> Simulated ETA != field-validated ETA.

## CURRENT_SIMULATION_AUDIT

Audit baseline: `558cb612cdd995921588a29d4457898547dc3264` on
`feat/v2-4-dashboard-simulation`.

- Simulation Mode already existed behind `DASHBOARD_SIMULATION_ENABLED`.
- Static scenarios lived in `static/dashboard_simulation_scenarios.js`.
- Playback interpolated the visible current marker between immutable 1 Hz
  scenario points and derived history only from elapsed scenario time.
- Historical track, current position, and predicted path were separate Google
  Maps overlays.
- Motion was estimated from recent simulation history; future coordinates
  were projected from the current position and one estimated motion vector.
- The fixed site and 100 m circle already existed and the site was assessed
  only after projection.
- Haversine distance, radial closing speed, analytic CPA, and quadratic
  protected-circle intersection were already implemented.
- ETA was not calculated with a `distance / speed` shortcut.
- Simulation was frontend-only: it made no REST, database, WebSocket broadcast,
  event, track, or device-state write.
- The primary right-hand information card was still **Motion**. Site outcome,
  ETA, and distance forecast were visually subordinate; ENTRY and CPA were not
  shown on the map. This was the product/UX defect addressed here.

Audit answers:

| Question | Finding |
|---|---|
| A. Prediction path only from motion vector? | Yes. |
| B. Site affects prediction path? | No. It is reference geometry only. |
| C. ETA uses distance / speed? | No. It uses line/circle intersection. |
| D. CPA implemented? | Yes, analytic CV CPA. |
| E. Protected radius implemented? | Yes, 100 m. |
| F. Largest UI information card? | Before refinement: Motion. After refinement: Site Approach. |

## Architecture and data flow

```text
TRACK / MOTION
  -> Trajectory Prediction
  -> Predicted Positions
  -> Fixed Site Assessment
  -> Distance / Trend / CPA / Simulated ETA
```

Site coordinates are never inputs to motion estimation or trajectory
projection. Relocating the site may change bearing, distances, closing speed,
trend, CPA, and ETA, but must not change any predicted latitude/longitude for
identical motion inputs.

`DEMO SITE ALPHA` uses the arbitrary demo-only coordinate
`25.0390, 121.5752` and `protected_radius_m = 100`. It is fixed for all three
scenarios and does not represent a real person, device, or protected facility.

## Constant-velocity projection

Heading uses `0 deg = north`, `90 deg = east`, `180 deg = south`, and
`270 deg = west`:

```text
vE = speed * sin(heading)
vN = speed * cos(heading)
P(t + h) = P(now) + V(now) * h
```

The `+5`, `+10`, `+15`, and `+30 s` points are independently projected from
the same current state. Predictions are never fed back as observations.
Short-range local EN offsets use Earth radius `6,371,000 m` and are converted
to latitude/longitude around the current reference latitude.

## Site geometry

Current and future absolute distances use Haversine distance. Bearing to site
is a geographic bearing. In the local EN frame, closing speed is:

```text
r = site - current
closing_speed = velocity dot (r / |r|)
```

Positive closing speed means a component toward the site; negative means away.
Trend combines this radial term with the independently calculated five-second
distance change. Central constants gate low speed (`0.5 m/s`), radial evidence
(`0.1 m/s`), and distance trend (`0.5 m`).

CPA uses `t = -(r dot v) / (v dot v)` in site-relative coordinates. A past CPA
is represented by the current distance/time zero; a future CPA is clamped to
the 300-second assessment horizon.

## Protected-radius intersection and simulated ETA

ETA means the first predicted entry into the protected radius, not arrival at
the site center. It solves:

```text
(v dot v)t^2 + 2(r dot v)t + (r dot r - R^2) = 0
```

The smallest non-negative future root is used. Explicit no-ETA reasons are
`LOW_SPEED`, `NO_SITE_INTERSECTION`, `NO_FUTURE_INTERSECTION`, `DEPARTING`,
`TREND_UNCERTAIN`, and data-quality reasons. `AT_SITE` returns zero. The UI
shows an ETA only for a valid approaching intersection or the already-inside
case. It never substitutes `distance / speed`.

## Output contract

`computeSimulationPredictionTick()` returns `simulation`, status/reasons,
`model: "CV"`, current state, fixed-site identity and distance, motion trend
and closing speed, four distance-bearing predictions, and an `approach` object
with CPA, ETA, and entry coordinates. Display gates explicitly control the
prediction, ETA, ENTRY, CPA, heading, and uncertainty overlays.

## UI information hierarchy

The simulation primary card is now **SITE APPROACH / 據點接近預測**:

1. approaching, departing, stationary, or uncertain;
2. simulated protected-radius entry ETA;
3. current absolute site distance;
4. predicted closest distance and time;
5. protected radius;
6. current/+5/+10/+15/+30 distance forecast;
7. collapsed engineering details: speed, heading, site bearing, closing speed,
   and CV model.

The map keeps amber historical track, cyan current position, cyan dashed
prediction, purple site/radius, and adds subordinate ENTRY and CPA markers.
The fixed simulation watermark remains visible in screenshots.

## Simulation isolation and real panels

Simulation data is immutable browser data. It performs zero event,
observation, track, device-state, and database writes; sends zero fake
WebSocket events; and never enters real Dashboard event/track collections.
Live Detection, Recent Events, Node Status, System Health, Node Controls, and
the Dashboard WebSocket continue to use real staging data.

## Limitations and rollback

Constant velocity does not model acceleration, turns, localization error,
wind, or intent. The ETA is sensitive to current motion-estimation accuracy,
which has not passed the required multi-node field validation. No evacuation
threshold or alert escalation exists in this phase.

Rollback is configuration-only: set `DASHBOARD_SIMULATION_ENABLED=false` on
isolated staging and redeploy. Production must remain disabled and unchanged.
