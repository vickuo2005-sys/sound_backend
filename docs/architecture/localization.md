# Localization Architecture

## Pipeline

```mermaid
flowchart TD
    Event["POST /events"]
    Fusion["Event Fusion"]
    Observations["event_group_observations"]
    Timestamp["Timestamp TDOA"]
    GCC["GCC-PHAT refinement"]
    Hybrid["Hybrid localization"]
    Result["localization_results"]
    Track["TrackingService"]

    Event --> Fusion --> Observations --> Timestamp --> Hybrid --> Result --> Track
    Observations --> GCC --> Hybrid
```

## Timestamp TDOA

Uses `corrected_arrival_time_ms`, GPS coordinates, speed of sound, and nonlinear least squares over source position and emission time.

## GCC-PHAT

Uses only PCM WAV TDOA clips. MP3 and live Opus are not used for waveform localization.

## Result Fields

- estimated latitude / longitude
- method
- status
- confidence
- residual
- uncertainty radius
- geometry quality
- reference device
- node count
- diagnostics JSON

