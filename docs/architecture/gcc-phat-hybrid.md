# GCC-PHAT / Hybrid Localization

V3.4 adds the waveform tools needed for short WAV clip localization.

MP3 is never used for timing. Only `tdoa_clip_path` WAV clips are eligible for
GCC-PHAT.

Current behavior:

- Read 16-bit PCM WAV.
- Convert stereo to mono for analysis.
- Estimate pairwise lag using GCC-PHAT.
- If enough valid clip pairs exist, attempt hybrid TDOA.
- If clip loading or correlation fails, fall back to timestamp TDOA.

The feature is guarded by:

```text
GCC_PHAT_ENABLED=false
GCC_MIN_CORRELATION_SCORE=0.04
```

This keeps production uploads safe while the waveform pipeline is still being
verified.
