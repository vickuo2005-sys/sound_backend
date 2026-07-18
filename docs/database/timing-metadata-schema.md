# Timing Metadata Schema

Migration file:

```text
migrations/v3_1a_timing_metadata.sql
```

Run it in Supabase SQL Editor before deploying the backend.

## events

Nullable fields added:

```text
timing_version INTEGER
timing_source TEXT
capture_start_time_ms BIGINT
event_start_sample BIGINT
event_end_sample BIGINT
rms_peak_sample BIGINT
sample_rate_hz INTEGER
channel_count INTEGER
rms_peak_time_ms BIGINT
```

Existing timing-like fields such as `device_event_time_ms`, `event_end_time_ms`, and `audio_duration_ms` are preserved for backward compatibility.

## event_group_observations

Nullable fields added:

```text
timing_version INTEGER
timing_source TEXT
capture_start_time_ms BIGINT
event_start_sample BIGINT
event_end_sample BIGINT
rms_peak_sample BIGINT
sample_rate_hz INTEGER
channel_count INTEGER
audio_duration_ms BIGINT
device_event_time_ms BIGINT
event_end_time_ms BIGINT
rms_peak_time_ms BIGINT
```

Observations copy these values from the persisted event record. This keeps each fusion observation as a snapshot of the event timing metadata.

## Safety

All new columns are nullable and added with `ADD COLUMN IF NOT EXISTS`, so old events and old APP payloads continue to work.
