# Staging Environment Variables

Use `.env.staging.example` as the staging checklist. Do not paste production secrets into documentation.

| Variable | Required | Secret | Purpose | Safe staging value | Production difference | Restart |
|---|---:|---:|---|---|---|---:|
| `APP_ENV` | Yes | No | Environment label | `staging` | `production` | Yes |
| `LOG_LEVEL` | No | No | Logging verbosity | `INFO` | `INFO` or stricter | Yes |
| `DATABASE_URL` | Yes | Yes | Supabase PostgreSQL connection | staging database pooler | production DB pooler | Yes |
| `GCS_BUCKET_NAME` | Yes | No | Audio bucket | staging bucket | production bucket | Yes |
| `GOOGLE_APPLICATION_CREDENTIALS_JSON` | Yes | Yes | GCS service account JSON | staging service account | production service account | Yes |
| `GOOGLE_MAPS_API_KEY` | Yes | Yes | Dashboard map key | restricted staging key | restricted production key | Yes |
| `UPLOAD_TOKEN` | Yes | Yes | App upload token | staging-only token | production token | Yes |
| `DASHBOARD_AUTH_SECRET` | Optional now | Yes | Future dashboard auth | staging secret | production secret | Yes |
| `NODE_WEBSOCKET_ENABLED` | Yes | No | Node WS feature flag | `true` | `true` | Yes |
| `COMMAND_WEBSOCKET_ENABLED` | Yes | No | Command push feature flag | `true` | canary first | Yes |
| `COMMAND_REST_FALLBACK_ENABLED` | Yes | No | Legacy polling fallback | `true` | keep `true` | Yes |
| `LIVE_AUDIO_ENABLED` | Yes | No | Live audio streaming | `false` initially | canary only | Yes |
| `LIVE_AUDIO_DEFAULT_CODEC` | Yes | No | Live audio codec | `pcm_s16le` | `pcm_s16le` | Yes |
| `LIVE_AUDIO_MAX_CONCURRENT_STREAMS` | Yes | No | Limit active streams | `1` | conservative | Yes |
| `LIVE_AUDIO_MAX_SESSION_SECONDS` | Yes | No | Stream duration cap | `300` | conservative | Yes |
| `EVENT_UPLOAD_RETRY_ENABLED` | Yes | No | Retry queue flag | `true` | `true` | Yes |

Feature flags should start conservatively. Enable live audio on staging one node at a time.

