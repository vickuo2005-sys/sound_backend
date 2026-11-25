# Pre-Staging Blocker Audit

Date: 2026-07-24  
Scope: Production Blocker Remediation, staging build preparation, release signing
preparation, and final local pre-staging validation.

No Render deployment, Supabase migration execution, Git staging, commit, push,
tag, or production resource modification was performed.

## Baseline

| Area | Result |
| --- | --- |
| Backend git status | Dirty / untracked release work present |
| README.md | Pre-existing dirty change, not staged or edited |
| Flutter git | Not a Git repository |
| Flutter source snapshot | Existing snapshot: `C:\release_snapshots\sound_detector_clean\20260724_005736` |
| Existing production URL | Not deployed or modified |

## Production Blockers

| Blocker | Status | Remediation |
| --- | --- | --- |
| Flutter source hardcoded demo upload token | Fixed for runtime | Added `AppConfig`; runtime uses `--dart-define-from-file`; no demo token fallback |
| Backend upload token default fallback | Fixed for runtime | `UPLOAD_TOKEN` must be configured; missing token returns 503 |
| Release APK debug signing | Partially remediated | Release signing config and scripts added; production build is blocked until keystore exists |
| No staging Supabase / GCS / Render | Still manual | Checklist and env validation tools added |
| Staging migrations not executed | Not run | Read-only pre/postcheck SQL added |
| Physical Android long-run test | Not run | Requires device/staging |
| Dashboard live audio audible browser verification | Not run | Requires staging/manual browser validation |
| Backend dirty worktree | Still dirty | Classified in `docs/release/pre_staging_git_classification.md` |
| Flutter not in Git | Still manual | Runbook added; no git init performed |

## Token Audit

Runtime changes:

- Flutter upload token is read from `UPLOAD_TOKEN`.
- Flutter device token is read from `DEVICE_TOKEN`.
- Production/staging runtime rejects missing token config.
- Production/staging runtime rejects the demo token.
- Backend upload endpoints no longer accept a default upload token when
  `UPLOAD_TOKEN` is unset.

Remaining references:

- `README.md` has pre-existing demo examples and was not edited.
- Old release/audit documents may describe historical demo-token blockers.
- Backend test fixtures now use `test-only-token`.

## Release Signing Audit

| Item | Result |
| --- | --- |
| `android/key.properties.example` | Created |
| `android/key.properties` | Not created |
| real release keystore | Not created |
| staging APK signing | Debug-signed, INTERNAL TEST ONLY |
| production APK signing | Blocked until keystore exists |
| fallback debug-signed production build via script | Blocked |

## Validation Summary

| Check | Result |
| --- | --- |
| Backend `pip check` | Pass |
| Backend `compileall` | Pass |
| Backend `pytest -ra` | Pass: 4 tests, 2 warnings |
| Backend realtime protocol tool | Pass |
| Local backend smoke | Pass |
| Flutter config tests | Pass |
| Flutter analyze | Pass |
| Flutter tests | Pass: 22 tests |
| Debug APK build | Pass |
| Staging release APK build | Pass |
| Production release APK build | Blocked: release keystore required |
| Staging APK signing verification | Pass for internal staging |

## APK

| Field | Value |
| --- | --- |
| Staging APK | `C:\Users\vicku\sound_detector_clean\build\app\outputs\flutter-apk\app-staging-release.apk` |
| Size | 174838569 bytes |
| SHA-256 | `42535146e859677e63680696c9748fe173b3dbb8199a5ed36657e171cea9e2b1` |
| applicationId | `com.example.sound_detector_clean.staging` |
| versionName | `1.0.0-staging` |
| signing | INTERNAL TEST ONLY |
| certificate SHA-256 | `36545ed91eaaaebdc564417abb39252c639385d9939716c441e6b29d5fc7ec04` |

## Decision

| Decision | Status |
| --- | --- |
| Local Code Complete | Yes |
| Ready to Create Staging Resources | Yes |
| Ready to Run Staging Migration | Yes, after staging database is selected |
| Ready to Deploy Staging | Yes, after staging resources/secrets exist |
| Ready for Production | No |
