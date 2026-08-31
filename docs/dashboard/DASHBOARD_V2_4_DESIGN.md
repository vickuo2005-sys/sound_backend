# Dashboard V2.4 Operational Intelligence Preview

Date: 2026-08-31

## Scope and product position

Dashboard V2.4 is a dark-first, map-centric operational view for multi-node
acoustic detection. It is not an administration console, military game UI, or
prediction product. Classification transport is verified. Motion remains
experimental and field-incomplete. ETA, CPA, future trajectory, Kalman output,
drone subtype, and automatic threat prediction are intentionally absent.

The implementation keeps FastAPI plus HTML/CSS/vanilla JavaScript. It adds no
frontend framework, package manager, build pipeline, or database migration.

## Baseline architecture audit (A-M)

### A. Active dashboard route

Before this branch, `GET /dashboard` directly called `dashboard_v4_clean()`.
The function returned the active V4 HTML. V2.4 changes the route to a
default-off feature switch: `DASHBOARD_V2_ENABLED=true` returns V2.4; otherwise
it calls the same `dashboard_v4_clean()` implementation.

### B. Frontend packaging

The active baseline is one large embedded HTML/CSS/JavaScript string in
`main.py`. V2.4 keeps the same no-build runtime architecture but moves the new
page to `templates/dashboard_v2_4.html` with a small deterministic renderer in
`services/dashboard_v2_4.py`.

### C. Legacy dashboard inventory

- `dashboard_v4_clean()` was the active routed implementation.
- `dashboard_legacy_unused()` is another embedded dashboard with no route.
- The V4 dashboard includes a browser-only simulated alert path that creates
  `simulated_*` events. V2.4 deliberately does not carry this feature forward.
- V2.4 exposes the active V4 implementation at `GET /dashboard/legacy` for
  rollback and debugging.

### D. Initial state REST endpoints

The active V4 page loads `/device-status`, `/events`, `/event-groups`, and
`/tracks`. V2.4 reuses those endpoints and also reads `/health` and
`/runtime-status` so health, build identity, GCS availability, and feature
states are not fabricated.

### E. Realtime WebSocket messages

`/ws/dashboard` currently emits or supports:

- `event_trigger`;
- `event_group`;
- `localization_result`;
- `track_update` and `tracks_rebuilt`;
- `location_update` and `device_location_updated`;
- `node_connected`, `node_heartbeat`, `node_live_update`, and
  `node_disconnected`;
- `device_status_deleted`;
- `event_audio_update`;
- `device_command_ack`.

V2.4 consumes the existing message types. It adds no required message type.
Unknown messages and unknown fields are ignored.

### F. `event_trigger` shape

The message preserves legacy top-level fields such as `type`, `device_id`,
`event_id`, `label`, timestamp, location, RMS, status, listening state, and
alert timing. It also carries nested `event` and `device` objects. When
`CLASSIFICATION_V1_WEBSOCKET_ENABLED=true`, it includes `classification` with
the `classification.v1` contract. V2.4 adds only optional
`dashboard_presentation` metadata.

### G. Classification in realtime events

Yes. The staging BI-1.5 deployment already includes classification.v1 in real
`event_trigger` messages when the existing classification WebSocket flag is
enabled. It includes the five canonical class scores and the server-normalized
`operational_class` and `is_target` policy.

### H. Node status update path

Both REST and WebSocket are used. `/device-status` supplies the initial and
recovery snapshot. Location and node lifecycle messages update individual
nodes. V4 also refreshes all state every 30 seconds. V2.4 is WebSocket-first and
fetches a new snapshot after a reconnect; it does not continuously poll the
whole page.

### I. Historical track API

`GET /tracks?limit=N&points_limit=N` returns `{status, count, tracks}`. Each
track may include `points`. `GET /tracks/{track_id}` returns a track plus up to
200 points, and `GET /tracks/{track_id}/points` returns the point array.
V2.4 draws only existing historical points and limits the display path to the
latest 200 points. It never changes raw track data.

### J. Google Maps lifecycle

V4 initializes one `google.maps.Map`, keeps markers in a `Map`, updates marker
options in place, and removes stale markers. It separately manages historical
polylines, event estimates, uncertainty regions, and one `InfoWindow`. V2.4
retains this lifecycle pattern: one map, keyed node markers, keyed historical
polylines, one latest detection marker, and one uncertainty circle.

If the staging service has no Google Maps key, the primary surface remains
usable: it switches to a clearly labelled relative-coordinate plot built only
from reported node/event latitude and longitude. The plot has no geographic
basemap and makes no localization or distance claim. Missing coordinates never
create a point.

