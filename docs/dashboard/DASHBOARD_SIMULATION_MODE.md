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

The static source is `static/dashboard_simulation_scenarios.js`. Three 90-second
scenarios cover direct approach, parallel fly-by, and departing motion around
the arbitrary fixed `DEMO SITE ALPHA`. They do not identify a real site,
device, flight, or person. The scenario, site, every point, every interpolation
result, every prediction, and the public test snapshot carry `simulation:
true`.

The overlay uses:

- orange for simulated history;
- cyan for the simulated current position;
- a cyan dashed line and markers for +5, +10, +15, and +30 second predictions;
- purple for the arbitrary fixed demo site and its 100 m protected radius;
- a cyan uncertainty circle for presentation only.

Prediction is straight-line constant velocity derived only from recent static
history. The fixed site is assessed after projection and cannot attract or
bias the predicted trajectory. It is deliberately not Kalman filtering,
production tracking, threat prediction, or a validated ETA. See
`DASHBOARD_SIMULATION_PREDICTION.md` for formulas, gates, and reason codes.

## Runtime behavior

The state machine is `inactive → ready → playing ↔ paused → completed`.
Opening the mode, including with `?simulation=1`, stops at `ready` and never
autoplays. Controls provide play/pause, restart, exit, 0.5×/1×/2× speed, seek,
and optional follow-target map panning. Animation uses
`requestAnimationFrame`; position is interpolated continuously.
Google Maps objects are created once and updated in place. Map geometry follows
the animation frame, prediction/site math is limited to 5 Hz, and text/control
DOM updates are limited to 8 Hz. Follow
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

## Interactive simulation lab

The staging workspace lets an operator add drones one at a time. Adding a drone
immediately enters map picking for that drone's start point; its route can then
be edited through the drone list. Clearing targets resets the selected target,
and the same add-and-pick action starts a fresh drone without reloading the page.
One configured drone can run by itself; any number of configured drones start
on the same simulation clock.

Clearing targets or the whole scene resets creation fields to Drone, 25 m/s,
and 90 degrees. Validation feedback appears directly below the add button and
focuses invalid inputs. All supported sound types appear in the editable target
list; the add button names the selected type. Creating or editing a target
pauses playback and exits history replay. Route edits stay attached to the
chosen target even if warning selection changes.

Node controls are grouped in a collapsible section. The placed-node list has a
second, collapsed-by-default disclosure so large layouts do not lengthen the
tool column until an operator needs per-node actions. Up to 100 simulation nodes
can be placed; the expanded list scrolls within 420 pixels. One shared detection radius
applies to every existing node and is inherited by newly placed nodes. At least
two online, enabled nodes must detect a drone before the lab emits a system
position estimate. Two reporting nodes form a line region; three or more form a
convex region.

Simulation and operational maps reuse the V2.2 node language. Fixed nodes use
one consistent circle symbol with a white fill and dark outline. A node that
currently participates in the system estimate
turns orange and pulses; its detection range also pulses. Two participating
nodes draw an orange connection, while three or more draw an orange convex
region. The animation follows the estimated path only, so the hidden simulation
truth path cannot trigger an operational warning, approach state, or ETA.
Configured offline nodes remain on the map at their fixed positions. They use a
solid slate fill, light outline and an `×` suffix instead of the white online
style, and never receive the orange reporting pulse while offline.

The purple path represents simulated ground truth and exists only for visual
comparison. The blue path represents the system estimate. Warning entry,
approach/departure state, distance to the site, protected-zone ETA, and site ETA
are calculated exclusively from the blue estimated position and its timestamped
history. Position and velocity come from the same finite regression trajectory.
The display ETA smooths the absolute entry timestamp and briefly holds an
unstable frame; CPA tolerance comes from trajectory residuals. Ground truth is
recorded only for per-frame ETA evaluation, never estimator input, and never
triggers a warning. See `SIMULATION_LAB_ETA_STABILITY.md` for the algorithm,
constants, reason codes, and deterministic tests. The sound-only/position-
incomplete condition remains available as a quick demonstration preset rather
than a manual event-creation control.

## Staging validation

1. Confirm the deployed SHA and `dashboard_simulation_enabled=true` in
   `/runtime-status` on the isolated staging host.
2. Open `/dashboard?simulation=1` and confirm state is READY with no movement.
3. Exercise play, pause, resume, seek, both non-default speeds, restart,
   follow-target off/on, completion, replay, and exit.
4. Exercise all three scenarios. Confirm history grows and current position,
   predictions, speed, heading, current/future site distances, trend, closing
   speed, CPA, and gated ETA/reason change while the site and radius stay fixed.
5. While playing, confirm the real WebSocket stays connected, Node Status and
   Node Controls remain usable, and no simulated item appears in Live
   Detection or Recent Events.
6. Repeat at 1024×768, 1366×768, and 1920×1080. Check for horizontal overflow
   and browser console errors.

## Rollback

Set `DASHBOARD_SIMULATION_ENABLED=false` on isolated staging and redeploy. The
button, scenario, controls, and overlay disappear. No data cleanup or database
rollback is required because the feature performs no writes. Production is
not part of this rollout or rollback path.
