# Audio Binary Protocol

Endpoint:

```text
WS /ws/audio/{device_id}
```

The endpoint is guarded by:

```text
LIVE_AUDIO_ENABLED=false
```

## Header Layout

Network byte order, fixed header length: 52 bytes.

| Field | Type | Description |
|---|---:|---|
| magic | 4 bytes | `SDAF` |
| protocol_version | uint8 | currently `1` |
| flags | uint8 | reserved |
| header_length | uint16 | `52` |
| stream_id | 16 bytes | UUID bytes |
| sequence_number | uint64 | monotonic per stream |
| capture_timestamp_us | uint64 | node capture timestamp |
| sample_rate_hz | uint32 | audio sample rate |
| channel_count | uint16 | 1 or 2 |
| codec_id | uint8 | 1 = pcm16, 2 = opus |
| frame_duration_ms | uint8 | typical 20 ms |
| payload_length | uint32 | payload byte count |

## Validation

The backend validates magic, protocol version, header length, codec, sample rate, channel count, duration, frame size, and payload length.

Malformed frames increment counters and do not crash the server.

## Storage Rule

Live audio frames are not written to PostgreSQL or GCS. Event MP3 and WAV clips remain the reliable evidence path.

