# BI-2A/B motion field validation report

Date: 2026-08-31

## Verdict

**TOOLING PASS / FIELD INCOMPLETE** (`PARTIAL PASS` for BI-2 engineering).

The capture format, Raw LS/current-tracker analyzer, event-time safeguards,
rejected raw-point telemetry, uncertainty diagnostic, and approaching/
departing shadow helpers are implemented and covered by automated tests.
Motion field accuracy cannot be evaluated: only one authorized physical
Android device is currently connected and isolated staging has zero tracks.
No synthetic or localhost result is substituted for field evidence.

BI-2C Kalman Shadow recommendation: **NO-GO** until the required multi-node
static and moving field dataset exists.

BI-3 short-horizon prediction recommendation: **NO-GO** because motion itself
has not yet been field validated.

## A-AA status

| ID | Result |
|---|---|
| A. Physical nodes | 1 connected (`23108RN04Y`); below the minimum 2 |
| B. Node positions | NOT COLLECTED for a BI-2 surveyed layout |
| C. Scenario/run count | 0 field runs; no scenario has the required 3 repeats |
| D. Static localization jitter | NOT COLLECTED |
| E. Static false speed p50/p95/max | NOT COLLECTED |
| F. Straight ground-truth speed | NOT COLLECTED |
| G. Raw LS speed MAE/RMSE/bias | NOT COLLECTED |
| H. Current Tracker speed MAE/RMSE/bias | NOT COLLECTED |
| I. Heading median/p95 error | NOT COLLECTED |
| J. Position RMSE/p50/p95/max | NOT COLLECTED |
| K. Uncertainty coverage | NOT COLLECTED; helper and output schema ready |
| L. Outlier count/impact | NOT COLLECTED; flagged raw retention ready when staging field flag is enabled |
| M. Median/p95/max gap | NOT COLLECTED |
| N. Late/duplicate discard | NOT COLLECTED |
| O. Event-time reorder | Automated E2/E3/E1 Raw LS equivalence PASS; field occurrence NOT COLLECTED |
| P. Stop -> Move -> Stop | Automated phase sanity PASS; field behavior NOT COLLECTED |
| Q. 90° turn | NOT COLLECTED |
| R. Approaching/departing | Automated shadow rules PASS; field result NOT COLLECTED |
| S. Minimum reliable speed | NOT RECOMMENDED without S0 data |
| T. Motion quality thresholds | No adjustment; field calibration missing |
| U. Telemetry counter bug | Implementation/tests completed on BI-2 Flutter branch; field recheck pending |
| V. Backend tests | PASS: 150 tests; compileall and diff check PASS (2 existing Pydantic deprecation warnings) |
| W. Flutter tests | PASS: 93 tests; `flutter analyze --no-pub` reports 0 issues; diff check PASS |
| X. Production safety | PASS: read-only check shows production SHA `5babe2bafaffbb77b48d16a5e1675f202ae7286b`; observation shadow/tracking, reorder, and DB probe remain false. Staging remains `18c5df262892abc66f555a789ca3eaf3d340121d`, motion shadow false, BI-2 telemetry absent/default-off, 0 tracks |
| Y. BI-2 verdict | **PARTIAL PASS — TOOLING PASS / FIELD INCOMPLETE** |
| Z. Kalman Shadow | **NO-GO** |
| AA. BI-3 Prediction | **NO-GO** |

## Implemented validation behavior

- Capture is fail-closed to the isolated staging hostname and emits JSON + CSV.
- Raw points include measured, filtered, predicted, event-time, localization
  method, uncertainty, node count, velocity, heading, innovation, outlier, and
  ordering diagnostics.
- In field-validation mode, motion `dt` cannot fall back to HTTP/DB/worker
  arrival time. Default production tracking semantics remain unchanged.
- Raw LS always receives explicit measured coordinates from the analyzer.
- Circular heading error handles 359° vs 1° as 2°.
- Static false-speed, position error, speed error, heading error, gap, outlier,
  uncertainty coverage, and site-relative shadow outputs are defined.
- `MOTION_FIELD_TELEMETRY_ENABLED` is default-off. When enabled only for field
  staging, rejected raw measurements are retained without updating accepted
  track state or point count.
- No Kalman, ETA, CPA, prediction, subtype, alert, cooldown, or production
  tracking behavior was added.

## Scenario comparison

No field cell below has been populated because the physical-node gate is not
met. These tables are the required Raw LS versus Current Tracker report shape;
they must be filled from retained runs rather than synthetic estimates.

### STATIC (S0)

| Metric | Raw LS | Current Tracker |
|---|---|---|
| Position jitter RMS / error spread | NOT COLLECTED | NOT COLLECTED |
| False speed p50 / p95 / max | NOT COLLECTED | NOT COLLECTED |
| Heading near zero speed | NOT COLLECTED | NOT COLLECTED |

### STRAIGHT (S1 east/west and S2 north/south)

| Metric | Raw LS | Current Tracker |
|---|---|---|
| Position RMSE / p50 / p95 / max | NOT COLLECTED | NOT COLLECTED |
| Speed MAE / RMSE / bias / relative error | NOT COLLECTED | NOT COLLECTED |
| Heading median / p95 circular error | NOT COLLECTED | NOT COLLECTED |

### DIAGONAL (S3)

| Metric | Raw LS | Current Tracker |
|---|---|---|
| Position and speed error | NOT COLLECTED | NOT COLLECTED |
| Diagonal heading error | NOT COLLECTED | NOT COLLECTED |

### STOP-MOVE-STOP (S4)

| Metric | Raw LS | Current Tracker |
|---|---|---|
| Static -> moving response | NOT COLLECTED | NOT COLLECTED |
| Moving -> static response | NOT COLLECTED | NOT COLLECTED |

### TURN (S5 90 degrees)

| Metric | Raw LS | Current Tracker |
|---|---|---|
| Turn error and recovery | NOT COLLECTED | NOT COLLECTED |
| Outlier sensitivity | NOT COLLECTED | NOT COLLECTED |

## Field execution gate

Do not deploy the BI-2 branch or start accuracy runs until:

1. at least two authorized physical Android nodes are connected;
2. their fixed IDs and surveyed coordinates are recorded;
3. the route markers and ground-truth files are ready;
4. the staging-only branch and flags pass review;
5. S0 static and at least one straight scenario can each be repeated three
   times without using production resources.
