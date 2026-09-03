# Dashboard simulation site prediction

## Scope and safety boundary

V2.4.2 is a deterministic, presentation-only staging simulation. It is
**SIMULATION / 模擬展示 — NOT FIELD VALIDATED** and is not a production
tracker, alert, threat score, or claim about a real aircraft or site.

**Simulation Demo Ready does not mean Motion Field Validated.** No field
validation is performed or implied by this layer.

The processing order is intentionally one-way:

```text
historical simulation positions
  -> motion-state estimation
  -> trajectory prediction
  -> predicted positions
  -> fixed-site assessment
  -> distance / trend / CPA / protected-radius ETA
```

Site coordinates are absent from motion estimation and projection. Moving the
site can change distances, trend, CPA, and ETA, but must produce byte-for-byte
identical predicted latitude/longitude values for the same history and current
position.

## Source separation

- `static/dashboard_simulation_prediction.js` contains pure deterministic
  math and the `computeSimulationPredictionTick(input)` contract.
- `static/dashboard_simulation_scenarios.js` contains static demo scenarios
  and the arbitrary fixed `DEMO SITE ALPHA` definition.
- `templates/dashboard_v2_4.html` owns playback, Google Maps objects, and
  presentation.

The prediction module has no clock, random number, network, browser storage,
DOM, Google Maps, or backend dependency. It uses no production event, track,
device, WebSocket, or database state.

## Coordinate and motion conventions

- Earth radius: `6,371,000 m`.
- Heading: `0° = north`, `90° = east`, increasing clockwise.
- Speed and velocity: metres per second.
- Local tangent plane: east/north metres about the current reference point.
- Geographic distance: Haversine with normalized antimeridian longitude,
  clamped floating-point term, and `atan2`.

Measurements are sorted by simulation/event time and duplicate timestamps are
collapsed. Invalid time or position, fewer than three usable points, less than
two seconds of history, or a gap greater than three seconds yields
`DATA_INSUFFICIENT` with explicit reason codes.

Motion uses the most recent five seconds of 1 Hz history. Per-segment east and
north velocities are exponentially weighted toward the newest measurement
with `tau = 2 s`. Headings are never directly averaged. Heading samples are
unwrapped across `359° -> 0°` before turn-rate diagnostics.

The active projection model is constant velocity (CV). Every `+5`, `+10`,
`+15`, and `+30 s` point is projected from the same current state. A
constant-turn helper exists for deterministic testing and future evaluation,
but turn correction is not active in this release.

CV is a short-horizon baseline for stable motion; it does not assert that a
UAV will fly in a straight line. During turns or acceleration, extrapolation
error generally grows with horizon. Every displayed future point is a
current-motion extrapolation, not future truth.

## Fixed site assessment

`DEMO SITE ALPHA` is an arbitrary stationary coordinate with a `100 m`
protected radius. The map renders one fixed site marker and one fixed radius
circle across playback and scenario changes.

For current position `p`, site vector `r`, and velocity `v`, radial closing
speed is the projection of `v` onto the current unit vector toward the site.
Positive values close the range; negative values open it.

Trend classification combines the five-second distance change and closing
speed:

- speed `< 0.5 m/s`: `STATIONARY`;
- `d(+5) - d(now) <= -0.5 m` and closing speed `>= 0.1 m/s`:
  `APPROACHING`;
- `d(+5) - d(now) >= 0.5 m` and closing speed `<= -0.1 m/s`:
  `DEPARTING`;
- otherwise: `UNCERTAIN`.

CPA is the analytic CV minimum of `|p + vt|`, with evaluation time clamped to
`0..300 s`. Both CPA distance and CPA time are displayed.

ETA is not `distance / speed`. It is the first non-negative root of the line /
protected-circle intersection:

```text
|p + vt|² = radius²
```

The result distinguishes `AT_SITE`, `LOW_SPEED`, `NO_SITE_INTERSECTION`, and
`MOVING_AWAY_OR_PAST_INTERSECTION`. Search is capped at 300 seconds. The UI
shows a simulated ETA only when the prediction is valid, movement is
approaching, closing speed passes its gate, and a future radius intersection
exists. Otherwise it shows an em dash and the reason.

## Output contract

Every result is tagged `simulation: true` and returns:

- `status` and `status_reasons`;
- `model`;
- `current` position, speed, heading, heading reliability, and turn-rate
  diagnostic;
- `site` identity, coordinate, radius, current distance, and bearing;
- `motion` trend, radial closing speed, and heading-to-site error;
- `predictions` with horizon, coordinate, and distance to site;
- `site_metrics` with CPA distance/time, simulated ETA, and ETA reason;
- `display` quality gates for prediction, heading, ETA, and uncertainty.

Uncertainty is a conservative visibility gate only. If configured position
uncertainty exceeds recent travelled path length, the result is
`DATA_INSUFFICIENT`. The demo does not label its uncertainty as calibrated or
as a 95% confidence interval.

## Demo scenarios

All scenarios use 1 Hz static history, start 1,000 m from the same fixed site,
and move at 10 m/s:

1. `DIRECT APPROACH`: heads toward the site; expected CPA is approximately
   zero and protected-radius ETA is approximately 90 seconds at the initial
   state.
2. `PARALLEL FLY-BY`: passes with approximately 800 m CPA; no protected-radius
   intersection and no ETA.
3. `DEPARTING`: opens the range with negative closing speed; no ETA.

## Performance and validation

Playback position and map-marker movement use `requestAnimationFrame`.
Haversine, motion estimation, prediction, CPA, and ETA run at no more than
5 Hz. Text/control DOM updates run at no more than 8 Hz. No site-assessment
math runs at animation-frame frequency.

Unit coverage includes cardinal headings, same-point/equator/antimeridian
Haversine cases, deterministic replay, site-path isolation, direct approach,
parallel fly-by, departing, already inside radius, tangent intersection, low
speed, heading wrap, duplicates, invalid data, history gaps, and uncertainty
gating.

## Rollback

Set `DASHBOARD_SIMULATION_ENABLED=false` on isolated staging and redeploy. The
entry point, scenario payload, prediction module, and all simulation overlays
are omitted from the rendered page. No database cleanup is required. This
feature must remain disabled in production.
