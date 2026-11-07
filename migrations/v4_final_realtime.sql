-- V4 Final realtime node connectivity, command delivery, and audio streaming.
-- Safe to run multiple times.

CREATE TABLE IF NOT EXISTS device_connections (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    device_id text NOT NULL,
    connection_id text NOT NULL,
    protocol_version integer DEFAULT 1,
    connected_at timestamptz DEFAULT now(),
    last_heartbeat_at timestamptz DEFAULT now(),
    disconnected_at timestamptz,
    disconnect_reason text,
    availability_status text DEFAULT 'ONLINE',
    websocket_connected boolean DEFAULT true,
    recording boolean DEFAULT false,
    detection_enabled boolean DEFAULT false,
    streaming boolean DEFAULT false,
    battery_percent integer,
    gps_available boolean,
    network_type text,
    app_version text,
    reconnect_count integer DEFAULT 0,
    generation integer DEFAULT 1,
    created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now()
);

ALTER TABLE device_connections
ADD COLUMN IF NOT EXISTS device_id text,
ADD COLUMN IF NOT EXISTS connection_id text,
ADD COLUMN IF NOT EXISTS protocol_version integer DEFAULT 1,
ADD COLUMN IF NOT EXISTS connected_at timestamptz DEFAULT now(),
ADD COLUMN IF NOT EXISTS last_heartbeat_at timestamptz DEFAULT now(),
ADD COLUMN IF NOT EXISTS disconnected_at timestamptz,
ADD COLUMN IF NOT EXISTS disconnect_reason text,
ADD COLUMN IF NOT EXISTS availability_status text DEFAULT 'ONLINE',
ADD COLUMN IF NOT EXISTS websocket_connected boolean DEFAULT true,
ADD COLUMN IF NOT EXISTS recording boolean DEFAULT false,
ADD COLUMN IF NOT EXISTS detection_enabled boolean DEFAULT false,
ADD COLUMN IF NOT EXISTS streaming boolean DEFAULT false,
ADD COLUMN IF NOT EXISTS battery_percent integer,
ADD COLUMN IF NOT EXISTS gps_available boolean,
ADD COLUMN IF NOT EXISTS network_type text,
ADD COLUMN IF NOT EXISTS app_version text,
ADD COLUMN IF NOT EXISTS reconnect_count integer DEFAULT 0,
ADD COLUMN IF NOT EXISTS generation integer DEFAULT 1,
ADD COLUMN IF NOT EXISTS created_at timestamptz DEFAULT now(),
ADD COLUMN IF NOT EXISTS updated_at timestamptz DEFAULT now();

CREATE INDEX IF NOT EXISTS device_connections_device_idx
ON device_connections (device_id, updated_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS device_connections_live_connection_idx
ON device_connections (device_id, connection_id);

ALTER TABLE device_commands
ADD COLUMN IF NOT EXISTS command_type text,
ADD COLUMN IF NOT EXISTS args_json jsonb,
ADD COLUMN IF NOT EXISTS issued_at_ms double precision,
ADD COLUMN IF NOT EXISTS expires_at_ms double precision,
ADD COLUMN IF NOT EXISTS idempotency_key text,
ADD COLUMN IF NOT EXISTS acked_at timestamptz,
ADD COLUMN IF NOT EXISTS result_at timestamptz,
ADD COLUMN IF NOT EXISTS result_message text,
ADD COLUMN IF NOT EXISTS delivery_channel text,
ADD COLUMN IF NOT EXISTS delivery_attempts integer DEFAULT 0;

CREATE INDEX IF NOT EXISTS device_commands_status_idx
ON device_commands (device_id, status, created_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS device_commands_idempotency_idx
ON device_commands (idempotency_key)
WHERE idempotency_key IS NOT NULL;

CREATE TABLE IF NOT EXISTS audio_stream_sessions (
    stream_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    device_id text NOT NULL,
    connection_id text,
    codec text,
    sample_rate_hz integer,
    channel_count integer,
    frame_duration_ms integer,
    started_at timestamptz DEFAULT now(),
    stopped_at timestamptz,
    last_frame_at timestamptz,
    received_frames bigint DEFAULT 0,
    dropped_frames bigint DEFAULT 0,
    sequence_gaps bigint DEFAULT 0,
    out_of_order_frames bigint DEFAULT 0,
    malformed_frames bigint DEFAULT 0,
    bytes_received bigint DEFAULT 0,
    subscriber_count integer DEFAULT 0,
    status text DEFAULT 'ACTIVE',
    created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now()
);

ALTER TABLE audio_stream_sessions
ADD COLUMN IF NOT EXISTS device_id text,
ADD COLUMN IF NOT EXISTS connection_id text,
ADD COLUMN IF NOT EXISTS codec text,
ADD COLUMN IF NOT EXISTS sample_rate_hz integer,
ADD COLUMN IF NOT EXISTS channel_count integer,
ADD COLUMN IF NOT EXISTS frame_duration_ms integer,
ADD COLUMN IF NOT EXISTS started_at timestamptz DEFAULT now(),
ADD COLUMN IF NOT EXISTS stopped_at timestamptz,
ADD COLUMN IF NOT EXISTS last_frame_at timestamptz,
ADD COLUMN IF NOT EXISTS received_frames bigint DEFAULT 0,
ADD COLUMN IF NOT EXISTS dropped_frames bigint DEFAULT 0,
ADD COLUMN IF NOT EXISTS sequence_gaps bigint DEFAULT 0,
ADD COLUMN IF NOT EXISTS out_of_order_frames bigint DEFAULT 0,
ADD COLUMN IF NOT EXISTS malformed_frames bigint DEFAULT 0,
ADD COLUMN IF NOT EXISTS bytes_received bigint DEFAULT 0,
ADD COLUMN IF NOT EXISTS subscriber_count integer DEFAULT 0,
ADD COLUMN IF NOT EXISTS status text DEFAULT 'ACTIVE',
ADD COLUMN IF NOT EXISTS created_at timestamptz DEFAULT now(),
ADD COLUMN IF NOT EXISTS updated_at timestamptz DEFAULT now();

CREATE INDEX IF NOT EXISTS audio_stream_sessions_device_idx
ON audio_stream_sessions (device_id, started_at DESC);

