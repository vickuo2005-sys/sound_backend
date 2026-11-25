# Sound Detector V2.3 known runtime issues

Snapshot date: 2026-09-04 (Asia/Taipei)

These entries separate directly observed runtime state from missing field
evidence. Missing evidence must not be replaced by local, synthetic,
projected, smoothed, or simulated values.

## A. Currently observed staging state

| ID | Status | Evidence | Operational impact |
| --- | --- | --- | --- |
| RUN-01 | OPEN | Runtime reported `node_websocket_connections=0`; A01 was offline and last seen on 2026-09-02. Local ADB listed zero attached devices. | Live node commands, new detections, and a live demo cannot run until an authorized Android device reconnects. |
| RUN-02 | OPEN | Staging reported `gcs_configured=false`; A01's last upload status was “Audio upload failed, metadata saved”. | Event metadata remains usable, but staging audio upload/playback is unavailable. |
| RUN-03 | OPEN | `/tracks` returned 0 tracks while `/event-groups` returned 20 groups. | Historical trajectory UI may correctly be empty; no track may be fabricated for presentation. |
| RUN-04 | ACCEPTED | Render Free instances may cold-start after inactivity; a prior deployment health check stalled while a retry completed normally. | First request or deploy completion can be delayed. This is an environment characteristic, not proof of an application regression. |
| RUN-05 | ACCEPTED | Backend tests passed with two Pydantic `.dict()` deprecation warnings. | No current functional failure, but future Pydantic upgrades require cleanup. |

The device-status row contains the node's last reported backend/WebSocket
fields. When the live runtime connection count is zero, those cached fields
must not be interpreted as proof that the device is currently connected.

## B. Validation and semantics gaps

| ID | Status | Evidence gap | Required evidence or action |
| --- | --- | --- | --- |
| VAL-01 | NO-GO | Fixed-site distance/ETA is simulation-only and does not consume a real validated track. | Feed real event-time track updates into a separately gated preview, then run controlled physical field trials before any evacuation use. |
| VAL-02 | NO-GO | No completed two-or-more-node motion dataset with required repeated scenarios. | Collect the BI-2 field matrix and report measured position, velocity, CPA, and ETA error distributions. |
| VAL-03 | NO-GO | Five-class transport works, but Airplane, Car, and Rainfall lack trustworthy field evidence. Speaker playback produced smoke evidence only. | Capture labeled real-world samples per class and publish confusion/coverage results. |
| VAL-04 | OPEN | The required 50 OFF / 50 ON staging latency comparison was not completed. | Measure real Android-to-staging distributions; do not substitute localhost or one-off values. |
| VAL-05 | ACCEPTED | Observation/tracking shadow state is in memory and clears on backend restart. | Treat it as best-effort diagnostic state until persistence semantics are explicitly designed. |
| VAL-06 | OPEN | Tracking reorder remains disabled in the archived staging runtime. | Preserve event-time ordering metrics and complete field comparison before enabling by default. |
| VAL-07 | OPEN | Only one physical Android node has been used in the recent acceptance flow. | Multi-node behavior remains unverified until two- and four-node field runs are completed. |

## C. UI and workflow limitations

| ID | Status | Limitation | User impact |
| --- | --- | --- | --- |
| UI-01 | OPEN | The fixed-site simulation describes approach/CPA/ETA but is not an operational alert policy. | It must not instruct users when to evacuate or imply a guaranteed arrival time. |
| UI-02 | DEFERRED | Live Audio remains unavailable/deferred in the current Dashboard flow. | Operators cannot use the Dashboard as a staging audio playback console. |
| UI-03 | DEFERRED | Map-click fixed-location editing is not restored; coordinate entry and current-GPS copy are available. | Fixed sites require explicit coordinate-based setup. |
| UI-04 | EXPECTED | Node Controls are disabled while the target node is offline. | A01 must be online and Node WS connected before commands are accepted. |

## D. Resume criteria

Before representing V2.3 as an operational fixed-site warning system, all of
the following must be true:

1. an authorized Android device is online in isolated staging;
2. staging audio storage is either configured with staging-only credentials or
   explicitly excluded from the test objective;
3. the multi-node motion field matrix is complete;
4. fixed-site distance, approach state, CPA, and ETA are evaluated against
   measured ground truth;
5. uncertainty and stale-track behavior are visible and fail closed;
6. alert/evacuation semantics receive a separate safety review;
7. production changes receive explicit approval after staging evidence.
