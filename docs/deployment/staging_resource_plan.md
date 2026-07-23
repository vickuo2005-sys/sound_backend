# Staging Resource Plan

This plan prepares staging resource creation. It does not create resources.

## Target Names

| Resource | Planned identity |
| --- | --- |
| Supabase | `sound-detector-staging` |
| GCS bucket | `sound-detector-staging-<unique-suffix>` |
| GCS prefix | `staging/` |
| Render service | `sound-backend-staging` |
| Git branch | `staging` |
| Flutter applicationId | `com.example.sound_detector_clean.staging` |

## Supabase

| Field | Plan |
| --- | --- |
| Purpose | Isolated staging PostgreSQL for schema and API validation |
| Region | Choose near Render/backend test region |
| Required permissions | Project admin for migration execution |
| Required secrets | `DATABASE_URL`, optional Supabase API URL/key for manual checks |
| Creation path | Supabase Dashboard -> New project |
| Validation | `tools\migration_precheck.sql`, then `tools\migration_postcheck.sql` |
| Cleanup | Delete staging project after export/evidence review |
| Cost impact | Running project may incur database cost |
| Production isolation proof | Project ref and DB host must differ from production |

## Google Cloud Storage

| Field | Plan |
| --- | --- |
| Purpose | Isolated staging audio storage |
| Bucket | `sound-detector-staging-<unique-suffix>` |
| Prefix | `staging/` |
| Required permissions | Object create/read sufficient for upload and signed playback |
| Required secrets | staging service account JSON |
| Creation path | Google Cloud Console -> Cloud Storage -> Create bucket |
| Validation | Upload one staging object and generate signed playback URL |
| Cleanup | Delete staging bucket or lifecycle cleanup |
| Cost impact | Storage + operation charges |
| Production isolation proof | Bucket must not be `sound-detector` |

## Render

| Field | Plan |
| --- | --- |
| Purpose | Staging FastAPI backend |
| Service | `sound-backend-staging` |
| Branch | `staging` |
| Worker count | 1 |
| Health check | `/health` |
| Required env | See `.env.staging.example` |
| Live audio | Disabled initially |
| Validation | `tools\post_deploy_smoke.py --base-url <staging-url> --allow-websocket` |
| Cleanup | Delete staging service or disable auto-deploy |
| Cost impact | Render instance cost |
| Production isolation proof | Service URL must not be `sound-backend.onrender.com` |

## Flutter

| Field | Plan |
| --- | --- |
| Config | `config\staging.local.json` |
| Backend URL | staging Render URL |
| Token source | staging-only generated token |
| Build | `tools\build_staging_apk.ps1` |
| Signing | Internal Test signing until production keystore exists |
| Validation | Install only after `APPROVE CANARY INSTALL` |
