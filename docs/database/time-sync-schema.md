# Time Sync Schema

Migration file:

```text
migrations/v3_2_time_sync.sql
```

Run it in Supabase SQL Editor before deploying the V3.2 backend.

## device_status

Nullable fields added:

```text
time_sync_offset_ms DOUBLE PRECISION
time_sync_rtt_ms DOUBLE PRECISION
time_sync_quality TEXT
time_sync_at TIMESTAMPTZ
last_time_sync_at TIMESTAMPTZ
```

These fields store the latest per-device sync state reported by
`POST /location-update`. `time_sync_at` is the primary V3.2 field;
`last_time_sync_at` is kept for backward compatibility with earlier local
builds.

## events

Nullable V3.2 snapshot fields:

```text
time_sync_version INTEGER
time_sync_offset_ms DOUBLE PRECISION
time_sync_rtt_ms DOUBLE PRECISION
time_sync_quality TEXT
time_sync_synced_at_ms BIGINT
time_sync_age_ms BIGINT
corrected_arrival_time_ms DOUBLE PRECISION
```

`corrected_arrival_time_ms` follows:

```text
corrected_arrival_time_ms = device_event_time_ms + time_sync_offset_ms
```

The sign convention is `server_time_ms - device_time_ms = time_sync_offset_ms`.
If an event snapshot is older than `TIME_SYNC_MAX_AGE_SECONDS`, the event keeps
the offset and corrected arrival time for diagnostics, but its effective
`time_sync_quality` becomes `stale`.

## event_group_observations

The same nullable fields are copied into each observation as a snapshot. This
keeps Event Fusion independent from later `device_status` updates.

## API Payload

`POST /location-update` now accepts:

```json
{
  "device_id": "node_A01",
  "latitude": 25.033,
  "longitude": 121.565,
  "time_sync_offset_ms": 12.5,
  "time_sync_rtt_ms": 42.3,
  "time_sync_quality": "good",
  "time_sync_at": "2026-07-18T12:00:00.000Z",
  "last_time_sync_at": "2026-07-18T12:00:00.000Z"
}
```

Existing fields remain valid and all new fields are nullable for backward
compatibility.

`POST /events` accepts the event-time snapshot:

```json
{
  "event_id": "event_001",
  "device_id": "node_A01",
  "timestamp": "2026-07-18T12:00:00.000Z",
  "device_event_time_ms": 1784656000000,
  "time_sync_version": 1,
  "time_sync_offset_ms": 12.5,
  "time_sync_rtt_ms": 42.3,
  "time_sync_quality": "good",
  "time_sync_synced_at_ms": 1784655999000,
  "time_sync_age_ms": 1000
}
```

## Safe Migration

The migration uses `ADD COLUMN IF NOT EXISTS` and `CREATE INDEX IF NOT EXISTS`,
so it can be run more than once.

```sql
ALTER TABLE device_status
ADD COLUMN IF NOT EXISTS time_sync_offset_ms DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS time_sync_rtt_ms DOUBLE PRECISION,
ADD COLUMN IF NOT EXISTS time_sync_quality TEXT,
ADD COLUMN IF NOT EXISTS time_sync_at TIMESTAMPTZ,
ADD COLUMN IF NOT EXISTS last_time_sync_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS device_status_time_sync_quality_idx
ON device_status (time_sync_quality);
```

The same migration also safely adds the event snapshot columns to `events` and
`event_group_observations`.
