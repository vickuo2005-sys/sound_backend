# Timing Metadata Testing

## Flutter

Run from:

```powershell
cd C:\Users\vicku\sound_detector_clean
flutter analyze
flutter test
```

The timing unit test checks:

- `16000` samples at `16000 Hz` equals `1000 ms`
- `8000` samples at `16000 Hz` equals `500 ms`
- `4410` samples at `44100 Hz` equals `100 ms`
- JSON field names match the backend contract
- invalid sample metadata is ignored safely

## Backend

Run from:

```powershell
cd C:\sound_backend
.\venv\Scripts\python.exe -m compileall main.py services tools
.\venv\Scripts\python.exe tools\test_event_fusion.py
.\venv\Scripts\python.exe tools\test_tdoa_solver.py
```

The backend event fusion test checks:

- old-style events still persist
- events with timing metadata persist successfully
- timing metadata is copied into `event_group_observations`
- `/events` still succeeds even if event fusion raises an internal error

## Manual API Check

After Supabase migration and Render deploy:

```text
GET https://sound-backend.onrender.com/health
GET https://sound-backend.onrender.com/event-groups
GET https://sound-backend.onrender.com/dashboard
```

Send one APP event and open an event group detail. Observation rows should show Timing Source, Device Event Time, Event Start Sample, RMS Peak Sample, Sample Rate, and Audio Duration.
