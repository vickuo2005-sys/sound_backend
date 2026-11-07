# BI-2 tracking schema and motion architecture audit

Date: 2026-08-31

Scope: Backend BI-2A/B validation branch only. This audit describes the code
that existed at the BI-1.5 base plus explicitly identified validation fixes.

## Data path

```text
event / observation event-time
  -> multi-node fusion or timestamp localization
  -> tracking measurement
  -> optional post-ingest reorder buffer
  -> alpha-beta current tracker
  -> target_tracks + target_track_points
  -> offline Raw LS field analyzer
```

The Raw LS implementation in `services/tracking/motion.py` is an offline/shadow
baseline. It is not the algorithm that currently writes the live track state.
The live tracker uses the alpha-beta update in
`services/tracking/tracking_service.py`.

## Required audit answers

### A. Where is a Track Point created?

`main.process_tracking_measurement()` validates and associates a measurement,
then calls `update_track_from_measurement()`. Accepted state is written by
`main.save_track_point()` into `target_tracks` and `target_track_points`.

Before BI-2, rejected outliers and late/duplicate measurements returned before
the raw point insert. BI-2 adds a default-off
`MOTION_FIELD_TELEMETRY_ENABLED` path that writes a rejected diagnostic point
without updating track state or accepted `point_count`.

### B. Which position should the baseline use?

- Raw LS: `measured_lat` / `measured_lng` only.
- Current Tracker comparison: `filtered_lat` / `filtered_lng` and its stored
  velocity/speed/heading.
- `predicted_lat` / `predicted_lng`: diagnostics only; never treated as a raw
  measurement or ground truth.

The generic BI-1 `estimate_constant_velocity()` parser prioritizes measured
coordinates but can fall back to filtered coordinates for compatibility. The
BI-2 analyzer constructs its Raw LS inputs explicitly from measured fields so
that a missing raw position cannot be hidden by that fallback.

### C. What is the canonical timestamp?

`target_track_points.measurement_time_ms`, sourced from the localization or
region measurement's event-time. It is not `created_at` or DB insertion time.

Audit finding: `update_track_from_measurement()` can fall back to the current
wall clock when `event_time_ms` is missing, and event-group tracking can fall
back to `updated_at` / current time. The default runtime behavior is retained
to avoid a production semantic change. When the default-off staging-only
`MOTION_FIELD_TELEMETRY_ENABLED` validation mode is enabled, BI-2 rejects a
missing canonical event-time instead. The offline analyzer always requires
event-time. `created_at` remains exportable only for arrival-order diagnostics.

### D. How does the current tracker calculate velocity?

The current tracker predicts the previous filtered position with its stored
east/north velocity, calculates the measurement residual, then applies an
alpha-beta update:

- filtered position = prediction + `alpha * residual`;
- velocity = previous velocity + `beta * residual / event_time_dt`;
- speed = `hypot(vx, vy)`;
- heading = `atan2(east_velocity, north_velocity)` in degrees.

Heading is `0° North`, `90° East`, `180° South`, `270° West`; below 0.05 m/s it
is null. The default physical speed limit is 80 m/s. This is not a Kalman
filter.

Raw LS independently converts measured latitude/longitude to local tangent
meters, orders by event-time, deduplicates equal event times, and fits `x(t)`
and `y(t)` by least squares.

### E. Which localization methods exist?

Observed code values include:

- `multi_node_region` for coarse segment/polygon regions;
- `weighted_centroid`;
- `weighted_centroid_fallback`;
- `tdoa_timestamp` in the legacy target-estimate path;
- `timestamp_tdoa` in the newer timestamp-localization service.

A single-node region is represented as `single_node`, but it is not accepted
to create a region track.

### F. How is uncertainty produced?

- Coarse fusion defaults: 2 nodes = 100 m, 3 nodes = 60 m, 4+ nodes = 40 m.
- Timestamp TDOA: a diagnostic radius based on residual, average sync RTT,
  and geometry, with a minimum of 20 m.
- Timestamp fallback: at least 80 m and increases with node spread.

The current tracker consumes the radius for its innovation gate but does not
establish probabilistic calibration. BI-2 therefore reports only
`actual error <= uncertainty radius` coverage diagnostics, never a 95%
confidence claim.

### G. Where is source node count stored?

Localization/event-group payloads expose `node_count` or
`reporting_node_count`. BI-2 copies it, the device IDs, and localization method
into `target_track_points.diagnostics_json`. The capture tool exports it as
`source_node_count`.

### H. Minimum nodes for a Track

Region tracking requires `TRACK_MIN_REGION_NODES`, default 2. Timestamp TDOA
requires at least 3 eligible nodes; a fallback may be produced depending on
the localization policy and confidence gate.

### I. Single-node localization

A single reporting node only identifies the node position/coarse point. The
region tracker explicitly rejects `single_node`; it is not source
localization and cannot validate motion accuracy.

### J. Real cadence ceiling

The Android inference hop is nominally 1.5 s, so observation-driven tracking
cannot exceed one new measurement per hop per source stream. Event cooldown,
fusion grouping, missing observations, confidence gating, worker ordering, and
historical suppression can make the real cadence much slower. Field tooling
therefore measures median/p95/max gaps rather than assuming 1.5 s.

### K. Historical replay

Yes. Observation replay policy suppresses historical observations from live
tracking while retaining their upload evidence. A delayed queue drain must not
be counted as a live motion point.

## Ordering audit

- Raw LS sorts by event-time and its automated E2/E3/E1 result equals normal
  E1/E2/E3.
- Direct live tracking rejects a measurement whose event-time is not greater
  than the associated track's last event-time.
- The optional post-ingest reorder buffer is default-off. A 300–500 ms window
  handles mild completion disorder but cannot recover E1 arriving after E2 and
  E3 when event timestamps are one second apart; the existing test records
  that limit.
- The capture format stores both event-time order and `created_at` arrival
  order. Motion `dt` always uses event-time.

## Schema coverage

Existing `target_track_points` columns already preserve measured, filtered,
predicted, velocity, speed, heading, uncertainty, confidence, innovation,
outlier state, state/covariance JSON, diagnostics, and `created_at`. No DB
migration is required for BI-2 tooling.

The capture export adds run metadata, localization method, source node count,
arrival/event ordering indexes, sequence/observation identity when available,
and raw diagnostics. Secrets and credentials are rejected by the capture tool.

## Current limitations that field data must answer

1. Coarse multi-node regions may describe node geometry rather than the source.
2. Alert cooldown can starve the event-driven track cadence.
3. TDOA uncertainty is not calibrated against field position error.
4. Alpha-beta current tracking may turn localization jumps into false motion.
5. A 300–500 ms reorder window does not solve arbitrarily late event-time data.
6. One physical node cannot produce a valid motion-accuracy dataset.
