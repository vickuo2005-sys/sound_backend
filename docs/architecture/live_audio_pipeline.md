# Live Audio Pipeline

```mermaid
sequenceDiagram
    participant Dashboard
    participant Backend
    participant Node

    Dashboard->>Backend: POST /device-command START_LIVE_AUDIO
    Backend->>Backend: create stream_id + stream_token
    Backend->>Node: WS command START_LIVE_AUDIO
    Node->>Backend: command_ack accepted
    Node->>Backend: WS /ws/audio/{device_id} with headers
    Backend->>Node: audio_stream_ready
    Node->>Backend: binary PCM S16LE frames
    Dashboard->>Backend: POST /device-command STOP_LIVE_AUDIO
    Backend->>Node: WS command STOP_LIVE_AUDIO
    Node->>Backend: command_result success
```

## Codec

Current implemented fallback:

- codec: `pcm_s16le`
- sample rate: 16000 Hz
- channels: mono
- sample width: 16-bit signed little-endian

Opus remains the preferred future codec, but PCM fallback is the implemented interoperable path.

## Audio Capture Fan-Out

Android keeps one `AudioRecord` source:

```mermaid
flowchart TD
    PCM["AudioRecord PCM buffer"]
    RMS["RMS / threshold"]
    Event["Event WAV / MP3"]
    Clip["TDOA WAV clip"]
    Live["Live PCM frames"]

    PCM --> RMS
    PCM --> Event
    PCM --> Clip
    PCM --> Live
```

Live frames are best-effort and are not written to PostgreSQL or GCS.

