# Android Background Runtime

## Current Runtime

The current Flutter APK uses Activity-based operation with:

- AudioRecord continuous monitoring.
- keep-screen-on flag.
- kiosk / lock-task support where available.
- boot receiver already present in the Android package.
- WebSocket reconnect and heartbeat in Dart.

## Foreground Service Recommendation

For production unattended field nodes, move these long-running tasks into a foreground service:

- AudioRecord monitoring.
- Node Control WebSocket.
- Heartbeat.
- Reconnect.
- Event audio upload retry.

The foreground notification must not show secrets, tokens, signed URLs, or raw event metadata.

## Android Permissions

Required permission set:

- `RECORD_AUDIO`
- `INTERNET`
- `ACCESS_FINE_LOCATION`
- `ACCESS_COARSE_LOCATION`
- foreground service microphone permissions on modern Android versions.

## Lifecycle Rules

- Do not start a second microphone recorder for live audio.
- Do not stop AudioRecord when starting/stopping live audio.
- Clear heartbeat timers and sockets on dispose.
- Device ID changes must reconnect WebSocket and update REST GPS payloads.

