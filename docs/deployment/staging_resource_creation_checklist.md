# Staging Resource Creation Checklist

Do not reuse production Supabase, GCS, or Render resources for staging.

## A. Staging Supabase

| Item | Value to prepare | Where to configure | Validation | Status |
| --- | --- | --- | --- | --- |
| Project name | sound detector staging project | Supabase dashboard | Not production project | [ ] |
| Region | closest practical staging region | Supabase dashboard | Recorded in release notes | [ ] |
| Database password | staging-only secret | Supabase dashboard / password manager | Not in Git | [ ] |
| DATABASE_URL | pooler connection string | Render staging env | `tools\staging\validate_staging_env.ps1` | [ ] |
| Schema | release migrations applied | SQL Editor | `tools\migration_postcheck.sql` | [ ] |
| Backup policy | staging snapshot before migration | Supabase | snapshot recorded | [ ] |

## B. Staging GCS

| Item | Value to prepare | Where to configure | Validation | Status |
| --- | --- | --- | --- | --- |
| Bucket name | staging-only bucket | Google Cloud Storage | not `sound-detector` | [ ] |
| Region | staging region | GCS | matches cost/latency plan | [ ] |
| Service account | staging-only account | IAM | least privilege | [ ] |
| Permissions | object create/read for signed URL flow | IAM | upload + signed URL smoke | [ ] |
| CORS | dashboard audio playback needs | GCS bucket | browser playback test | [ ] |
| Retention | short staging retention | lifecycle policy | policy visible | [ ] |

## C. Staging Render

| Item | Value to prepare | Where to configure | Validation | Status |
| --- | --- | --- | --- | --- |
| Service name | sound-backend-staging | Render | service exists | [ ] |
| Repository / branch | staging branch or selected commit | Render | commit SHA recorded | [ ] |
| Build command | `pip install -r requirements.txt` | Render | deploy logs | [ ] |
| Start command | `uvicorn main:app --host 0.0.0.0 --port $PORT --workers 1` | Render | one worker only | [ ] |
| Health check | `/health` | Render | 200 OK | [ ] |
| Env vars | staging-only | Render | validation passed | [ ] |
| Live audio | disabled initially | Render env | one-node canary later | [ ] |
| Rollback | previous Render deploy | Render | rollback runbook reviewed | [ ] |

## D. Flutter Staging

| Item | Value to prepare | Where to configure | Validation | Status |
| --- | --- | --- | --- | --- |
| Config file | `config\staging.local.json` | local only | validate script passes | [ ] |
| Backend URL | staging Render URL | config file | not production host | [ ] |
| Upload token | staging-only | config file | not demo token | [ ] |
| Device token | staging-only | config file | configured | [ ] |
| APK signing | internal test signing | build report | debug signing accepted only for staging | [ ] |
| Test device IDs | A01/A02/A03 | app UI | Dashboard sees nodes | [ ] |
| Logs | adb/logcat capture | local evidence | saved outside Git | [ ] |
