# V3.1a PCM Timing Metadata

V3.1a adds timing metadata from the Android PCM capture flow. The goal is to preserve sample-index based timing for later localization work without changing the current detection, WAV upload, event fusion, or dashboard alert behavior.

## Scope

The Flutter Android node keeps using Android `AudioRecord` with 16000 Hz mono PCM16 and the existing 2 second pre-buffer. When a candidate event is saved, the app reports where the event starts, ends, and peaks inside the saved WAV using PCM sample indexes.

This version does not implement MP3, time sync, corrected arrival time, TDOA, GCC-PHAT, tracking, or estimated target marker changes.

## Timing Source

`timing_source = PCM_SAMPLE_INDEX` means the event timing was calculated from PCM sample indexes instead of UI timestamps or HTTP request arrival time.

The important formula is:

```text
offset_ms = sample_index * 1000 / sample_rate_hz
device_event_time_ms = capture_start_time_ms + offset_ms(event_start_sample)
```

`capture_start_time_ms` points to the first PCM sample included in the saved WAV. If the WAV contains pre-buffer audio, this timestamp is before the moment the threshold was crossed.

## Event Flow

```text
AudioRecord PCM
-> RMS threshold candidate
-> WAV with pre-buffer saved
-> EventTimingMetadata created from sample indexes
-> AI inference
-> POST /events with timing metadata
-> Event Fusion observation snapshots timing metadata
```

Event Fusion still groups by the existing event timestamp and label. V3.1a only stores timing fields for future localization work.
