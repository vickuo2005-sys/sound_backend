# Backend Change Classification

## Core Runtime

- `main.py`
- database fallback and request schema

## Realtime

- `app/protocol/`
- `services/realtime/`
- `/ws/node/{device_id}`
- `/ws/audio/{device_id}`
- `/ws/audio-monitor/{stream_id}`

## Audio

- `/upload-audio`
- `/upload-tdoa-clip`
- signed audio URLs
- live audio binary forwarding

## Dashboard

- `/dashboard`
- live audio monitor UI
- map, alert, localization, track, event group views

## Migration

- `migrations/v2_1_remote_node_management.sql`
- `migrations/v3_0_event_fusion_tracking.sql`
- `migrations/v3_1a_timing_metadata.sql`
- `migrations/v3_1b_smart_audio_upload.sql`
- `migrations/v3_2_time_sync.sql`
- `migrations/v3_3_localization.sql`
- `migrations/v3_4_hybrid_localization.sql`
- `migrations/v4_0_tracking.sql`
- `migrations/v4_final_*.sql`

## Tests

- `tools/test_*.py`
- `tests/test_audio_stream_manager.py`
- `pytest.ini`
- `requirements-dev.txt`

## Documentation

- `docs/architecture/`
- `docs/database/`
- `docs/deployment/`
- `docs/release/`
- `docs/testing/`
- `docs/audit/`

## Pre-existing README Change

`README.md` is dirty and should not be included in a release commit unless explicitly reviewed.

