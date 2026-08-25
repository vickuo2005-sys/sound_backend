# Staging Cloud Execution Plan

Do not execute this plan until the user explicitly says:

`APPROVE STAGING EXECUTION`

## Supabase Migration Sequence

1. Confirm selected Supabase project is staging.
2. Record masked project ref and database host.
3. Create evidence directory under `artifacts\staging_migration\<timestamp>\`.
4. Take schema backup or initial dump.
5. Run `tools\migration_precheck.sql`.
6. Review precheck output.
7. Apply migrations in the approved release order.
8. Run `tools\migration_postcheck.sql`.
9. Validate output with `tools\validate_migration_output.py`.
10. Record migration ledger with file names, SHA-256, exit status, and notes.

Failure handling: stop immediately, do not continue to later migrations, and
use forward-fix/rollback runbook guidance.

## GCS Sequence

1. Create staging-only bucket.
2. Enable uniform bucket-level access.
3. Keep public access prevention enabled.
4. Configure CORS only as needed for staging playback.
5. Create least-privilege service account.
6. Store JSON only in Render staging secret, not Git.
7. Validate upload and signed URL playback.

## Render Sequence

1. Confirm backend staging branch has been pushed.
2. Create service `sound-backend-staging`.
3. Configure one worker.
4. Set health check to `/health`.
5. Configure staging-only environment variables.
6. Ensure `LIVE_AUDIO_ENABLED=false` initially.
7. Deploy staging.
8. Run post-deploy smoke.

## Gates

- No production URL, database, bucket, token, or service may be used.
- Live Audio remains disabled until `APPROVE STAGING LIVE AUDIO`.
- ADB install remains blocked until `APPROVE CANARY INSTALL`.