### K. Audio playback

The browser calls `GET /events/{event_id}/audio-url` only after the user selects
an event. The Backend creates a ten-minute GCS signed URL when an audio path and
GCS configuration exist.

### L. Missing staging GCS

The audited staging runtime reports `gcs_configured=false`. V4 attempts the URL
request when `audio_path` exists and then shows a generic playback error. V2.4
uses `/runtime-status` to disable the playback action and explicitly displays
`Staging 未配置音訊儲存`. It never displays a broken player.

### M. Reused data; no new API required

The existing APIs already provide event/classification, five scores, node
state, listening state, GPS, upload state, track points, health, build identity,
GCS state, and motion flags. No Dashboard database migration or new operational
API is necessary.

## Information architecture

V2.4 implements three logical views without a frontend router:

1. Dashboard: compact health metrics, Live Detection, five score bars, Map &
   Tracks, Experimental Motion, Recent Events, Node Status, and System Health.
2. Events: target/class/node/time filters, complete event table, classification
   detail, signal/location, audio state, and raw IDs.
3. Nodes: reported and canonical node slots, online/listening/GPS/AI/backend/
   upload state, last seen, and map focus.

The command bar permanently identifies `STAGING`, Backend state, WebSocket
state, last update, and current time.

## Visual hierarchy

- Background: deep navy `#07111f`.
- Surfaces: `#101c2d`, `#132238`, and `#172a43`.
- Primary operational accent: cyan.
- Healthy: green; target: amber; system error: red; experimental: purple.
- Every state combines a symbol, text, and color.
- Live Detection is the first focal card; the map is the largest operational
  surface. Health cards are compact and do not consume the first screen.

## Verified versus experimental policy

- Classification uses the transported `model_label`, `confidence`, five
  `class_scores`, `operational_class`, and `is_target`. Model values are called
  model scores, never accuracy or real-world probability.
- Presentation sorting never changes canonical transport order.
- Legacy events display their original label and a Legacy state; the browser
  does not invent a target policy.
- Motion is always labelled `EXPERIMENTAL` and `未完成多節點實地驗證`.
- Motion UI reads Backend fields only. It performs no browser motion algorithm.
- When motion shadow is false, approaching/departing says `尚未啟用`.

## Realtime and fallback logic

1. Fetch REST snapshot.
2. Connect `/ws/dashboard`.
3. Apply event, node, and track messages incrementally.
4. Reconnect after 1, 2, 4, 8, 16, then at most 30 seconds.
5. After a successful reconnect, fetch a fresh snapshot to cover the gap.
6. Keep at most 200 recent browser events and at most 200 displayed points per
   historical track.

Loading, empty, unavailable, disconnected, and error states are explicit.
Unknown optional fields and unknown WebSocket types are ignored.

## Responsive layout

- Target: 1920x1080, 1440x900, and 1366x768.
- At less than 1500 px, the right rail moves below the main content so the
  operational surface is not squeezed at 1366x768.
- At less than 1100 px, metrics use three columns and Live Detection/Class
  Scores stack.
- At less than 900 px, the sidebar becomes a horizontal compact navigation bar.
- At narrow mobile widths, metrics, detection detail, and node cards stack.
- Map minimum height is 430 px on desktop and 380 px below 900 px.
- Tables scroll within their cards rather than overflowing the page.

## Feature flags

- `DASHBOARD_V2_ENABLED=false` by default.
- `DASHBOARD_V2_EXPERIMENTAL_MOTION_ENABLED=false` by default.
- Neither flag changes tracking, classification, cooldown, offline retry, or
  motion-shadow semantics.

Staging enables Dashboard V2 only. Experimental Motion remains off for the
initial demo because the current staging dataset has one node, zero tracks, and
no multi-node field validation.

## Demo flow

Open the staging Dashboard, open the staging Flutter app as Node A01, confirm
Backend and WebSocket connectivity, start listening, play the known Drone test
audio, then verify Live Detection, five class scores, Recent Events, Node state,
and location if the event contains one. Audio unavailability is an expected
staging state while GCS is unconfigured.

## Rollback

1. Set staging `DASHBOARD_V2_ENABLED=false`.
2. Confirm `/dashboard` serves the V4 legacy page.
3. Use `/dashboard/legacy` for direct comparison.
4. Do not change production or motion flags.
5. If code rollback is required, redeploy the previous staging SHA; no schema
   rollback is needed because V2.4 creates no migration.
