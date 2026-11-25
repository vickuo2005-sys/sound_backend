# Integration Environment Correction Report

Date: 2026-07-24

## Environment Model

The current cloud resources are development/integration resources, not production:

- Render: `https://sound-backend.onrender.com`
- Supabase: existing project
- GCS: existing bucket

No second Supabase project, GCS bucket, or `sound-backend-staging` Render service is required for the current project testing phase.

## Guard Changes

| Area | Change |
| --- | --- |
| Flutter `AppConfig` | Removed the rule that rejected `staging` configs pointing at `sound-backend.onrender.com`. |
| Flutter development config | Remote development backends must use HTTPS; localhost remains allowed for local dev. |
| Flutter config validator | Added `development` as a valid environment and removed the false production-host rejection for internal-test builds. |
| Flutter internal-test build script | `tools\build_staging_apk.ps1` now defaults to `APP_ENV=development` while keeping the `staging` Android flavor/applicationId. |
| Flutter local config | `config\staging.local.json` now points to `https://sound-backend.onrender.com` with `APP_ENV=development`. Tokens remain external and are not printed. |
| Backend target validator | Updated to validate the current integration target instead of requiring separate staging cloud resources. |
| Backend env validator | Allows `APP_ENV=development`, `integration`, or `staging`, and no longer rejects existing bucket `sound-detector`. |
| Render YAML | Prepared for existing service `sound_backend` with `APP_ENV=development`, one worker, and `LIVE_AUDIO_ENABLED=false`. |

## Security Preserved

| Control | Status |
| --- | --- |
| No hardcoded `test-token-123` runtime credential | Preserved |
| `AppConfig` and `--dart-define-from-file` | Preserved |
| Missing token fails validation | Preserved |
| Demo token rejected | Preserved |
| HTTPS/WSS for remote backend | Preserved |
| Internal-test debug signing allowed | Preserved |
| Production release signing checks | Preserved |
| Git ignores local config/secrets/APKs | Preserved |

## Existing Render Readiness

Read-only checks against `https://sound-backend.onrender.com`:

| Endpoint | Status |
| --- | --- |
| `/health` | 200 |
| `/dashboard` | 200 |
| `/time-sync` | 200 |
| `/event-groups` | 200 |
| `/device-status` | 200 |
| `/events` | 200 |
| `/nodes/live` | 200 |
| `/audio-streams` | 200 |
| `/localization-results` | 200 |
| `/tracks` | 200 |
| `/ws/node/{device_id}` smoke without token | 403, expected until smoke tool sends node auth token |

Conclusion: the existing Render service is alive and is running the current V4 API surface for dashboard, realtime node status, localization results, tracks, and audio stream session metadata.

## Existing GCS Compatibility

Signed URL checks were read-only and did not upload, delete, or mutate objects.

| Artifact | Result |
| --- | --- |
| MP3 primary audio signed URL | OK, `audio/mpeg`, HTTP 200 |
| Legacy WAV primary audio signed URL | OK, `audio/wav`, HTTP 200 |
| TDOA clip WAV signed URL | OK, `audio/wav`, HTTP 200 |

Conclusion: existing Render credentials and GCS bucket configuration can generate playback signed URLs for MP3, legacy WAV, and TDOA clip WAV.

## Validation

| Command | Result |
| --- | --- |
| Backend compileall | Pass |
| Backend pytest | Pass, 4 tests |
| Backend realtime protocol test | Pass |
| Backend local stress/smoke | Pass |
| Flutter config validation | Pass, `APP_ENV=development`, backend `sound-backend.onrender.com` |
| Flutter format check | Pass |
| Flutter analyze | Pass |
| Flutter test | Pass, 22 tests |
| Flutter debug APK build | Pass |

## Internal-Test APK

| Field | Value |
| --- | --- |
| Path | `C:\Users\vicku\sound_detector_clean\build\app\outputs\flutter-apk\app-debug.apk` |
| SHA-256 | Recompute after final release packaging if needed |
| Size | Recompute after final release packaging if needed |
| applicationId | `com.example.sound_detector_clean` |
| versionName | Debug build |
| versionCode | Debug build |
| Signing | Debug signing |
| Certificate SHA-256 | Recompute for release signing if needed |
| Runtime env | `development` |
| Backend | `https://sound-backend.onrender.com` |
| Node WebSocket | `wss://sound-backend.onrender.com/ws/node/{device_id}` |
| Audio WebSocket | `wss://sound-backend.onrender.com/ws/audio/{device_id}` |

## Not Performed

- No schema-changing migration was executed.
- Render deployment is handled by pushing the backend `staging` branch to GitHub.
- No GCS upload/delete/move was performed.
- Backend Git commits were pushed for the current dashboard and validation fixes.
- Flutter changes were committed locally; this repository currently has no Git remote configured.
