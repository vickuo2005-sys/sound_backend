# V3.2 Time Sync

V3.2 adds lightweight clock synchronization between each Flutter Android node
and the FastAPI backend. The goal is to estimate each phone's clock offset and
round-trip latency so later localization work can compare event arrival times
with better context.

## Scope

The app keeps the existing AudioRecord, pre-buffer, AI, upload mode, GPS,
Event Fusion, and Smart Audio Upload behavior. V3.2 only adds time-sync
measurement and status reporting.

This version does not implement NTP, PTP, GCC-PHAT, tracking, or final TDOA
localization.

## Algorithm

The Flutter app periodically calls:

```text
GET /time-sync
```

For each sample:

```text
client_send_ms
server_time_ms
client_receive_ms
```

The app estimates:

```text
rtt_ms = client_receive_ms - client_send_ms
client_midpoint_ms = (client_send_ms + client_receive_ms) / 2
offset_ms = server_time_ms - client_midpoint_ms
```

Each sync run takes three samples and keeps the sample with the lowest RTT.
This is still approximate, but it reduces the chance that one slow HTTP request
becomes the active offset.

## Quality

RTT quality is classified as:

```text
good    <= 50 ms
medium  <= 150 ms
poor    <= 300 ms
bad      > 300 ms
missing  no usable sample
stale    last sync is older than the freshness window
```

The app treats a sync sample as fresh for 120 seconds. If the value is stale,
the app still keeps monitoring and uploading GPS, but reports
`time_sync_quality = stale`.

## Data Flow

```text
Flutter node
-> GET /time-sync, best-of-3 samples
-> store offset / RTT / quality locally
-> POST /location-update with time sync status
-> device_status stores latest per-node sync status
-> Dashboard displays sync quality per node
-> POST /events includes offset / RTT when fresh
-> events and observations keep timing metadata snapshots
```

## Limits

This is not a hard real-time clock synchronization system. It gives the backend
an approximate per-device offset and RTT quality. Later V3.3/V3.4 localization
should still treat high RTT, stale sync, and missing sync as lower-confidence
inputs.
