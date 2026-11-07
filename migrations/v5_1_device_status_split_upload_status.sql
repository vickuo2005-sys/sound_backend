BEGIN;

ALTER TABLE device_status
    ADD COLUMN IF NOT EXISTS backend_http_status text,
    ADD COLUMN IF NOT EXISTS node_websocket_status text,
    ADD COLUMN IF NOT EXISTS metadata_upload_status text,
    ADD COLUMN IF NOT EXISTS audio_upload_status text,
    ADD COLUMN IF NOT EXISTS gps_upload_status text,
    ADD COLUMN IF NOT EXISTS last_location_upload_at timestamptz;

UPDATE device_status
SET
    backend_http_status = COALESCE(backend_http_status, backend_status),
    metadata_upload_status = COALESCE(metadata_upload_status, last_upload_status)
WHERE
    backend_http_status IS NULL
    OR metadata_upload_status IS NULL;

COMMIT;
