# Timestamp TDOA

Timestamp TDOA uses one best observation per device from an Event Group.

Required observation fields:

- `device_id`
- `latitude`
- `longitude`
- `corrected_arrival_time_ms`
- `time_sync_rtt_ms`
- `time_sync_quality`

The solver rejects stale, missing, bad, or high-RTT observations. It then checks
geometry quality and physical feasibility before solving source position.

Equation:

```text
distance(source, node_i) = sound_speed * (arrival_i - emission_time)
```

The solver estimates:

- source east/north position
- emission time

Result fields are stored in `localization_results`.
