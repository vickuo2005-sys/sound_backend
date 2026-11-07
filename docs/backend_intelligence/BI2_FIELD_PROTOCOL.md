# BI-2 controlled moving acoustic source field protocol

This protocol validates localization-to-motion behavior. A portable speaker
playing the known Drone test audio is a **controlled moving acoustic source**;
it is not a real drone flight and does not validate classification accuracy.

## Safety and minimum equipment

- Use an open, safe, measurable area.
- Fix every Android node in place; nodes must not follow the speaker.
- Minimum for a field-accuracy verdict: two physical Android nodes. Three or
  four are preferred, and timestamp TDOA normally needs three eligible nodes.
- Record fixed device IDs and surveyed node coordinates in a local node-layout
  JSON file.
- Mark the ground-truth route independently from Backend estimates.

With only one node, only tooling, export, and non-accuracy pipeline sanity are
permitted. The verdict must remain `FIELD INCOMPLETE`.

## Ground-truth files

Keep site-specific coordinates in local run metadata. Do not include tokens or
credentials.

Linear/static example:

```json
{
  "route_start": {"lat": 0.0, "lng": 0.0},
  "route_end": {"lat": 0.0, "lng": 0.0},
  "route_length_m": 40.0,
  "start_time": "2026-01-01T00:00:00Z",
  "end_time": "2026-01-01T00:00:40Z",
  "motion_start_time": "2026-01-01T00:00:10Z",
  "motion_end_time": "2026-01-01T00:00:30Z",
  "ground_truth_speed_mps": 2.0,
  "validation_site": {"lat": 0.0, "lng": 0.0},
  "analysis": {
    "expected_interval_s": 1.5,
    "minimum_reliable_motion_speed_mps": null,
    "minimum_closing_speed_mps": null
  }
}
```

Replace all zero coordinates with measured local values before a run. Leave
the reliable-speed thresholds null during the first static dataset; derive a
recommendation from static false-speed evidence instead of inventing one.

For a 90-degree turn, provide event-time waypoints:

```json
{
  "waypoints": [
    {"time": "2026-01-01T00:00:00Z", "lat": 0.0, "lng": 0.0},
    {"time": "2026-01-01T00:00:20Z", "lat": 0.0, "lng": 0.0},
    {"time": "2026-01-01T00:00:40Z", "lat": 0.0, "lng": 0.0}
  ],
  "analysis": {"expected_interval_s": 1.5}
}
```

Node-layout example:

```json
{
  "survey_method": "measured_fixed_markers",
  "nodes": [
    {"device_id": "A01", "lat": 0.0, "lng": 0.0},
    {"device_id": "A02", "lat": 0.0, "lng": 0.0}
  ]
}
```

## Scenarios and repeats

Keep every run, including failures. Minimum three runs per scenario; five if
time permits.

| Scenario | Route | Minimum duration/purpose |
|---|---|---|
| S0_static | Speaker fixed | 60 s; jitter and false speed |
| S1_east_west | 20–50 m straight | Ground-truth speed and E/W heading |
| S2_north_south | 20–50 m straight | N/S heading |
| S3_diagonal | 30–50 m straight | One diagonal direction |
| S4_stop_move_stop | 10–20 s stop, move, 10–20 s stop | 0 -> moving -> 0 response |
| S5_turn_90 | 20 m leg, 90° turn, 20 m leg | Quantify constant-velocity failure |

Record route markers, route length, video, exact start/end timestamps, audio
asset identity, weather/background notes, failed nodes, and any network gap.

## Staging preparation

1. Use only `sound-backend-staging.onrender.com` and the isolated staging DB.
2. Deploy a reviewed BI-2 feature-branch commit only after tests pass.
3. Keep `MOTION_SHADOW_ENABLED=false` when using only the offline analyzer.
4. Enable `MOTION_FIELD_TELEMETRY_ENABLED=true` only in staging to retain
   rejected raw diagnostic points. Production remains false/absent.
5. Confirm at least two authorized devices in `adb devices -l`.
6. Confirm each fixed node ID/location before starting the speaker.

## Capture command

Use ISO-8601 UTC times and a track ID when more than one track overlaps:

```powershell
python tools/capture_motion_field_run.py `
  --base-url https://sound-backend-staging.onrender.com `
  --run-id static-01 `
  --scenario S0_static `
  --start-time 2026-01-01T00:00:00Z `
  --end-time 2026-01-01T00:01:00Z `
  --track-id TRACK_UUID `
  --node-id A01 --node-id A02 `
  --audio-asset known-drone-test-audio.wav `
  --ground-truth-file config/bi2_ground_truth.local.json `
  --node-layout-file config/bi2_node_layout.local.json
```

The capture tool is fail-closed to the isolated staging hostname and rejects
secret-like metadata keys. Each run produces JSON and CSV with raw measured,
filtered, predicted, event-time, motion, uncertainty, innovation, outlier, node
count, and ordering fields.

## Analyze command

```powershell
python tools/analyze_motion_field.py `
  docs/backend_intelligence/validation/bi2/run_S0_static_static-01_raw.json `
  --aggregate-output docs/backend_intelligence/validation/bi2/aggregate.json
```

The analyzer reports raw and current-tracker results side by side. It never
deletes raw points and reports both with-outlier and diagnostic-excluded Raw LS
results. Heading trust remains disabled until the static dataset yields a
minimum reliable speed recommendation.

## Run acceptance checklist

- Fixed node count and surveyed positions recorded.
- Ground truth came from route measurement/video, never Backend estimates.
- JSON and CSV point counts match.
- Raw measured coordinates exist; filtered values did not replace them.
- Event-time is monotonic after sorting; arrival reorder remains recorded.
- Rejected/outlier points remain in raw telemetry when the field flag is on.
- Median/p95/max gap and late/duplicate counts are reported.
- Raw LS and Current Tracker metrics are both present.
- No run is removed because its result is unattractive.
- No production service, DB, flag, or Dashboard is changed.

## Observation retry telemetry semantics

These counters describe process ownership; they do not change queue delivery:

- `raw_created_this_process`: valid raw target observations created by the
  currently running app process.
- `persisted_from_previous_process_total` and
  `observation_recovered_after_restart_total`: persisted active rows found with
  a different process session during restart recovery.
- `uploaded_this_process`: all successful uploads performed by this process,
  including old persisted rows.
- `uploaded_current_process_observations`: successful uploads whose observation
  was created by this same process.
- `recovered_uploaded_this_process`: successful uploads created by an older
  process and drained by this process.
- `pending`: the current durable retry-queue depth.
- `raw_to_upload_loss_count` is
  `max(0, raw_created_this_process - uploaded_current_process_observations)`.
  Recovered old rows therefore cannot make the loss negative or inflate the
  current process delivery percentage above 100%.
