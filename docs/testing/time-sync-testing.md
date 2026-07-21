# V3.2 Time Sync Testing

## Backend

```powershell
cd C:\sound_backend
$env:PYTHONPYCACHEPREFIX = Join-Path $env:TEMP 'sound_backend_pycache_check'
.\venv\Scripts\python.exe -m compileall main.py services tools
.\venv\Scripts\python.exe tools\test_time_sync.py
.\venv\Scripts\python.exe tools\test_event_fusion.py
.\venv\Scripts\python.exe tools\test_smart_audio_upload.py
.\venv\Scripts\python.exe tools\test_tdoa_solver.py
```

Smoke-test these routes after deployment:

- `GET /health`
- `GET /time-sync`
- `GET /device-status`
- `POST /location-update`
- `GET /dashboard`
- `GET /events`
- `GET /event-groups`

Expected behavior:

- `/time-sync` returns `server_time_ms` and quality thresholds.
- `/location-update` accepts time sync metadata and stores it in
  `device_status`.
- `/device-status` returns per-device `time_sync_offset_ms`,
  `time_sync_rtt_ms`, `time_sync_quality`, `time_sync_at`, and
  `last_time_sync_at`.
- Dashboard node cards show time sync quality and RTT.
- Existing `/events`, `/upload-audio`, `/upload-tdoa-clip`, and Event Fusion
  behavior remains unchanged.

## Flutter

```powershell
cd C:\Users\vicku\sound_detector_clean
flutter pub get
flutter analyze
flutter test
flutter build apk --debug
```

Expected app behavior:

- App calls `/time-sync` immediately after startup.
- App repeats sync every 30 seconds.
- Each sync run takes three samples and keeps the lowest RTT sample.
- GPS `/location-update` continues every 2 seconds.
- Location payload includes the latest fresh time sync metadata.
- If sync fails, sound detection and GPS continue.
- If sync is stale, location payload reports `time_sync_quality = stale`.
- Event payloads include `time_sync_offset_ms` and `time_sync_rtt_ms` only when
  the sync sample is fresh.

## Manual Checks

On the Dashboard, confirm each online node displays:

- Sync quality
- Sync RTT
- Sync offset

In Supabase `device_status`, confirm:

```text
time_sync_offset_ms is not null
time_sync_rtt_ms is not null
time_sync_quality is good / medium / poor / bad / stale
time_sync_at is recent
```

High RTT or stale sync should not crash the app or backend. It should only lower
the reported quality.
