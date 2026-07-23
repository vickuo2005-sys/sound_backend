# Render Deployment Notes

## Build

```text
pip install -r requirements.txt
```

## Start

```text
uvicorn main:app --host 0.0.0.0 --port $PORT
```

## Environment Variables

- `DATABASE_URL`
- `GCS_BUCKET_NAME`
- `GOOGLE_APPLICATION_CREDENTIALS_JSON`
- `GOOGLE_MAPS_API_KEY`
- `UPLOAD_TOKEN`
- `NODE_WEBSOCKET_ENABLED`
- `COMMAND_WEBSOCKET_ENABLED`
- `LIVE_AUDIO_ENABLED`
- `LOCALIZATION_ENABLED`
- `GCC_PHAT_ENABLED`
- `TRACKING_ENABLED`

## Worker Count

Use one Render worker for the current in-memory WebSocket managers.

Multiple workers require Redis/pub-sub or sticky routing.

## Deployment Order

1. Run Supabase migrations.
2. Push backend to GitHub.
3. Wait for Render deployment.
4. Smoke test:
   - `/health`
   - `/dashboard`
   - `/nodes/live`
   - `/audio-streams`
   - `/event-groups`
   - `/localization-results`
   - `/tracks`

