# Phase 4 staging environment variables

This inventory is based on variables read by `main.py` and Flutter
`AppConfig`/`main.dart`. Empty examples are not proof that a cloud secret is
configured.

## Backend required for Phase 4

| Variable | Secret | Source | Required staging value / note |
|---|---:|---|---|
| `APP_ENV` | No | Manual | `staging`; deployment identity marker. Current backend code does not expose it from `/health`, so also verify it in Render. |
| `DATABASE_URL` | Yes | Supabase | Isolated staging Session pooler URI; never a production URI. |
| `POSTGRES_SCHEMA_AUTO_INIT` | No | Fixed | `false`; apply reviewed migrations explicitly. |
| `UPLOAD_TOKEN` | Yes | Generated | Staging-only random token shared with Flutter. |
| `DASHBOARD_WRITE_TOKEN_REQUIRED` | No | Fixed | `true`. |
| `DASHBOARD_ADMIN_TOKEN` | Yes | Generated | Staging-only dashboard write token. The code does not read `DASHBOARD_WRITE_TOKEN`. |
| `GCS_BUCKET_NAME` | No | GCS | Staging-only bucket if target detections can use existing audio upload paths. |
| `GOOGLE_APPLICATION_CREDENTIALS_JSON` | Yes | GCS | JSON for a staging-only service account with access only to the staging bucket. |
| `GOOGLE_MAPS_API_KEY` | Yes | Manual | Browser-restricted staging key when the map is required. |

Backend Phase 4 flags:

| Variable | Value |
|---|---|
| `FAST_EVENT_INGEST_ENABLED` | `true` |
| `POST_INFERENCE_LATENCY_TRACING_ENABLED` | `true` |
| `OBSERVATION_SHADOW_ENABLED` | `true` |
| `OBSERVATION_TRACKING_ENABLED` | `true` |
| `TRACKING_ENABLED` | `true` |
| `TRACKING_REORDER_BUFFER_ENABLED` | `false` |
| `STAGING_DB_LATENCY_PROBE_ENABLED` | `false`, except during a bounded authenticated DB probe |
| `NODE_WEBSOCKET_ENABLED` | `true` |
| `COMMAND_WEBSOCKET_ENABLED` | `true` |
| `COMMAND_REST_FALLBACK_ENABLED` | `true` |
| `LIVE_AUDIO_ENABLED` | `false` for the first smoke |

Backend Observation replay policy (staging only until field acceptance):

| Variable | Value | Meaning |
|---|---:|---|
| `OBSERVATION_LIVE_MAX_AGE_MS` | `5000` | Upper age for `live`. |
| `OBSERVATION_LIVE_TRACKING_MAX_AGE_MS` | `120000` | Upper age for replay into shadow tracking. |
| `OBSERVATION_HISTORICAL_MAX_AGE_MS` | `21600000` | Six-hour historical/expired boundary. |
| `OBSERVATION_IDEMPOTENCY_TTL_SECONDS` | `21600` | Six-hour in-memory duplicate tombstone retention. |
| `OBSERVATION_IDEMPOTENCY_MAX_IDS` | `50000` | Bounded tombstone capacity. |

The remaining sizing/TTL variables in `.env.staging.example` have safe code
defaults but are pinned there for repeatability.

## Flutter required

| Key | Secret | Source | Note |
|---|---:|---|---|
| `APP_ENV` | No | Fixed | `staging` |
| `BACKEND_BASE_URL` | No | Render | Actual approved staging HTTPS origin |
| `UPLOAD_TOKEN` | Yes | Generated | Must exactly match Render staging |
| `DEVICE_TOKEN` | Yes | Generated | Required by current `AppConfig`; currently not sent to the backend |
| `LIVE_AUDIO_ENABLED` | No | Fixed | `false` |
| `COMMAND_WEBSOCKET_ENABLED` | No | Fixed | `true` |
| `REST_FALLBACK_ENABLED` | No | Fixed | `true` |
| `FAST_METADATA_UPLOAD_ENABLED` | No | Fixed | `true` |
| `PERSISTENT_METADATA_HTTP_CLIENT_ENABLED` | No | Fixed | `true` |
| `POST_INFERENCE_LATENCY_TRACING_ENABLED` | No | Fixed | `true` |
| `OBSERVATION_SHADOW_ENABLED` | No | Fixed | `true` |

`OBSERVATION_TRACKING_ENABLED` is a backend-only variable and must not be
added to Flutter JSON as if the app read it.

## Not used by current code

- `STREAM_TOKEN_SECRET`
- `DASHBOARD_AUTH_SECRET`
- `DASHBOARD_WRITE_TOKEN` (use `DASHBOARD_ADMIN_TOKEN`)
- Supabase URL/API key for the backend (the backend uses `DATABASE_URL`)

Do not configure unused names to imply protection that the application does
not enforce.

## Local generation versus manual input

`tools/generate_staging_secrets.ps1` can generate `UPLOAD_TOKEN`,
`DEVICE_TOKEN`, and `DASHBOARD_ADMIN_TOKEN` with the platform cryptographic
random-number generator. Its output and inventory files are ignored and it
refuses to overwrite an existing file.

The operator must supply the Supabase database URI, actual Render hostname,
staging GCS project/bucket/service-account JSON, and any restricted Maps key.
No secret belongs in Git, docs, tests, command arguments, build logs, or field
evidence.
