# Dashboard simulation mode

## Purpose and boundary

V2.4.2 adds a presentation-only motion overlay to the V2.4 Operational
Dashboard. It exists so a staging demo can explain track history, a current
position, and a simple future-path visualization when field tracking evidence
is unavailable.

This mode is **SIMULATION / 模擬展示 — NOT FIELD VALIDATED**. It is not a
tracking result, alert, localization measurement, or estimate of a real
aircraft. It must not be used as field evidence.

## Feature flag and environment

`DASHBOARD_SIMULATION_ENABLED=false` is the code default. When false, the
Dashboard does not render the simulation entry button, control panel, or
scenario payload. Only the isolated Render staging service may set it to
`true`. Production must keep it false.

`GET /runtime-status` exposes `dashboard_simulation_enabled` so the deployed
configuration can be audited. The flag is additive and does not change the
Dashboard V2 switch or experimental motion switch.

## Scenario contract

The static source is `static/dashboard_simulation_scenarios.js`. Scenario
`approach_site_demo_v1` lasts 75 seconds, includes a direction change, and uses
arbitrary demo coordinates near the Dashboard's default map center. It does
not identify a real site, device, flight, or person. The scenario, site, every
point, every interpolation result, every prediction, and the public test
snapshot carry `simulation: true`.

The overlay uses:

- orange for simulated history;
- cyan for the simulated current position;
- a cyan dashed line and markers for +5, +10, +15, and +30 second predictions;
- purple for the arbitrary demo site;
- a cyan uncertainty circle for presentation only.

Prediction is straight-line constant velocity derived from the active static
scenario segment. It is deliberately not Kalman filtering, production
tracking, threat prediction, or a validated ETA. The Motion card labels all
derived values as simulated.

## Runtime behavior

The state machine is `inactive → ready → playing ↔ paused → completed`.
Opening the mode, including with `?simulation=1`, stops at `ready` and never
autoplays. Controls provide play/pause, restart, exit, 0.5×/1×/2× speed, seek,
and optional follow-target map panning. Animation uses
`requestAnimationFrame`; position and metrics are interpolated continuously.
Google Maps objects are created once and updated in place. Map geometry follows
the animation frame, while text/control DOM updates are limited to 8 Hz. Follow
Target pans only when the marker enters the outer 18% of the visible bounds;
it never calls `fitBounds` per frame.

Exit cancels the animation frame, removes every simulation-only Google Maps
object, restores the normal operational overlay opacity, and does not reload
the page.

## Isolation guarantees

Simulation state is separate from the existing Dashboard `state.events`,
`state.tracks`, `state.devices`, groups, command lifecycle, and WebSocket
connection. Simulation code does not call `fetch`, create a WebSocket, write
browser storage, invoke an ingest endpoint, or write a database. Real Live
Detection, Recent Events, Node Status, Node Controls, and `/ws/dashboard`
continue updating while the overlay is active.

No backend event schema, tracking semantics, database schema, migration,
Flutter code, or production environment is changed by this mode.

## Staging validation

1. Confirm the deployed SHA and `dashboard_simulation_enabled=true` in
   `/runtime-status` on the isolated staging host.
2. Open `/dashboard?simulation=1` and confirm state is READY with no movement.
3. Exercise play, pause, resume, seek, both non-default speeds, restart,
   follow-target off/on, completion, replay, and exit.
4. Confirm history grows; current position, prediction, speed, heading,
   distance, relative motion, closest distance, and ETA change.
5. While playing, confirm the real WebSocket stays connected, Node Status and
   Node Controls remain usable, and no simulated item appears in Live
   Detection or Recent Events.
6. Repeat at 1366×768 and 1920×1080. Check for horizontal overflow and browser
   console errors.

## Rollback

Set `DASHBOARD_SIMULATION_ENABLED=false` on isolated staging and redeploy. The
button, scenario, controls, and overlay disappear. No data cleanup or database
rollback is required because the feature performs no writes. Production is
not part of this rollout or rollback path.
