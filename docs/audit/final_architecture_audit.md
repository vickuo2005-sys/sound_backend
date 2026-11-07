# Final Architecture Audit

## Scope

This audit covers the local backend at `C:\sound_backend` and the Flutter Android node at `C:\Users\vicku\sound_detector_clean`.

## Baseline

The system already had REST-based node reporting, GPS upload, command polling, AI classified events, MP3 event upload, WAV TDOA clip upload, Time Sync, Event Fusion, localization, tracking, GCS signed playback URLs, and Dashboard WebSocket updates.

## Added In Final Architecture Pass

- Node Control WebSocket contract and route: `/ws/node/{device_id}`
- In-memory `NodeManager` for live connection state, duplicate connection replacement, heartbeat, per-node send lock, and live node state.
- WebSocket-first command delivery while keeping REST command polling as legacy fallback.
- Binary audio frame protocol parser and `AudioStreamManager`.
- Audio stream endpoint: `/ws/audio/{device_id}` guarded by `LIVE_AUDIO_ENABLED`.
- Live state endpoint: `/nodes/live`.
- Audio stream state endpoint: `/audio-streams`.
- Final safe migration files:
  - `migrations/v4_final_realtime.sql`
  - `migrations/v4_final_localization.sql`
  - `migrations/v4_final_tracking.sql`
- Realtime protocol tests.
- Final documentation package.

## Preserved Legacy Behavior

- `POST /events`
- `POST /upload-audio`
- `POST /upload-tdoa-clip`
- `POST /location-update`
- `GET /device-command/{device_id}`
- `POST /device-command-ack`
- Dashboard WebSocket `/ws/dashboard`
- Event Fusion, Time Sync, MP3 playback, WAV clip playback, localization, and tracking.

## Risks

- Live Opus streaming is architecture-ready and parser-backed, but disabled by default with `LIVE_AUDIO_ENABLED=false`.
- In-memory WebSocket managers assume one Render worker. Multiple workers need Redis/pub-sub or sticky routing.
- Flutter now has Node Control WebSocket support, but legacy polling remains active for compatibility.
- Existing APP UI contains older mojibake strings; this pass avoided broad UI rewriting.

## Baseline Validation

Run:

```powershell
cd C:\sound_backend
.\venv\Scripts\python.exe -m compileall main.py app services tools
.\venv\Scripts\python.exe tools\test_realtime_protocol.py
```

Flutter:

```powershell
cd C:\Users\vicku\sound_detector_clean
flutter analyze
flutter test
flutter build apk --debug
```

