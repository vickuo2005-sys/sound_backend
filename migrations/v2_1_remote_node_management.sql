-- Sound Detector Backend V2.1
-- Remote node status and command management.

CREATE TABLE IF NOT EXISTS device_status (
    device_id TEXT PRIMARY KEY,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    last_seen TIMESTAMPTZ DEFAULT now(),
    status TEXT DEFAULT 'online',
    is_listening BOOLEAN,
    upload_mode TEXT,
    battery INTEGER,
    ai_status TEXT,
    backend_status TEXT,
    app_status TEXT,
    last_ai_label TEXT,
    last_upload_status TEXT,
    last_event_id TEXT,
    last_event_at TIMESTAMPTZ,
    last_command_id BIGINT,
    updated_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE device_status ADD COLUMN IF NOT EXISTS latitude DOUBLE PRECISION;
ALTER TABLE device_status ADD COLUMN IF NOT EXISTS longitude DOUBLE PRECISION;
ALTER TABLE device_status ADD COLUMN IF NOT EXISTS last_seen TIMESTAMPTZ DEFAULT now();
ALTER TABLE device_status ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'online';
ALTER TABLE device_status ADD COLUMN IF NOT EXISTS is_listening BOOLEAN;
ALTER TABLE device_status ADD COLUMN IF NOT EXISTS upload_mode TEXT;
ALTER TABLE device_status ADD COLUMN IF NOT EXISTS battery INTEGER;
ALTER TABLE device_status ADD COLUMN IF NOT EXISTS ai_status TEXT;
ALTER TABLE device_status ADD COLUMN IF NOT EXISTS backend_status TEXT;
ALTER TABLE device_status ADD COLUMN IF NOT EXISTS app_status TEXT;
ALTER TABLE device_status ADD COLUMN IF NOT EXISTS last_ai_label TEXT;
ALTER TABLE device_status ADD COLUMN IF NOT EXISTS last_upload_status TEXT;
ALTER TABLE device_status ADD COLUMN IF NOT EXISTS last_event_id TEXT;
ALTER TABLE device_status ADD COLUMN IF NOT EXISTS last_event_at TIMESTAMPTZ;
ALTER TABLE device_status ADD COLUMN IF NOT EXISTS last_command_id BIGINT;
ALTER TABLE device_status ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT now();

CREATE TABLE IF NOT EXISTS device_commands (
    id BIGSERIAL PRIMARY KEY,
    device_id TEXT NOT NULL,
    command TEXT NOT NULL,
    value TEXT,
    status TEXT DEFAULT 'pending',
    issued_by TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    executed_at TIMESTAMPTZ,
    ack_message TEXT
);

ALTER TABLE device_commands ADD COLUMN IF NOT EXISTS device_id TEXT;
ALTER TABLE device_commands ADD COLUMN IF NOT EXISTS command TEXT;
ALTER TABLE device_commands ADD COLUMN IF NOT EXISTS value TEXT;
ALTER TABLE device_commands ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'pending';
ALTER TABLE device_commands ADD COLUMN IF NOT EXISTS issued_by TEXT;
ALTER TABLE device_commands ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT now();
ALTER TABLE device_commands ADD COLUMN IF NOT EXISTS executed_at TIMESTAMPTZ;
ALTER TABLE device_commands ADD COLUMN IF NOT EXISTS ack_message TEXT;

CREATE INDEX IF NOT EXISTS device_commands_pending_idx
ON device_commands (device_id, status, created_at);
