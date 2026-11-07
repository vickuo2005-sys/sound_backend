# BI-1.5 staging classification end-to-end validation

Date: 2026-08-31 (Asia/Taipei)

## Verdict

**PARTIAL PASS.** The versioned classification contract completed a real
Android-to-staging round-trip for the model output `Drone`, including normal
network delivery, offline retry, App-process restart recovery, PostgreSQL
persistence through the alert event path, and a real Dashboard WebSocket
message. Backward compatibility, server normalization, refresh safety,
duplicate replay, malformed-input safety, and automated regressions passed.

This is not a five-class accuracy result. The supplied speaker playback was
described as airplane audio, but the model emitted only `Drone` and
`Electric_saw`. No trustworthy `Airplane`, `Car`, or `Rainfall` inference was
observed. `Electric_saw` was observed on Android but, under the existing target
admission semantics, did not enter the target observation/event path. The
required 50-event OFF/ON latency and backend-performance comparisons were not
run, so they remain **INCONCLUSIVE**. Dashboard WebSocket JSON passed; browser
render was not measured. Staging audio upload is blocked because staging-only
GCS is intentionally not configured.

BI-2 recommendation: **CONDITIONAL GO** for design or isolated staging work
only. Do not enable production or claim a full BI-1.5 PASS until a trustworthy
Airplane round-trip, one non-target round-trip, the 50/50 latency/performance
comparison, and visual Dashboard validation are complete.

## A-AF result summary

| ID | Result |
|---|---|
| A. Flutter HEAD | `5c2b951506d0131721ccd21225f4d802ea077fbd` |
| B. Backend local HEAD | `18c5df262892abc66f555a789ca3eaf3d340121d` |
| C. Backend staging deployed HEAD | `18c5df262892abc66f555a789ca3eaf3d340121d` |
| D. APK SHA-256 | `8f6a32ffac995e434ada5b7a3ca26deb5e5feb464a8c02f78b1d88ffe8c5a53e` (186,369,035 bytes) |
| E. Staging migration | PASS; nine nullable additive columns and two partial indexes exist only in isolated staging |
| F. Staging flags | classification enabled/persistence/WebSocket `true`; motion flags `false`; tracking reorder and DB probe `false` |
| G. Field-validated classes | `Drone` transport round-trip; `Electric_saw` Android inference contract only |
| H. Sample count | 51 complete Android inferences: Drone 11, Electric_saw 40, Airplane 0, Car 0, Rainfall 0; all 51 contract-valid |
| I. Android example | `classification.v1`, model `v1_1_0_flower_drone_audio` 1.1.0, Drone 0.6086772680, aircraft probability 0.6088918836, five scores present |
| J. Observation queue | PASS; normal 2/2 HTTP 202, long-offline 7/7 drained, restart 6/6 drained |
| K. Offline retry equality | PASS for directly joined persisted sample: ID, session, sequence, observed/event time, and classification JSON unchanged; 7/7 delivered |
| L. App restart equality | PASS for directly joined persisted sample; new PID restored six rows and final queue was zero |
| M. DB round-trip | PASS for classified `/events` record; Flutter = normalized backend = PostgreSQL = WebSocket for the real Drone event |
| N. Legacy refresh | PASS; legacy update of the same event did not null existing classification |
| O. WebSocket | PASS for real `event_trigger` JSON with legacy fields plus full classification; visual browser render NOT VALIDATED |
| P. Legacy alert | PARTIAL PASS; two live Drone observations yielded one alert under unchanged 10 s cooldown; Airplane/non-target field cases NOT VALIDATED |
| Q. Classification OFF latency | INCONCLUSIVE; count 0, p50/p95/p99/max null |
| R. Classification ON latency | INCONCLUSIVE; one diagnostic joined event only, below the required 50; distribution fields null |
| S. Measurable latency regression | INCONCLUSIVE; no legal matched OFF/ON population |
| T. Payload size | Controlled JSON: observation 737 -> 1,095 bytes (+358, +48.58%); event 175 -> 526 bytes (+351, +200.57%) |
| U. DB/ingest overhead | INCONCLUSIVE; one ON diagnostic had db 540.38 ms, ingest 543.15 ms, non-DB 2.77 ms; no OFF population |
| V. Duplicate replay | PASS in one runtime: flags `[false,true,true,true,true]`; one logical observation and no extra tracking measurement |
| W. Backend restart duplicate | NOT VALIDATED; in-memory tombstone durability was not claimed |
| X. Tracking non-regression | PARTIAL/INCONCLUSIVE comparison; ON sanity was 2 accepted -> 2 measurements -> 2 points, zero late/duplicate discard; no matched OFF segment |
| Y. Flutter tests | PASS, 91/91 |
| Z. Backend tests | PASS, 138/138; two pre-existing Pydantic deprecation warnings |
| AA. Flutter analyze | PASS, 0 issues |
| AB. Diff check | PASS in both repositories |
| AC. Production flags | Production build remains `5babe2b`; observation shadow/tracking, reorder, and DB probe report false. BI-1 classification/motion keys are absent from that older runtime and therefore not active. Production was not changed. |
| AD. BI-1.5 verdict | **PARTIAL PASS** |
| AE. Missing evidence | Trustworthy Airplane, Car, and Rainfall samples; non-target backend round-trip; 50 OFF + 50 ON latency/performance; visual Dashboard render; staging-only GCS audio path; optional backend-restart replay |
| AF. BI-2 | **CONDITIONAL GO**, isolated/non-production work only, subject to the missing gates above |

