# Tracking Schema

Migration file:

```text
migrations/v4_0_tracking.sql
```

Tables:

- `target_tracks`
- `target_track_points`

`target_tracks` stores active or closed track summaries. `target_track_points`
stores every measurement update, filtered position, predicted position, speed,
heading, and diagnostics.

Important fields:

- `last_lat`
- `last_lng`
- `last_speed_mps`
- `last_heading_deg`
- `velocity_east_mps`
- `velocity_north_mps`
- `point_count`
- `status`
