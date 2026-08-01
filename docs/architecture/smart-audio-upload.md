# V3.1b Smart Audio Upload

V3.1b only changes the audio upload package around each accepted sound event.
It does not change AudioRecord monitoring, AI inference, detection/collection mode,
event fusion grouping, GPS updates, time sync, TDOA, GCC-PHAT, or tracking.

## Flow

```text
Android AudioRecord PCM
  -> RMS / AI / V3.1a timing metadata from original PCM
  -> save full event WAV locally
  -> POST /events immediately for dashboard alert
  -> background smart audio pipeline
       -> full event WAV -> MP3 primary audio
       -> POST /upload-audio
       -> POST /events again with the same event_id to refresh audio metadata
```

The second `/events` call is an idempotent update. It refreshes `events` and the
existing `event_group_observations` snapshot, but it must not create a new
observation or retrigger dashboard alerts.

## Primary Audio

The primary event audio is used for Dashboard playback and human review.

- Format: MP3 when encoding succeeds.
- Bitrate: 64 kbps CBR.
- Channel: mono.
- Fallback: none for current production nodes. If MP3 encoding fails, metadata
  remains saved and the audio upload is retried/flagged instead of uploading WAV.
- GCS path: `audio/{drone|other}/{device_id}/{YYYYMMDD}/{event_id}.mp3`

MP3 is not used for timing, TDOA, GCC-PHAT, or AI. It is only a storage and
playback artifact.

## TDOA Clip Compatibility

Current production nodes no longer upload the short WAV clip because the system
is not using WAV cross-correlation. The backend keeps nullable `tdoa_clip_*`
fields and the legacy `/upload-tdoa-clip` endpoint so older records remain
readable, but new app uploads should leave those fields empty.

Historical V3.1b clip behavior was:

- Source: original PCM WAV.
- Center: `rms_peak_sample` when available.
- Window: 1 second before peak plus 1 second after peak.
- Format: original sample rate, channel count, and PCM 16-bit WAV.
- GCS path: `audio/{drone|other}/{device_id}/{YYYYMMDD}/{event_id}_tdoa_clip.wav`

Clip indexes are frame indexes relative to the full event PCM:

- `tdoa_clip_start_sample`: inclusive start frame.
- `tdoa_clip_end_sample`: exclusive end frame.
- `tdoa_clip_peak_sample`: peak frame inside the clip.
- `tdoa_clip_duration_ms`: clip duration in milliseconds.

If `rms_peak_sample` is unavailable, the app falls back to `event_start_sample`,
then the event center.
