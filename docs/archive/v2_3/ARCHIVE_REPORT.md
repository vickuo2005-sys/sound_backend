# Sound Detector V2.3 archive report

Archive date: 2026-09-04 (Asia/Taipei)  
Archive status: **COMPLETE — DEVELOPMENT BASELINE PRESERVED**  
Operational prediction verdict: **NO-GO pending real field validation**

## 1. Executive summary

V2.3 is archived as the current integrated staging/demo baseline. It includes
the restored operational Dashboard, node controls, five-class transport,
observation/tracking staging paths, and the fixed-site approach simulation.

The source and runtime evidence are sufficient to preserve and reproduce the
software baseline. They are not sufficient to claim that the system can make
a safety-critical evacuation decision from a real drone's distance and ETA.
The current approach display is a deterministic simulation preview, not a
field-validated tracking input.

No feature, UI, database migration, environment flag, or deployment was
changed as part of this archive operation.

## 2. Release identity and source baselines

| Component | Branch / environment | Exact baseline |
| --- | --- | --- |
| Backend functional source | `feat/v2-4-dashboard-simulation` | `256f44548c8375c544d3d6bc972e126041746232` |
| Flutter source | `feat/v2-4-bi2-motion-field-validation` | `e593007cfd9df9c969ff6cfdd89ff8c9c9288121` |
| Isolated Render staging | `sound-backend-staging` | `256f44548c8375c544d3d6bc972e126041746232` |
| Current production runtime | `sound-backend.onrender.com` | `5babe2bafaffbb77b48d16a5e1675f202ae7286b` |
| Flutter package | staging application | `1.0.2-staging` (`versionCode` 3) |

The V2.4.x names above are internal implementation labels. The archived
product version requested by the owner is **V2.3**.

The backend working tree contained a pre-existing local modification to
`docs/dashboard/NODE_CONTROL_FLOW.md`. It was deliberately excluded from the
immutable source snapshot and from this archive commit. No user work was
overwritten.

## 3. Archived functional scope

The baseline preserves:

- Google Maps operational view and fixed-site marker/protected radius;
- fixed-site approach, entry, closest-point-of-approach, and ETA simulation;
- Dashboard node controls and command acknowledgement flow;
- live detection, recent events, five-class `classification.v1` transport;
- observation shadow/tracking paths in isolated staging;
- event groups, historical track presentation, CSV export, and fixed-location
  coordinate/GPS-copy editor;
- Flutter staging client restart telemetry correction at its exact source SHA.

The fixed-site simulation performs no event, device, track, observation, or
database writes. It is a presentation and scenario-analysis path only.

## 4. Validation evidence retained

| Check | Result |
| --- | --- |
| Backend automated suite | PASS — 226 tests |
| Backend warnings | 2 existing Pydantic `.dict()` deprecation warnings |
| Dashboard 1366×768 | PASS — no horizontal overflow |
| Dashboard 1920×1080 | PASS — no horizontal overflow |
| Browser console | PASS — 0 errors during final staging check |
| Direct-approach simulation | PASS — distance decreased and ETA was shown |
| Parallel/fly-by simulation | PASS — CPA shown and ETA withheld |
| Departing simulation | PASS — distance increased and ETA withheld |
| Staging runtime health | PASS at capture time |
| Production runtime health | PASS at capture time; no production mutation |

Previously completed speaker-playback Drone checks establish an end-to-end
smoke path from the Android client through live detection and recent events.
They do not establish physical-drone detection range or class accuracy.

### Previously captured node-control acceptance

The following evidence was captured in isolated staging on 2026-09-01 through
2026-09-02. It is preserved here because the detailed source note remains a
pre-existing, uncommitted working-tree change and is intentionally not included
as source code in this archive commit.

- Acceptance backend SHA:
  `f92b3c224e178e7a919162a9284be0d37c05c9e2`.
- Android package/version:
  `com.example.sound_detector_clean.staging`, `1.0.2-staging`
  (`versionCode=3`).
- Device: A01; acceptance ended ONLINE, Detection mode, Listening OFF.
- No fake event, production operation, code/UI change, or redeploy was used.

