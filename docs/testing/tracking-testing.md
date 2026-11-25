# Tracking Testing

Run:

```powershell
cd C:\sound_backend
.\venv\Scripts\python.exe tools\test_tracking.py
```

Smoke routes:

- `GET /tracks`
- `GET /tracks/{track_id}`
- `GET /tracks/{track_id}/points`
- `POST /tracks/{track_id}/close`

Expected:

- first localization creates a track
- following nearby localization associates to the same track
- filtered position, speed, heading, and predicted point are stored
