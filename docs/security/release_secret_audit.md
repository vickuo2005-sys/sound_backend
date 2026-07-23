# Release Secret Audit

Date: 2026-07-24

This audit checked for obvious credential patterns without printing secret values. No production secret was required or used.

## Findings

| Area | Finding | Risk | Action |
|---|---|---:|---|
| Backend default token | `DEFAULT_UPLOAD_TOKEN = "test-token-123"` remains in `main.py` as development fallback. | Medium | Set `UPLOAD_TOKEN` in staging/production and consider refusing startup in production when unset. |
| Flutter upload token | `lib/main.dart` contains `test-token-123`. | High for production | Move to build-time config or node provisioning before production. Acceptable only for demo/staging. |
| GCS credentials | Backend reads `GOOGLE_APPLICATION_CREDENTIALS_JSON` from env. | Low | Correct pattern. Do not commit JSON key. |
| Database credentials | Backend reads `DATABASE_URL` from env. | Low | Correct pattern. Do not log or commit connection string. |
| Stream tokens | Runtime `stream_token` and `subscriber_token` are generated with `secrets.token_urlsafe`. | Low | Correct pattern. Subscriber token is sent by WebSocket first message, not URL. |
| Local Android config | `android/local.properties` exists. | Low | Keep ignored and out of any Flutter release snapshot. |
| Backend venv cert files | `.pem` files found only under `venv` package certifi. | Low | Not source secrets; keep `venv/` ignored. |

## Secret Patterns Reviewed

- API keys
- upload tokens
- bearer/authorization tokens
- Supabase URLs and keys
- PostgreSQL connection strings
- Google service account JSON
- private keys
- keystore and signing configs
- `.env` and `.env.*`

## Git Ignore Notes

Backend `.gitignore` should be expanded before a clean release branch:

```gitignore
.env.*
!.env.example
.pytest_cache/
.venv/
.venv_release_validation/
artifacts/
*.pem
*.key
service-account*.json
credentials*.json
```

Flutter `.gitignore.release-proposal` was prepared separately and does not modify the current Flutter project.

## Decision

- Ready for staging secrets review: Yes
- Ready for production with current hard-coded Flutter token: No
- Production blocker: move Flutter upload token out of source or treat every distributed APK as trusted internal-only demo software.

