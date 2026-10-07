# Live sensor region membership fix — 2026-10-07

## Cause
`dashboard_live_map_patch.js` filtered current active_device_ids for node lights/geometry, but left persisted four-node group centers unchanged. Fresh historical region tracks still took precedence over the estimate marker. `/device-status` also omitted the in-memory detection state, so polling replaced WebSocket inference states with incomplete rows.

## Change
When runtime explicitly disables localization and inference telemetry exists, the live map displays the current sensor region center (not a located aircraft). Four, three, two and single-node regions update from current states; zero hides the marker. Negative, stale and disconnected states remove nodes. Legacy clients keep the existing accepted-event fallback. Receipt time determines freshness instead of phone clock. Backend group/track/event history is preserved, and this display never feeds TDOA, Tracking or ETA. API snapshots include inference states; WebSocket updates arriving during either poll win over older replies.

## Validation
- Actual template renderMap + installed patch regression: 4→3→2→1→0→2→4, old track precedence, preserved history, localization enabled isolation, stale telemetry, invalid position and phone clock skew.
- Both actual snapshot functions: negative WebSocket inference received during snapshot overrides older positive API state.
- Actual FastAPI /device-status test verifies nested state, false, sequence and connection identity.
- All 26 JavaScript suites passed.
- Relevant pytest selection: 62 passed.
- Expanded pytest after installing missing local redis dependency: 401 passed, 23 skipped, 5 deselected. Separate existing cache test: 1 passed.
- Existing event-bus benchmark cases (4,20,50,100 nodes) fail locally due to zero measured durations/ZeroDivisionError; reproduced all four failures on unchanged older checkout. No assertions weakened or benchmark changed. Linux CI is required before staging deploy.
- git diff --check passed.

## Staging and follow-up
Only sound-backend-staging, srv-da6kdn61egvs7392r92g, branch fix/dashboard-alert-map-latency is eligible for this fix. It has manual deploy enabled. No production settings, database data/schema, localization/Tracking/Fusion math or worker counts are changed.
At inspection Node A02 still used flutter-node-v4-stable-overlap-v6 (no per-inference detection_state); A01/A03/A04 reported the new realtime state. A02 therefore has accepted-event freshness behavior rather than immediate negative inference behavior until its client is updated. A new physical four-node run is required after deployment; automated simulated transitions are not physical results.