## Runtime and isolation

- Staging service: `sound-backend-staging.onrender.com`, Render service
  `srv-da6kdn61egvs7392r92g`, validation branch
  `validate/v2-4-bi1-5-classification-staging`.
- Staging Supabase project ref: `reamgpuvjfvmsouipvom`.
- Production Supabase project ref: `zlwunuycbcycpbongtxw`.
- The staging APK is package `com.example.sound_detector_clean.staging`,
  version `1.0.2-staging`, installed on one authorized physical Android device.
- Staging has no GCS bucket/service-account configuration. A bounded audio
  attempt returned HTTP 500 with `GCS_BUCKET_NAME is not configured`; no
  production bucket was reused.
- No production deploy, migration, payload, flag change, or load test occurred.

## Android inference evidence

Complete bounded Base64 telemetry was decoded; truncated samples were not
accepted. Across the three usable field logs there were 51 complete inferences:

| Log | Drone | Electric_saw | Total | Contract-valid |
|---|---:|---:|---:|---:|
| Offline probe | 3 | 5 | 8 | 8 |
| Network-on segment | 2 | 21 | 23 | 23 |
| App-restart offline segment | 6 | 14 | 20 | 20 |
| Total | 11 | 40 | 51 | 51 |

For every accepted sample, all five canonical score keys existed, every score
was finite, top label equalled the maximum score, confidence equalled that
score, aircraft probability equalled `Airplane + Drone`, and drone subtype was
null. The telemetry contains one inference record per 1.5 s window; retry logs
carry the queued classification and do not show a second inference for the
same queued observation.

The playback source is not a reliable per-class validation asset. It must not
be used to infer Airplane accuracy merely because the user described it as an
airplane recording.

## Queue and restart evidence

Normal network:

- Two live target observations, sequences 8 and 9, both returned HTTP 202 and
  left queue depth zero.
- Backend counters for that bounded segment advanced by two unique, live,
  tracking-eligible observations; tracking produced two measurements and two
  points with zero late or duplicate discard.

Offline retry:

- Seven target observations accumulated while Wi-Fi was unavailable.
- Recovery produced seven HTTP 202 responses and queue depth 7 -> 0, with no
  expired, overflow, or permanent-failure rows.
- Directly joined sequence 1 retained the same observation ID, process session,
  sequence, observed time, event time, and exact classification JSON. The
  classification SHA-256 before and after retry was
  `68057321eed53a32ba98ab0bf9bb179dddc9240dc3cad9ae2d7991fd440e00d3`.
- The long delay made these historical replay rows; their intentional tracking
  suppression is not a delivery loss.

App restart:

- Wi-Fi was disabled and six target rows accumulated. The App was force-stopped
  and relaunched with a different PID while still offline.
