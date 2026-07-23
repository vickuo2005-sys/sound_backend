# Final Completion Audit

## Completed

- Node Control WebSocket route and protocol validation.
- Flutter NodeConnectionService hello, heartbeat, reconnect, command ACK/result.
- WebSocket-first command handling with REST polling fallback.
- Command idempotency cache in Flutter command dispatcher.
- Backend stream-scoped live audio session token generation for `START_LIVE_AUDIO`.
- Audio WebSocket header authentication with `x-upload-token`, `x-stream-id`, and `x-stream-token`.
- Flutter live audio PCM S16LE binary frame serialization.
- Android AudioRecord fan-out for live audio frames without opening a second microphone recorder.
- AudioStreamManager validation, sequence gap, malformed frame, and backpressure counters.
- Migration conflict matrix and final execution plan.
- Backend and Flutter tests for realtime protocol and live frame serialization.

## Preserved

- AudioRecord continuous monitoring and pre-buffer.
- Detection Mode / Collection Mode.
- AI inference.
- Event MP3 upload and WAV TDOA clip upload.
- Time Sync, Event Fusion, Localization, and Tracking.
- Legacy REST command polling.

## Remaining Field Validation

- Real device live audio monitoring must be tested with `LIVE_AUDIO_ENABLED=true`.
- Dashboard browser-side PCM playback UI is not yet a production-grade audio monitor.
- Android true Foreground Service is documented, but this pass does not replace the current Activity-based runtime with a service.
- Persistent offline upload queue is documented as required, while existing event upload flow remains unchanged.

## Baseline Test Results

See `docs/testing/final_validation.md`.

