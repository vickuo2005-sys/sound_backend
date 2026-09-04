# Dashboard V2.2 parity plan

Date: 2026-09-04

V2.2 comparison baseline: `perf/post-inference-latency-v2-2` at `2b29da3`

Implementation branch: `feat/v2-4-dashboard-simulation` (isolated staging only)

## Objective

Restore the operational capabilities that were visible in the V2.2 Dashboard
without undoing the safer V2.4 command lifecycle, classification contract, or
staging isolation. This is a presentation-layer parity pass. It does not change
event admission, fusion, tracking, localization, database schema, or production
configuration. The only server-side correction is initialization of the
existing SQLite CSV select clause; it does not change the export schema.

## Capability comparison

| Capability | V2.2 | V2.4.2 before this pass | Decision |
|---|---|---|---|
| Five-class classification and live event | Legacy label-first UI | Verified `classification.v1` scores and null-safe legacy fallback | Keep V2.4 |
| Node start/stop and detection/collection modes | Direct controls | Confirmed command lifecycle with delivery, ACK, timeout, and final state | Keep V2.4 |
| Event browser and audio playback | Alert list and event audio | Filtered event browser; signed audio URL is runtime-gated | Keep V2.4 |
| CSV export | `/events/export.csv` link | Link absent | Restore now |
| Fusion region estimates | List and map preview | Data loaded but not rendered | Restore now |
| Historical tracks | List, map preview, playback | Lines only; no selection/detail/playback | Restore now |
| Fixed node location | GPS copy, coordinate/map editing, clear | Effective location displayed only | Restore safe coordinate/GPS-copy editor and clear now |
| Map-click fixed-location editing | Available | Absent | Defer; coordinate editor preserves the underlying function with less accidental-write risk |
| Live audio monitor | Start/stop and PCM WebSocket player | Intentionally disabled in Advanced controls | Defer until isolated-staging authorized-device validation |
| Simulated browser alert | Created a fake `simulated_*` event | Removed | Never restore |

## Implemented scope

### Tracks and estimates

The `Tracks` workspace reads the existing `/event-groups` and `/tracks`
responses already included in the snapshot. It shows only groups with a real
Backend-provided center. Selecting a group focuses the real center and draws an
uncertainty circle only when `uncertainty_radius_m` is present.

The operational map auto-selects only a non-closed estimate updated within 15
seconds. Older estimates remain available as history in the Tracks workspace
and appear on the map only after an explicit operator selection, so a stale
region is not presented as the current source.

Historical replay reveals the existing stored points in event-time order. It
does not interpolate, smooth, fill missing observations, extrapolate, or draw a
future path. Google Maps is required for animated replay; the coordinate
fallback still marks a selected group without pretending to be a geographic
basemap.

### Fixed node locations

The Nodes view distinguishes effective location, raw GPS, and fixed location.
The editor supports explicit latitude/longitude entry, copying current raw GPS,
and clearing a fixed location through the existing PUT/DELETE
`/device-locations/{device_id}` endpoints.

Writes require the staging write token. The token is placed only in the
`x-upload-token` request header, is cleared when the modal closes or a request
fails, and is never written to `localStorage` or `sessionStorage`. Clearing uses
a two-step themed confirmation within the modal.

### CSV

The Events page exposes the existing read-only `/events/export.csv` download.
Browser smoke exposed an existing SQLite-only `columns` initialization error;
the fallback now builds the same schema-aware select clause already used by the
PostgreSQL path.

## Explicit exclusions

- No fake event generator or synthetic alert is added.
- Live audio is not enabled by this pass.
- No client-side localization, smoothing, prediction, or ETA is added.
- No REST or WebSocket contract is made mandatory; legacy payloads remain
  null-safe.
- No migration, new table, feature flag, production deploy, or production
  configuration change is required.

## Compatibility and rollback

All additions consume existing optional response fields. Unknown and missing
fields keep their empty-state behavior. The safest rollback is to revert this
Dashboard-only commit; Backend event ingestion, device commands, storage, and
tracking data remain unchanged.

## Acceptance checks

- Existing Dashboard and node-control regression tests remain green.
- A rendered template passes JavaScript syntax validation.
- Tracks and estimates render empty states when optional data is absent.
- Location writes use PUT/DELETE plus `x-upload-token`, with no browser storage.
- No `simulateAlert` path exists.
- Isolated Render staging serves the exact candidate SHA before browser smoke.
