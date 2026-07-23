# Pre-Staging Execution Report

Date: 2026-07-24  
Work package: Production Blocker Remediation + Staging Build Preparation +
Release Signing Preparation + Final Pre-Staging Validation.

## 1. Executive Summary

The major source-level production blockers were remediated locally:

- Flutter runtime no longer hardcodes the demo upload token.
- Backend upload token fallback was removed.
- Flutter staging/production config is explicit and fail-fast.
- Android signing is prepared with a production-blocking release path.
- Staging APK can be built as an internal-test artifact.

Production is still blocked until real release signing, staging infrastructure,
staging migrations, and physical-device validation are completed.

## 2. Baseline State

- Backend: `C:\sound_backend`
- Flutter: `C:\Users\vicku\sound_detector_clean`
- Flutter snapshot: `C:\release_snapshots\sound_detector_clean\20260724_005736`
- Backend Git: dirty/untracked worktree; no files staged.
- Flutter Git: not initialized.
- README.md: pre-existing dirty change, not included in this remediation.

## 3. Demo Token Remediation

Runtime no longer depends on the demo upload token:

- Flutter `lib/config/app_config.dart` reads token config from `--dart-define`.
- Backend `verify_upload_token()` now requires `UPLOAD_TOKEN`.
- Test fixtures use `test-only-token`.

## 4. Runtime Config Architecture

Added `AppConfig` fields:

- `APP_ENV`
- `BACKEND_BASE_URL`
- `UPLOAD_TOKEN`
- `DEVICE_TOKEN`
- `LIVE_AUDIO_ENABLED`
- `COMMAND_WEBSOCKET_ENABLED`
- `REST_FALLBACK_ENABLED`

Invalid config prevents:

- node WebSocket startup
- command polling
- time sync
- GPS upload
- event metadata upload
- audio upload
- event retry worker

## 5. Staging Build Configuration

Added:

- `config/staging.example.json`
- `config/production.example.json`
- local ignored fixtures for validation
- `tools/build_staging_apk.ps1`
- `tools/build_production_apk.ps1`
- `tools/validate_flutter_config.ps1`

Staging build command:

```powershell
tools\build_staging_apk.ps1 -ConfigPath config\staging.local.json
```

## 6. Production Config Validation

Production config validation requires:

- `APP_ENV=production`
- HTTPS backend URL
- non-empty upload token
- non-empty device token
- no demo token
- no localhost
- no staging host

Production build is blocked without release signing prerequisites.

## 7. Release Signing Status

Added:

- Android product flavors: `staging`, `production`
- `android/key.properties.example`
- `tools/generate_release_keystore.ps1`
- `tools/verify_apk_signing.ps1`
- `docs/release/android_release_signing_guide.md`

No real keystore was generated.

## 8. APK Signing Verification

Staging APK verification:

- Signed: Yes
- Debug-signed: Yes
- Classification: INTERNAL TEST ONLY
- Certificate SHA-256: `36545ed91eaaaebdc564417abb39252c639385d9939716c441e6b29d5fc7ec04`

Production APK:

- Status: Blocked
- Reason: `android/key.properties` and release keystore are required.

## 9. Event Retry Regression

Automated queue lifecycle tests passed. Invalid runtime config no longer starts
the upload worker and queued items remain local.

Physical retry tests are not run because they require real devices/staging.

## 10. Foreground Service Regression

Debug and staging release APK builds passed after flavor/signing changes.
Foreground service source was not redesigned.

Physical start/stop and Android background behavior were not run in this local
pass.

## 11. Backend Token Readiness

Backend staging env example now includes staging-only placeholders for:

- `UPLOAD_TOKEN`
- `DEVICE_TOKEN`
- `STREAM_TOKEN_SECRET`
- `DASHBOARD_AUTH_SECRET`

No secret values were written to source-controlled files.

## 12. Staging Resource Checklist

Created:

`docs/deployment/staging_resource_creation_checklist.md`

## 13. Migration Precheck Package

Created:

- `tools/migration_precheck.sql`
- `tools/migration_postcheck.sql`
- `tools/validate_migration_output.py`

The SQL scripts are read-only.

## 14. Staging Command Kit

Created:

- `tools/staging/prepare_staging_env.ps1`
- `tools/staging/validate_staging_env.ps1`
- `tools/staging/run_staging_smoke.ps1`
- `tools/staging/collect_staging_evidence.ps1`

## 15. Backend Git Classification

Created:

`docs/release/pre_staging_git_classification.md`

No Git index changes were made.

## 16. Flutter Version Control Plan

Created:

`docs/release/flutter_git_initialization_runbook.md`

No `git init` was performed.

## 17. Backend Tests

| Test | Result |
| --- | --- |
| `pip check` | Pass |
| `python -m compileall .` | Pass |
| `python -m pytest -ra` | Pass |
| `python tools\test_realtime_protocol.py` | Pass |
| local `tools\post_deploy_smoke.py` | Pass |

## 18. Flutter Tests

| Test | Result |
| --- | --- |
| `dart format --output=none --set-exit-if-changed .` | Pass after formatting |
| `flutter analyze` | Pass |
| `flutter test` | Pass: 22 tests |
| `flutter build apk --debug` | Pass |
| `flutter build apk --flavor staging --release` | Pass |
| `tools\build_staging_apk.ps1` | Pass |
| `tools\build_production_apk.ps1` | Blocked as designed |

## 19. APK Artifacts

See:

- `artifacts/apk_manifest.json`
- `artifacts/apk_manifest.txt`

Staging APK:

`C:\Users\vicku\sound_detector_clean\build\app\outputs\flutter-apk\app-staging-release.apk`

SHA-256:

`42535146e859677e63680696c9748fe173b3dbb8199a5ed36657e171cea9e2b1`

## 20. Remaining Manual Actions

1. Create staging Supabase, GCS, and Render resources.
2. Fill staging secrets in Render, not files.
3. Run staging migration precheck.
4. Execute approved staging migrations.
5. Run migration postcheck.
6. Deploy staging backend.
7. Install staging APK on physical devices.
8. Run real-device GPS, command, audio, retry, and live-audio tests.
9. Create production release keystore before production APK.

## 21. Staging Blockers

- Staging resources do not yet exist.
- Staging migration was not run.
- Physical Android staging validation was not run.
- Browser audible live-audio verification was not run.

## 22. Production Blockers

- Production release keystore missing.
- Production APK not built/release-signed.
- Staging validation not completed.
- Production migration/deployment not approved or run.

## 23. Ready for Staging Decision

Ready to create staging resources: Yes.

Ready to run staging migration: Yes, after staging database is selected and
precheck output is reviewed.

Ready to deploy staging: Yes, after staging resources and secrets are prepared.

## 24. Ready for Production Decision

Ready for production: No.
