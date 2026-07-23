# Node Control Protocol

Endpoint:

```text
WS /ws/node/{device_id}
Production: wss://sound-backend.onrender.com/ws/node/{device_id}
```

## Envelope

```json
{
  "protocol_version": 1,
  "message_type": "heartbeat",
  "device_id": "node_A01",
  "message_id": "client-generated-id",
  "sent_at_ms": 1780000000000,
  "payload": {}
}
```

## Node To Backend

- `hello`
- `heartbeat`
- `status_update`
- `command_ack`
- `command_result`
- `stream_started`
- `stream_stopped`
- `protocol_error`

## Backend To Node

- `hello_ack`
- `command`
- `start_stream`
- `stop_stream`
- `request_status`
- `ping`
- `protocol_error`

## Command Payload

```json
{
  "command_id": "123",
  "command_type": "START_DETECTION",
  "args": {},
  "issued_at_ms": 1780000000000,
  "expires_at_ms": 1780000030000,
  "idempotency_key": "node_A01:123:uuid"
}
```

## Heartbeat Policy

- Flutter sends heartbeat every 5 seconds.
- Backend status:
  - `ONLINE`: heartbeat age <= 10 seconds
  - `DEGRADED`: heartbeat age > 10 and <= 20 seconds
  - `OFFLINE`: heartbeat age > 20 seconds

Legacy REST command polling remains available.

