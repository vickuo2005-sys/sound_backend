# Dashboard V2.4 staging demo runbook

## Before the meeting

1. Open `https://sound-backend-staging.onrender.com/dashboard`.
2. Confirm the large `STAGING` badge is visible.
3. Wait for `Backend 已連線` and `WebSocket 即時連線`.
4. Open the installed staging Flutter app on the authorized Android device.
5. Set or confirm Node ID A01.
6. Confirm A01 appears in Node Status. Do not present A02-A04 as active; an
   unreported node must say `未回報`.

## Live demonstration

1. Tap `開始監聽` in the staging app.
2. Confirm the Dashboard changes A01 to `LISTENING` without a manual refresh.
3. Play the known Drone test audio near the phone.
4. Wait for on-device inference and upload.
5. Confirm Live Detection shows:
   - Drone / 無人機聲音;
   - Model score;
   - TARGET / 目標;
   - Node A01;
   - event time and event ID.
6. Confirm Class Scores shows Airplane, Car, Drone, Electric_saw, and Rainfall.
7. Confirm Recent Events receives the event automatically.
8. Open Events, select the event, and review classification, signal, location,
   upload/audio state, and raw IDs.
9. If location exists, use the event or A01 entry to focus Google Maps.
10. Explain that Motion is Experimental and has not completed multi-node field
    validation. Do not describe ETA or predicted trajectory.

## Expected staging limitations

- The current staging runtime reports `gcs_configured=false`. Audio controls
  should say `Staging 未配置音訊儲存` and remain disabled.
- The current BI-2 field gate has one physical node. Motion speed, heading, and
  approach/departure may remain unavailable.
- Historical tracks are rendered only when real track points exist.

## Troubleshooting

### WebSocket disconnected

Wait for automatic reconnect. The delay grows from 1 to 30 seconds. After a
successful reconnect the Dashboard automatically fetches a complete snapshot.
Do not repeatedly reload the page.

### Backend cold start

Render may need tens of seconds after inactivity. Keep the page open until the
Backend state changes from connecting to connected.

### App offline

Confirm the phone is on the intended network and that the app is the staging
build. The Dashboard must not be pointed at production as a substitute.

### A01 does not show Listening

Check the app's Node ID, Backend state, and network. If the current Backend does
not emit the listening change immediately, wait for the next existing node
heartbeat. Do not change remote command or app semantics during the demo.

### No classification

Confirm monitoring is active, the known Drone test audio is audible to the
phone, and the app has completed inference. Do not inject a fake Dashboard
event.

### No audio

This is expected while staging GCS is unconfigured. The event/classification
path is still valid; explain the explicit unavailable state.

### GPS unavailable

The event and classification remain usable. The map must not invent a marker;
show the Node/Event location as `-`.

### Google Maps key unavailable

The Dashboard switches to `RELATIVE COORDINATES`. Confirm that it explicitly
says there is no geographic basemap and that every plotted point comes from a
reported node/event coordinate. Do not describe the plot as a distance or
localization result.

## Rollback during a demo

Open `/dashboard/legacy` or set staging `DASHBOARD_V2_ENABLED=false`. No database
rollback is required. Production must not be redeployed or used as staging.
