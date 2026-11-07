# Dashboard Browser Validation

## Automated Coverage

Local synthetic validation confirmed:

- `/dashboard` returns HTTP 200.
- `POST /device-command` can create a live audio command.
- `/ws/audio/{device_id}` accepts authenticated PCM S16LE frames.
- `/ws/audio-monitor/{stream_id}` accepts dashboard subscriber authentication.
- A binary frame sent by the node endpoint is received byte-identical by the dashboard subscriber endpoint.
- SHA-256 of the sent and received frame matched.

Artifact:

- `artifacts/test_results/audio_websocket_integration.txt`
- `artifacts/test_results/local_api_smoke.json`

## Manual Browser Checks Required

The following cannot be fully proven by backend unit tests:

- Browser autoplay behavior.
- AudioContext resume after user gesture.
- Audible quality of scheduled PCM playback.
- Jitter buffer behavior under real network delay.
- Long-running dashboard cleanup on page unload.
- Slow subscriber behavior in an actual browser.

Status: `MANUAL AUDIO VERIFICATION REQUIRED`

## Staging Acceptance

For staging, pass requires:

1. Open dashboard in browser.
2. Select one online node.
3. Click live audio start.
4. Confirm frame count increases.
5. Confirm audible audio is acceptable.
6. Click stop.
7. Confirm node stops streaming and `/audio-streams` subscriber count returns to zero.

