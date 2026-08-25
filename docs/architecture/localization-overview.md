# Localization Overview

V3.3 to V4 adds a backend localization and tracking layer after Event Fusion.

Flow:

```text
POST /events
-> Event Fusion group
-> localization_results
-> target_tracks
-> Dashboard map
```

The APP still uploads HTTP events, MP3 audio, short WAV clips, GPS, and command
status exactly as before. The backend now uses the existing
`event_group_observations` snapshots as localization input.

## Stages

- V3.3: timestamp-based TDOA using `corrected_arrival_time_ms`.
- V3.4: GCC-PHAT helpers for short WAV clips and hybrid localization fallback.
- V4.0: Kalman-style target tracks from successful localization results.

Fallback localization is stored for diagnostics, but it does not feed tracking
unless `TRACK_ALLOW_FALLBACK=true`.
