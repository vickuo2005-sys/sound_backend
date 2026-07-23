# Staging Execution Plan

SECTION A local preparation is complete or in progress. SECTION B cloud
execution is blocked until explicit approval.

Required approval phrase:

`APPROVE STAGING EXECUTION`

## Planned Cloud Actions After Approval

| Action | Target | Production isolation check |
| --- | --- | --- |
| Push backend branch | `staging` | Do not push `main` |
| Create Supabase | `sound-detector-staging` | Project ref/host must differ |
| Create GCS | `sound-detector-staging-<unique-suffix>` | Bucket must not be `sound-detector` |
| Create Render | `sound-backend-staging` | URL must not be production |
| Configure secrets | Render staging | staging-only values |
| Run migration | staging DB only | precheck/postcheck required |
| Deploy backend | staging Render only | one worker |
| Build APK | staging flavor | `.staging` applicationId |

## Rollback / Cleanup

- Render: redeploy previous staging commit or suspend service.
- Supabase: restore staging backup/snapshot or delete staging project.
- GCS: delete staging test objects or bucket.
- APK: uninstall `com.example.sound_detector_clean.staging`.

## Not Approved Yet

- Git push
- Supabase project creation
- GCS bucket/service account creation
- Render service creation
- Staging migration execution
- Staging deployment
- Canary install
- Live Audio enablement