- On the new process, queue initialization showed depth six. The directly
  joined sequence 10 retained its original observation/session/sequence/time
  identity and exact classification JSON; both sides had SHA-256
  `e362d3065b70b420b75a7c3365dd37b75e6ff6324fecdeeeba34f72dd38ff8d7`.
- After Wi-Fi returned, all six rows received HTTP 202 and queue depth became
  zero. Backend saw six unique historical replays and suppressed all six from
  live tracking as designed.
- Diagnostic caveat: the restored queue was functionally proven, but the
  session-local `observation_recovered_after_restart_total` counter remained
  zero and `raw_to_upload_loss_count` became negative while old rows drained.
  Those counters need a later telemetry-semantics fix; they were not used as
  proof of persistence.

## Real event, database, and WebSocket join

Real event `event_1788105163431_node_A01` was joined across Android telemetry,
the staging `/events` readback (PostgreSQL-backed), and a real
`/ws/dashboard` `event_trigger`. Semantic classification equality passed at all
three points:

```json
{
  "schema_version": "classification.v1",
  "model_id": "v1_1_0_flower_drone_audio",
  "model_version": "1.1.0",
  "model_label": "Drone",
  "confidence": 0.6086772680282593,
  "class_scores": {
    "Airplane": 0.0002146155311493203,
    "Car": 0.0000030053977297939127,
    "Drone": 0.6086772680282593,
    "Electric_saw": 0.366513729095459,
    "Rainfall": 0.02459142915904522
  },
  "operational_class": "drone",
  "aircraft_probability": 0.6088918835594086,
  "is_target": true,
  "drone_subtype": null
}
```

The standalone shadow observation registry is bounded in-memory storage; the
current schema does not create a separate durable observation row. Therefore
the PostgreSQL assertion applies to the classified event generated by the
existing alert path, while shadow observation reception/normalization is
verified through its HTTP response, registry counters, and tracking counters.

## API, refresh, duplicate, and failure safety

Bounded validator run `4b0ddd83ab7c` passed all ten checks:

- legacy and classified events: HTTP 200;
- legacy and classified observations: HTTP 202;
- server-derived operational normalization;
- PostgreSQL readback equality;
- legacy refresh preserved classification;
- Dashboard WebSocket equality while retaining the legacy label;
- five-send duplicate replay produced `[false,true,true,true,true]`;
- partial classification, unknown schema, unknown label, missing score,
  wrong type, non-null subtype, NaN, and Infinity all failed safely with HTTP
  422 and no 500.

Existing policy is score-driven, not blindly label-driven:

- `aircraft_probability = Airplane + Drone` (clamped to 0..1);
- target when that probability is greater than 0.5;
- target operational class is `drone` when Drone score is greater than
  Airplane, otherwise `aircraft`;
- all remaining cases are `non_aircraft`.

No policy, threshold, cooldown, tracking, Kalman, ETA, or prediction behavior
was changed in BI-1.5.

## Latency and payload

The only real joined classification-ON diagnostic event measured:

- AI finish -> HTTP start: 10.775 ms
- HTTP RTT: 950.311 ms
- server DB: 540.38 ms
- server ingest: 543.15 ms
- server non-DB: 2.77 ms

One sample is not a percentile population and is not compared with a matched
OFF scenario. All requested OFF/ON p50, p95, p99, and max values remain null.
No smoothing or tail deletion was applied.

Controlled exact JSON sizes from the deployed contract fixture were:

- event: 175 legacy bytes, 526 classified bytes (+351, +200.57%);
- observation: 737 legacy bytes, 1,095 classified bytes (+358, +48.58%).

At one observation every 1.5 seconds, the classification-only observation
overhead is 238.67 bytes/s (1.91 kbit/s), or approximately 0.819 MiB/hour per
node. Estimated overhead is 1.639 MiB/hour for two nodes and 3.278 MiB/hour for
four nodes. Audio bandwidth is excluded.

## Final automated verification

- Flutter: 91/91 tests passed; `flutter analyze --no-pub` reported no issues;
  `git diff --check` passed.
- Backend: 138/138 tests passed; `python -m compileall -q .` and
  `git diff --check` passed. Only two existing Pydantic `dict()` deprecation
  warnings were emitted.
- Flutter worktree is clean. Backend functional source is clean; this
  validation directory is the only pending documentation change.
