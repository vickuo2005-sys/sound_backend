# Phase 4 isolated staging audit — 2026-08-25

## Decision

`BLOCKED`. No staging cloud resource, schema, deployment, health result, APK,
or field result exists yet. Production was not used as a fallback.

## Frozen source inspected

- Backend starting head: `55230b9af51bd519c67733b723a0aeda1b4dc034`
- Flutter starting head: `17639961980bbcb1af06b066887fc5dc16a455ce`
- Branch: `feat/v2-3-phase4-field-shadow`

## Cloud identity result

| System | Result | Action |
|---|---|---|
| Render | Sign-in page; workspace/service identity unavailable | No resource created or changed |
| Supabase | Sign-in page; organization/project identity unavailable | No project created; no SQL run |
| Google Cloud | Signed in to an ambiguously named project containing only the existing `sound-detector` bucket | Treated as non-staging; no bucket, IAM binding, service account, or key created |

## Local configuration result

- Ignored Flutter `config/staging.local.json` exists, but identifies
  `development` and the known production backend. Tokens are present but were
  neither printed nor reused. The strengthened validators reject it.
- Ignored backend `config/staging_targets.local.json` likewise describes the
  old development/production-shaped target. The strengthened target validator
  rejects it.
- Both local files are ignored and untracked. They were not overwritten because
  their token ownership cannot be safely inferred.

## Secrets

New random local values were generated for `UPLOAD_TOKEN`, `DEVICE_TOKEN`, and
the code's actual dashboard-write secret, `DASHBOARD_ADMIN_TOKEN`. The ignored
files are:

- `config/phase4_staging_secrets.local.env`
- `config/phase4_staging_secrets_inventory.local.json`

No value or suffix is present in this report. These secrets are generated
locally but not configured in Render or Flutter, because no approved staging
hostname/resource identity exists.

`DASHBOARD_WRITE_TOKEN` is not read by current backend code. When
`DASHBOARD_WRITE_TOKEN_REQUIRED=true`, the backend reads
`DASHBOARD_ADMIN_TOKEN` and falls back to `UPLOAD_TOKEN`. Legacy
`STREAM_TOKEN_SECRET` and `DASHBOARD_AUTH_SECRET` are also not read.

## Database baseline

The existing migration chain is not directly runnable on an empty project:
`v3_0_event_fusion_tracking.sql` expects `events` to exist. The new
`migrations/v2_0_events_baseline.sql` is an additive fresh-staging prerequisite.
The reviewed order and object inventory are in
`docs/database/phase4_staging_schema_baseline.md`.

No schema was applied. A real staging target summary, precheck, SQL review,
application, and postcheck remain mandatory.

## GCS decision

Observation shadow ingestion itself does not write audio. The first Phase 4
smoke also exercises the existing real detection `/events` flow, whose normal
audio-upload paths can call GCS. Therefore this run treats a staging-only GCS
bucket and bucket-scoped service account as prerequisites unless the smoke is
explicitly narrowed to prove that every audio upload path is disabled.

## APK and device

- `adb devices -l`: zero physical devices.
- The APK was not built because staging hostname, DB isolation, GCS isolation,
  Render health, token configuration, and an authorized device are missing.
- No smoke or field evidence was produced.
