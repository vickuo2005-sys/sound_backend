# Localization Testing

Run:

```powershell
cd C:\sound_backend
.\venv\Scripts\python.exe tools\test_timestamp_tdoa.py
.\venv\Scripts\python.exe tools\test_gcc_phat.py
.\venv\Scripts\python.exe tools\test_localization_pipeline.py
```

Smoke routes:

- `GET /localization-results`
- `GET /event-groups/{group_id}/localization`
- `POST /event-groups/{group_id}/localize`

Expected:

- timestamp TDOA succeeds for synthetic 3+ node geometry
- stale sync falls back
- GCC-PHAT recovers synthetic sample delay
- full pipeline creates Event Group, Localization Result, and Track
