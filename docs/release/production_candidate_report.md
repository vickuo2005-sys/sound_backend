# Production Candidate Report

Date: 2026-07-24

## 1. Executive Summary

Production Final source is locally complete enough for staging preparation, but it is not production-ready until staging migrations, physical-device tests, live audio manual playback, and secret hardening are completed.

## 2. Source State

- Backend Git repo: Yes.
- Flutter Git repo: No.
- Backend working tree: Dirty with existing V3/V4 changes and release prep artifacts.
- README.md: Dirty and intentionally not staged or committed.

## 3. Secret Audit

See `docs/security/release_secret_audit.md`.

Result: staging-ready with internal test token, production blocker until Flutter token handling is hardened.

## 4. Migration Audit

See `docs/database/release_migration_matrix.md`.

Result: safe for staging runbook review. No migration was executed.

## 5. Staging Configuration

- `.env.staging.example` created.
- `render.staging.yaml` created.
- Live audio default is disabled for initial staging.

## 6. Render Readiness

Ready for staging review with one worker. Multiple workers are not safe because realtime managers are in memory.

## 7. Backend Tests

Local validation artifacts are under `artifacts/test_results`.

- Fresh venv: `.venv_release_validation`
- `compileall`: Passed
- `pytest -ra`: Passed, 4 tests, 2 pydantic deprecation warnings
- `tools/test_realtime_protocol.py`: Passed
- `pip check`: Passed

## 8. Flutter Tests

APK manifest artifacts are under `artifacts/`.

- `dart format --output=none --set-exit-if-changed .`: Passed
- `flutter doctor -v`: Completed
- `flutter pub get`: Passed
- `flutter analyze`: Passed
- `flutter test`: Passed, 16 tests
- `flutter build apk --debug`: Passed
- `flutter build apk --release`: Passed

## 9. WebSocket Integration

Node WebSocket, command push, audio WebSocket, and dashboard audio subscriber have local synthetic validation.

- REST local smoke: Passed
- Node WebSocket hello / command push: Passed
- Audio WebSocket node upload: Passed
- Dashboard subscriber authentication and binary forwarding: Passed
- Sent and received binary payload SHA-256 matched

## 10. Dashboard Playback Status

Frame forwarding is validated locally. Actual browser audio quality remains `MANUAL AUDIO VERIFICATION REQUIRED`.

See `docs/testing/dashboard_browser_validation.md`.

## 11. Foreground Service

Android foreground service builds successfully. Physical-device long-run behavior is not run in this pass.

## 12. Event Retry Queue

Unit tests pass for persistent queue lifecycle. Restart, network failure, backend 500, and missing-file scenarios require physical or staging integration evidence.

See `docs/testing/event_retry_queue_validation.md`.

## 13. APK Manifest

See `artifacts/apk_manifest.json` and `artifacts/apk_manifest.txt`.

- Debug APK SHA-256 recorded.
- Release APK SHA-256 recorded.
- Release build currently uses debug signing config from `android/app/build.gradle.kts`.

## 13a. Release Snapshot

- Flutter snapshot generated at `C:\release_snapshots\sound_detector_clean\20260724_005736`.
- Files copied: 70.
- Snapshot manifest generated inside the snapshot directory.

## 13b. Local Stress Test

- Non-production local stress test: Passed.
- Simulated 10 location updates and 10 command creations.
- Artifact: `artifacts/test_results/local_stress_test.json`.

## 14. Known Limitations

- Flutter project is not version controlled.
- Release APK is currently signed with debug signing config.
- Flutter source contains demo upload token.
- Dashboard live audio uses Web Audio scheduled PCM buffers; manual audio QA remains required.
- Local stress testing is not a substitute for Render staging tests.

## 15. Staging Blockers

- None blocking source packaging.
- Staging database and staging GCS credentials must be provided.
- Staging migrations must be run manually.

## 16. Production Blockers

- Production secrets not hardened in Flutter.
- Release signing not configured.
- No physical multi-node validation evidence in this pass.
- No production Supabase migration execution.
- No production Render deployment.

## 17. Recommended Deployment Order

1. Create clean backend release branch.
2. Review and exclude README.md unless intended.
3. Run staging migrations.
4. Deploy staging with one worker and live audio disabled.
5. Run post-deploy smoke.
6. Install release APK on one node.
7. Canary command and event flow.
8. Enable one-node live audio canary.
9. Perform physical device test matrix.
10. Only then plan production.

## 18. Rollback Plan

See `docs/deployment/rollback_runbook.md`.

## 19. Go / No-Go

- Local Code Complete: Yes
- Ready for Staging: Yes, after staging secrets and database are prepared
- Ready for Production: No
