# Staging Tooling Status

Date: 2026-07-24  
Updated after `APPROVE STAGING EXECUTION`. GitHub push is available and was used. Cloud project creation remains blocked because the required cloud CLIs or API tokens are not available in this local environment.

| Tool | Status | Authentication | Notes |
| --- | --- | --- | --- |
| `git` | AVAILABLE | N/A | `git version 2.52.0.windows.1` |
| `gh` | NOT_INSTALLED | NOT_RUN | GitHub CLI unavailable |
| `supabase` | NOT_INSTALLED | NOT_RUN | Use Supabase UI or install CLI |
| `psql` | NOT_INSTALLED | NOT_RUN | Needed for local scripted SQL execution |
| `gcloud` | NOT_INSTALLED | NOT_RUN | Use Google Cloud UI or install SDK |
| `gsutil` | NOT_INSTALLED | NOT_RUN | Use Google Cloud UI or install SDK |
| `render` | NOT_INSTALLED | NOT_RUN | Use Render dashboard or API manually |
| `python` | AVAILABLE | N/A | `Python 3.14.0` visible on PATH |
| `adb` | AVAILABLE_NOT_ON_PATH | N/A | Found at `C:\Users\vicku\AppData\Local\Android\sdk\platform-tools\adb.exe` |
| `keytool` | AVAILABLE_NOT_ON_PATH | N/A | Found at `C:\Program Files\Android\Android Studio\jbr\bin\keytool.exe` |
| `apksigner` | AVAILABLE_NOT_ON_PATH | N/A | Found in Android SDK build-tools |
| `aapt` | AVAILABLE_NOT_ON_PATH | N/A | Found in Android SDK build-tools |

## Environment Token Check

Only variable presence was checked. Secret values were not printed.

| Variable | Present |
| --- | --- |
| `GITHUB_TOKEN` / `GH_TOKEN` | No |
| `SUPABASE_ACCESS_TOKEN` | No |
| `DATABASE_URL` | No |
| `GOOGLE_APPLICATION_CREDENTIALS` / `GOOGLE_APPLICATION_CREDENTIALS_JSON` | No |
| `GCP_PROJECT_ID` / `GOOGLE_CLOUD_PROJECT` | No |
| `RENDER_API_KEY` / `RENDER_TOKEN` | No |

## Practical Impact

- Backend local Git operations can run.
- Backend `staging` branch can be pushed through the configured Git remote.
- Staging cloud creation is currently manual UI work unless CLI tools are installed.
- Supabase migration cannot be executed locally without `psql`, Supabase CLI, or a staging `DATABASE_URL`.
- GCS bucket/service-account setup cannot be executed locally without Google Cloud SDK or credentials.
- Render service creation/deployment cannot be executed locally without Render CLI/API access or dashboard UI access.
- APK signing verification can run with explicit SDK paths.
- ADB can run with an explicit path for canary install after approval.

## Staging URL Probe

`https://sound-backend-staging.onrender.com/health` returned HTTP 404 on 2026-07-24, so no usable staging Render service is currently reachable at the planned URL.
