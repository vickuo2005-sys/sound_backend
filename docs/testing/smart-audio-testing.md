# V3.1b Smart Audio Testing

## Backend

```powershell
cd C:\sound_backend
$env:PYTHONPYCACHEPREFIX = Join-Path $env:TEMP 'sound_backend_pycache_check'
.\venv\Scripts\python.exe -m compileall main.py services tools
.\venv\Scripts\python.exe tools\test_event_fusion.py
.\venv\Scripts\python.exe tools\test_smart_audio_upload.py
.\venv\Scripts\python.exe tools\test_tdoa_solver.py
```

Smoke-test these routes after deployment:

- `GET /health`
- `GET /dashboard`
- `GET /events`
- `GET /event-groups`
- `GET /event-groups/{group_id}`
- `GET /events/{event_id}/audio-url`
- `GET /events/{event_id}/tdoa-clip-url`
- `POST /upload-audio`
- `POST /upload-tdoa-clip`

Expected behavior:

- Legacy WAV upload still works.
- MP3 upload returns `audio_format = mp3`.
- TDOA clip upload returns `tdoa_clip_format = wav`.
- Invalid extension/header/MIME combinations return 400.
- Posting the same `event_id` after audio upload updates the observation
  snapshot and does not add a duplicate observation.

## Flutter

```powershell
cd C:\Users\vicku\sound_detector_clean
flutter pub get
flutter analyze
flutter test
flutter build apk --debug
```

Expected app behavior:

- AI, RMS, and V3.1a timing still use original PCM.
- Event metadata is posted quickly before background audio upload finishes.
- MP3 encoding runs after the event WAV is saved.
- Short WAV clip is extracted around `rms_peak_sample`.
- If MP3 encoding fails, the app uploads the original WAV as fallback.
- If clip upload fails, primary audio still remains available.
- Dashboard playback uses the primary audio signed URL.
- Event Group observation detail can show and play the short WAV clip.

## Useful Log Lines

Flutter:

```text
[AUDIO_PIPELINE] primaryFormat=mp3 sourcePcmBytes=... primaryBytes=...
tdoaClipBytes=... encodingMs=... savingPercent=...
```

Backend:

```text
[AUDIO_UPLOAD] type=primary format=mp3 bytes=... device=...
[AUDIO_UPLOAD] type=tdoa_clip format=wav bytes=... device=...
```
