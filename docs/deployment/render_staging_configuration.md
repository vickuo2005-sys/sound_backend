# Render Staging Configuration Audit

## Required Shape

- Service type: Web Service
- Runtime: Python
- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT --workers 1`
- Health check: `/health`
- Worker count: 1

## Why One Worker

`NodeManager` and `AudioStreamManager` are in-memory managers. Multiple workers would split node connections, command push, live audio sessions, and dashboard subscribers across processes. Staging and production should run one worker until a shared broker is added.

## WebSocket Readiness

- Node WebSocket: `/ws/node/{device_id}`
- Audio upload WebSocket: `/ws/audio/{device_id}`
- Dashboard monitor WebSocket: `/ws/audio-monitor/{stream_id}`
- Dashboard event WebSocket: `/ws/dashboard`

Render restart will disconnect nodes. Nodes must reconnect and REST polling fallback must remain enabled.

## Feature Flags

Start staging with:

- `NODE_WEBSOCKET_ENABLED=true`
- `COMMAND_WEBSOCKET_ENABLED=true`
- `COMMAND_REST_FALLBACK_ENABLED=true`
- `LIVE_AUDIO_ENABLED=false`

Only enable `LIVE_AUDIO_ENABLED=true` after baseline node command and event upload checks pass.

## Production Caution

Do not point staging to production Supabase or production GCS. Do not paste service account JSON into files.

