# Final Validation

## Backend

```powershell
cd C:\sound_backend
.\venv\Scripts\python.exe -m compileall main.py app services tools
.\venv\Scripts\python.exe tools\test_time_sync.py
.\venv\Scripts\python.exe tools\test_event_fusion.py
.\venv\Scripts\python.exe tools\test_smart_audio_upload.py
.\venv\Scripts\python.exe tools\test_timestamp_tdoa.py
.\venv\Scripts\python.exe tools\test_gcc_phat.py
.\venv\Scripts\python.exe tools\test_tracking.py
.\venv\Scripts\python.exe tools\test_localization_pipeline.py
.\venv\Scripts\python.exe tools\test_realtime_protocol.py
```

## Local API Smoke

```powershell
.\venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8016
```

Check:

- `/health`
- `/dashboard`
- `/nodes/live`
- `/audio-streams`
- `/time-sync`
- `/event-groups`
- `/localization-results`
- `/tracks`

## Flutter

```powershell
cd C:\Users\vicku\sound_detector_clean
flutter analyze
flutter test
flutter build apk --debug
```

APK:

```text
C:\Users\vicku\sound_detector_clean\build\app\outputs\flutter-apk\app-debug.apk
```

