# Dashboard status overview simplification — 2026-09-07

## Follow-up: map-first pages and reliable simulation exit

The later user review supersedes the first layout below. The overview now
contains status, node metrics, and the full map. Detection summary contains the
latest record, expanded model scores, and recent events. Event search, tracks,
nodes, system status, and simulation have separate navigation entries.
Simulation temporarily owns the same map element and returns it to the overview
on exit. A fixed "結束模擬" button remains accessible during scrolling and from
other views. Existing inline exit also remains available.

Google Maps configuration was recovered from the existing staging page for the
local preview, held only in the preview process environment/memory. Google
returned RefererNotAllowedMapError for http://127.0.0.1:8765/dashboard. The
template now handles gm_authFailure and provides a labeled coordinate fallback.
It never changes or bypasses Google website restrictions.

Previous conversations were read sequentially. In "降低推論後警示延遲"
(01a03451-2633-7042-93fe-24daf628693b), historical completion messages report
successful Google Maps on the isolated staging hostname, with local commands
using an empty GOOGLE_MAPS_API_KEY. No evidence of authorized localhost usage
was found in the inspected history pages. Reusing the historical validation
path means deploying the reviewed UI to isolated staging; this follow-up has
not deployed it. Alternatively, the key owner can allow the specific local URL.

Validation after the page split: 234 backend tests passed, 2 existing warnings.
The fixed simulation exit was clicked in the in-app preview and returned to the
overview with simulation controls hidden. Full Google basemap/overlay validation
is pending a permitted origin. API reference:
[Google Maps errors](https://developers.google.com/maps/documentation/javascript/error-messages#referer-not-allowed-map-error).

## User outcome

The overview now answers whether nodes are listening and what to do next.
Three primary metrics show online nodes, listening nodes, and service access.
Five-class scores and experimental motion use native disclosure controls.
Diagnostics, node summaries, audio storage configuration, and runtime revision
are available in the System Status view. Existing node controls, event detail,
CSV export, tracks, map controls, and simulation entry remain available.

## Product research and design decisions

- [AXIS Camera Station health monitoring](https://newsroom.axis.com/en-us/article/health-monitoring-axis-camera-station)
  presents system and device health together and surfaces equipment requiring
  attention. Applied here as an explicit summary and a relevant next action.
- [UniFi Protect 7.0](https://blog.ui.com/article/introducing-protect-7-0)
  prioritizes live views and reduces repetitive detection noise. Applied here
  as a focused overview; this change does not implement event deduplication.
- [Grafana dashboard best practices](https://grafana.com/docs/grafana/latest/visualizations/dashboards/build-dashboards/best-practices/)
  describes overview-to-detail navigation. Applied here as overview, events,
  tracks, nodes, and system views with diagnostics removed from the overview.

These are design adaptations, not a claim of product or capability equivalence.

## Status semantics

- Initial load is unknown, not zero nodes confirmed.
- No readable service response produces an unconfirmed monitoring state.
- A failed device snapshot or one older than 20 seconds produces unknown node
  status and replaces online/listening counts with dashes.
- Fresh node data distinguishes no online nodes from online but not listening.
- Listening is described as node-reported, not verified classification accuracy.
- WebSocket disconnection is visible; full snapshots refresh every 30 seconds
  in addition to the existing 5-second device refresh. Concurrent snapshot
  requests are guarded.
- An event dated within the past 60 seconds is labeled "最近 1 分鐘". Older,
  missing, or future event timestamps do not receive that label. This interval
  is a display rule, not an alert or safety threshold.
- Historical event cards no longer show LIVE. Event tables include date/time.
- Map text explicitly states that markers can represent historical positions.
- Experimental simulation remains visibly labeled and opens its motion details.

## Validation

- Backend: 231 passed, 2 existing Pydantic deprecation warnings.
- Node: status scenarios and existing simulation prediction assertions passed.
- Browser: 1440×1000 and 390×844; no page JavaScript errors or document overflow.
  Checked node/system/event navigation, model-score disclosure, simulation
  enter/exit, and historical event labeling.
- Browser preview uses a read-only real staging snapshot captured at
  2026-09-07T09:55:09 UTC. The preview header identifies the snapshot timestamp.
  It does not support writes, live WebSocket updates, or a Google Maps basemap.
- The production template still uses its existing live endpoints and WebSocket.
  Live Android controls were not exercised because no devices were available.
- No commit, push, deployment, database modification, or production change.

## Main files

- templates/dashboard_v2_4.html: hierarchy, Chinese labels, freshness integration.
- static/dashboard_status.js: pure status and event-age presentation rules.
- services/dashboard_v2_4.py: includes status rules in the rendered page.
- tests/js/test_dashboard_status.js: loading, offline, stale, listening, update
  disconnection, and event age checks.
