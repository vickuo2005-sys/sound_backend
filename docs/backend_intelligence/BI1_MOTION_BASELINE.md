# BI-1 Raw Constant-Velocity Motion Baseline

## Scope

`services/tracking/motion.py` is a pure offline estimator. It has no database,
network, Alert, Dashboard, fusion, or production tracker integration. BI-1 does
not modify the existing alpha-beta prediction path.

## Algorithm

1. Parse valid measured lat/lng and `measurement_time_ms`.
2. Sort by event time; ignore later duplicates at the same event time while
   counting them.
3. Use the first point as a local tangent reference:

   ```text
   x = R cos(lat0) (lon - lon0)
   y = R (lat - lat0)
   ```

   Angles are radians and x/y are metres.
4. Fit independent least-squares lines `x(t)` and `y(t)` across all retained
   points. Their slopes are `vx` east and `vy` north.
5. Compute `speed = hypot(vx, vy)` and compass heading
   `atan2(vx, vy)`, normalized to 0–360 degrees.
6. Report residual RMSE, time gaps, uncertainty, duplicates, maximum segment
   speed, outlier diagnostic, validity, and quality.

This is a baseline, not a statistically calibrated confidence model.

## Default configurable quality thresholds

High requires at least 5 points, at least 6 s span, max gap no more than 1.75 ×
the expected 1.5 s hop, mean uncertainty at most 40 m, residual RMSE at most
30 m, no duplicates, and no diagnostic speed outlier.

Medium requires at least 3 points, at least 3 s span, max gap no more than 3 ×
the expected hop, mean uncertainty at most 100 m when provided, residual RMSE
at most 75 m, and no diagnostic speed outlier. Other estimable results are low;
fewer than two unique times are insufficient.

All values live in `MotionQualityConfig`. The wide default diagnostic speed is
200 m/s; it is not asserted to be a physical drone maximum. An outlier lowers
quality. `outlier_speed_guard_enabled=false` keeps the estimate valid for
diagnostics; enabling it marks an outlier result invalid but still does not
silently delete or smooth the point.

Backend flags remain off by default:

- `MOTION_SHADOW_ENABLED=false`
- `MOTION_OUTLIER_SPEED_GUARD_ENABLED=false`
- `MOTION_MAX_DIAGNOSTIC_SPEED_MPS=200`

## Deterministic simulator result

Run:

```text
python tools/simulate_motion_estimation.py
```

| Scenario | Expected | Estimated | Error | Quality/diagnostic |
| --- | --- | --- | --- | --- |
| Stationary | 0 m/s | 0 m/s | 0 | high |
| East | 10 m/s, 90° | 10 m/s, 90° | < 1e-8 | high |
| North | 15 m/s, 0° | 15 m/s, 0° | < 1e-8 | high |
| Southwest | 20 m/s, 225° | 20 m/s, 225° | < 1e-8 | high |
| Noisy positions | 10 m/s, 90° | 9.934 m/s, 89.615° | 0.066 m/s, 0.385° | high, 1.929 m RMSE |
| One +500 m outlier | 10 m/s, 90° | 10 m/s, 90° regression | 0 | low, max segment 343.33 m/s, outlier flagged |
| Missing middle hop | 10 m/s, 90° | 10 m/s, 90° | < 1e-8 | medium, max gap 3 s |
| Arrival E2/E3/E1 | 10 m/s, 90° | 10 m/s, 90° | < 1e-8 | medium; identical after event-time sort |
| Duplicate point | 10 m/s, 90° | 10 m/s, 90° | < 1e-8 | medium; duplicate count 1 |
| One point | unavailable | unavailable | n/a | insufficient |

The outlier happens to cancel in the symmetric regression slope. It is still
correctly exposed by segment speed and residual diagnostics; quality is not
allowed to hide it.

## Why no Kalman filter

Filtering would add model assumptions before event time, cadence, localization
uncertainty, missing measurements, and outlier distributions have field
evidence. BI-1 therefore establishes a transparent comparator first. A future
filter must beat this baseline on held-out tracks without masking starvation or
ordering failures.
