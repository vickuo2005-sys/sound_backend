# Event Audio Reliability

Event audio remains separate from live audio.

## Reliable Path

```mermaid
sequenceDiagram
    participant Node
    participant Backend
    participant GCS
    participant DB

    Node->>Backend: POST /events metadata
    Backend->>DB: upsert event
    Backend-->>Node: metadata accepted
    Node->>Backend: POST /upload-audio MP3
    Backend->>GCS: store complete event MP3
    Backend->>DB: update audio_path
    Node->>Backend: POST /upload-tdoa-clip WAV
    Backend->>GCS: store short PCM WAV clip
    Backend->>DB: update tdoa_clip_path
```

## Current Guarantees

- Event metadata uses idempotent `event_id`.
- MP3 path is for Dashboard playback.
- WAV clip path is for future GCC-PHAT.
- Signed URLs are generated only on request.

## Future Flutter Queue

The final architecture expects an offline upload queue with retry count, checksum, next retry time, and upload state. This pass keeps the existing upload flow and documents the queue requirement.

