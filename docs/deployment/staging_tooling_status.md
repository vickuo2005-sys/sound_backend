# Staging Tooling Status

Date: 2026-07-24  
This is local tooling discovery only. No cloud project was selected or modified.

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

## Practical Impact

- Backend local Git operations can run.
- Staging cloud creation is currently manual UI work unless CLI tools are installed.
- APK signing verification can run with explicit SDK paths.
- ADB can run with an explicit path for canary install after approval.
