# GCC-PHAT

GCC-PHAT estimates pairwise lag from PCM WAV localization clips.

## Requirements

- Same or resampled sample rate.
- Mono PCM signal.
- Clip timing metadata:
  - `tdoa_clip_start_sample`
  - `tdoa_clip_end_sample`
  - `tdoa_clip_peak_sample`
  - `tdoa_clip_duration_ms`

## Pair Result

Each pair can produce:

- device_a
- device_b
- lag_samples
- lag_seconds
- correlation_score
- accepted
- rejection_reason
- max physical lag

## Current Status

The backend parser and synthetic GCC-PHAT test are implemented. Production hybrid usage is controlled by `GCC_PHAT_ENABLED`.

