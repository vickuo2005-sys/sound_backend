# Final System Architecture

```mermaid
flowchart LR
    Node["Flutter Android Node"]
    Control["WSS /ws/node/{device_id}<br/>Node control, heartbeat, command push"]
    Audio["WSS /ws/audio/{device_id}<br/>Binary Opus/PCM live frames"]
    Rest["HTTPS REST<br/>events, audio upload, GPS, time sync"]
    Backend["FastAPI Backend"]
    Db["Supabase PostgreSQL"]
    Gcs["Google Cloud Storage"]
    DashWs["WSS /ws/dashboard"]
    Dashboard["Dashboard"]

    Node --> Control --> Backend
    Node --> Audio --> Backend
    Node --> Rest --> Backend
    Backend --> Db
    Backend --> Gcs
    Backend --> DashWs --> Dashboard
    Dashboard --> Backend
```

## Backend Services

- `NodeManager`: live node connection state, heartbeat, duplicate connection policy, command delivery.
- `RealtimeCommandService`: WebSocket command push with REST polling fallback.
- `AudioStreamManager`: validates binary frame headers, tracks sequence gaps, backpressure drops, and stream stats.
- `EventFusionService`: groups multiple node observations.
- `LocalizationService`: Timestamp TDOA, GCC-PHAT-ready refinement, hybrid fallback.
- `TrackingService`: target track association and filtered movement state.

## Runtime Channels

- Node Control WebSocket: reliable low-volume control plane.
- Audio WebSocket: best-effort live monitoring plane, not used for TDOA persistence.
- HTTPS REST: reliable metadata, event audio, GPS, Time Sync, and fallback command polling.
- Dashboard WebSocket: live visual update plane.

## Render Constraint

The current realtime managers are in-memory. Use one Render worker. If scaling to multiple workers, add Redis pub/sub or sticky routing.

