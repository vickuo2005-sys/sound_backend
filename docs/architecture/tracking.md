# Target Tracking

V4.0 creates target tracks from localization results.

Tracking input:

- `localization_results.status = SUCCESS`
- `estimated_lat`
- `estimated_lng`
- `confidence`
- `event_time_ms`

Fallback localization does not create tracks unless:

```text
TRACK_ALLOW_FALLBACK=true
```

The tracker uses a lightweight alpha-beta / Kalman-style update:

- keeps filtered position
- estimates east/north velocity
- estimates speed and heading
- stores predicted next position

Track association uses label, time gap, speed gate, and uncertainty radius.
