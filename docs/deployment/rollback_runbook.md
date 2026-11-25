# Rollback Runbook

## Emergency Feature Flags

- `LIVE_AUDIO_ENABLED=false`
- `COMMAND_WEBSOCKET_ENABLED=false`
- `COMMAND_REST_FALLBACK_ENABLED=true`

## Application Rollback

1. Disable live audio first.
2. Roll Render service back to the previous successful deploy.
3. Confirm `/health` and `/dashboard`.
4. Confirm nodes reconnect or fall back to REST polling.

## Mobile APK Rollback

1. Reinstall previously validated APK with `adb install -r`.
2. Confirm node id and upload mode.
3. Confirm GPS update and event upload.

## Database Failure

Do not destructively revert production schema unless a database backup restore is explicitly approved. Prefer forward-fix migrations and feature flags.

## GCS / Audio Playback Failure

Disable dashboard playback controls if signed URL generation fails, but keep event metadata upload active.

