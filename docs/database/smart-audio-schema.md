# V3.1b Smart Audio Schema

Run this migration in Supabase SQL Editor before deploying V3.1b:

```text
C:\sound_backend\migrations\v3_1b_smart_audio_upload.sql
```

The migration is safe to run more than once because it only uses
`ADD COLUMN IF NOT EXISTS`.

## Columns Added To events

- `audio_format TEXT`
- `audio_size_bytes BIGINT`
- `source_pcm_size_bytes BIGINT`
- `audio_encoding_status TEXT`
- `tdoa_clip_path TEXT`
- `tdoa_clip_format TEXT`
- `tdoa_clip_size_bytes BIGINT`
- `tdoa_clip_start_sample BIGINT`
- `tdoa_clip_end_sample BIGINT`
- `tdoa_clip_peak_sample BIGINT`
- `tdoa_clip_duration_ms INTEGER`
- `tdoa_clip_source TEXT`

## Columns Added To event_group_observations

The same fields are added to `event_group_observations` so each observation
keeps a snapshot of the audio upload metadata.

When the same `event_id` is posted again after background audio upload,
Event Fusion updates the existing observation snapshot instead of inserting a
duplicate observation.

## Compatibility

Old rows can leave all new fields as `NULL`.

Legacy WAV events continue to use:

- `audio_path`
- `audio_format = wav` when known, otherwise inferred from the object path.

New MP3 primary events use:

- `audio_path`
- `audio_format = mp3`
- `audio_size_bytes`

Short localization clips use:

- `tdoa_clip_path`
- `tdoa_clip_format = wav`
- `tdoa_clip_size_bytes`
- `tdoa_clip_*_sample`
