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