| Command | ID | POST | Delivery | Pending UI | ACK status / message | Final state |
| --- | ---: | --- | --- | --- | --- | --- |
| `start_listening` | 7 | success | WebSocket | observed | `succeeded` / `listening started` | ONLINE, Detection, Listening ON |
| `stop_listening` | 8 | success | WebSocket | observed | `succeeded` / `detection stopped` | ONLINE, Detection, Listening OFF |
| `set_collection_mode` | 9 | success | WebSocket | observed | `succeeded` / `collection mode applied` | ONLINE, Collection, Listening OFF |
| `set_detection_mode` | 10 | success | WebSocket | observed | `succeeded` / `detection mode applied` | ONLINE, Detection, Listening OFF |

The Dashboard reflected terminal ACK and node-state changes without manual
refresh.

The associated speaker-playback demo used command 11 to start and command 12
to stop. Event `event_1788312711282_node_A01` reached Live Detection and Recent
Events as `classification.v1`, model `v1_1_0_flower_drone_audio`, with label
Drone and confidence 90.76%. All five scores were present: Drone 90.76%,
Electric_saw 8.99%, Airplane 0.21%, Rainfall 0.03%, and Car 0.01% (rounded).
No fake event was used. This remains transport/demo evidence only.

## 5. Runtime snapshot at archive time

The sanitized evidence capture is stored in `runtime_snapshot.json`.

At `2026-09-04T02:25:00Z`, isolated staging reported:

- deployed backend SHA `256f44548c8375c544d3d6bc972e126041746232`;
- PostgreSQL active and Dashboard simulation enabled;
- Observation Shadow and Observation Tracking enabled;
- tracking reorder buffer and staging DB latency probe disabled;
- zero live node WebSocket connections;
- A01 offline, Listening OFF, last seen 2026-09-02;
- zero stored tracks returned by `/tracks`;
- 20 event groups returned by `/event-groups`;
- GCS not configured, so event audio upload/playback is unavailable.

At `2026-09-04T02:25:57Z`, production reported SHA
`5babe2bafaffbb77b48d16a5e1675f202ae7286b`. Observation Shadow,
Observation Tracking, tracking reorder, and staging DB latency probe all
remained disabled. Production was not used as staging and was not modified.

## 6. Release verdict

| Use | Verdict |
| --- | --- |
| Reproducible source/archive baseline | YES |
| Isolated staging Dashboard demo | YES, after an authorized Android node reconnects if live data is required |
| Speaker-playback end-to-end smoke | YES, with the documented evidence limitation |
| Real multi-node motion validation | NO |
| Physical-drone range/accuracy claim | NO |
| Fixed-site evacuation ETA decision | NO |
| Production rollout of the new staging-only paths | NO |

## 7. Restore and rollback references

- Backend functional restore point:
  `256f44548c8375c544d3d6bc972e126041746232`.
- Flutter restore point:
  `e593007cfd9df9c969ff6cfdd89ff8c9c9288121`.
- Production runtime remains independently pinned to:
  `5babe2bafaffbb77b48d16a5e1675f202ae7286b`.
- Re-enable or disable staging-only features through their existing feature
  flags; do not substitute production for isolated staging.

Restoration should use the exact Git objects or the external archive bundle
whose SHA-256 manifests match. Local ignored configuration and credentials
must be recreated from the appropriate secret manager; they are intentionally
not recoverable from the archive.

## 8. Archive integrity and exclusions

The external V2.3 bundle is built from committed Git trees, not the mutable
working directories. It includes per-file SHA-256 JSON and text manifests.

Excluded by design:

- `.git`, build and dependency caches;
- `.env`, `config/staging.local.json`, tokens, database URLs, service keys;
- `google-services.json`, signing keys, keystores, and PEM/key files;
- APKs and other generated binaries;
- captured audio and local event stores;
- precise device/site coordinates.

See [KNOWN_RUNTIME_ISSUES.md](KNOWN_RUNTIME_ISSUES.md) before resuming
development or presenting V2.3 as operationally validated.
