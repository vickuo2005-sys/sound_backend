# Staging resource creation checklist

Status at the time this checklist was prepared: Render and Supabase were not
authenticated. Google Cloud showed only an ambiguous project containing the
existing `sound-detector` bucket. No cloud resource was created.

Production is never a fallback. Stop if any project, service, database, bucket,
or credential cannot be positively identified as staging-only.

## A. Supabase Dashboard

1. Sign in to the Supabase Dashboard and select the intended staging
   organization.
2. Click **New project**.
3. Set the name to `sound-detector-staging` (or another explicit staging name),
   generate a new database password in a password manager, and choose a region
   near the Render staging region. Singapore is the intended pairing in the
   current Render template.
4. Wait until the project is healthy. Record, without the password:
   - organization;
   - project name;
   - project ref from the dashboard URL;
   - region;
   - database hostname.
5. Open **Connect** and copy the Session pooler connection string for Render.
   Store it only as Render staging `DATABASE_URL`; include TLS as required.
6. Before any SQL, produce this target summary and compare it with the cloud UI:

   ```text
   Project: <staging project ref>
   Environment: STAGING
   Host: <staging database host, no password>
   Production ref/host differs: YES
   Tables: events, device_status, device_locations, device_commands,
   event_groups, event_group_observations, localization_results,
   localization_pair_results, target_tracks, target_track_points,
   device_connections, audio_stream_sessions
   ```

7. In **SQL Editor**, run `tools/migration_precheck.sql` first. For a new empty
   project, apply only the ordered files in
   `docs/database/phase4_staging_schema_baseline.md`. Then run
   `tools/migration_postcheck.sql`.
8. Stop on any unexpected existing application table, missing `pgcrypto`, SQL
   error, identity mismatch, or evidence that the project is production.

Return to Codex: project ref, region, database hostname (no password), and the
precheck/postcheck output. Provide the connection URI only through a secure
secret mechanism, never chat or Git.

## B. Google Cloud Console

The current ambiguous project must not be assumed staging. Prefer a dedicated
GCP project named `sound-detector-staging`.

1. Use the project selector, click **New project**, create/select the explicitly
   staging project, and confirm billing/organization identity.
2. Open **Cloud Storage → Buckets → Create**.
3. Use a globally unique name such as
   `sound-detector-staging-audio-<unique-suffix>`, select the same region as the
   backend where practical, Standard storage, public access prevention, and
   uniform bucket-level access.
4. Add a short staging lifecycle policy only after retention requirements are
   agreed. Do not grant `allUsers` or `allAuthenticatedUsers`.
5. Open **IAM & Admin → Service Accounts → Create service account** and create
   `sound-detector-staging-backend` in the staging project.
6. On the staging bucket's **Permissions** tab, grant that service account an
   object role at the bucket scope only. `Storage Object Admin` is sufficient
   for the current create/read/delete object flow; do not grant project-wide
   access and do not grant access to `sound-detector`.
7. Create a JSON key only when ready to place it directly into Render staging.
   Treat key creation as a sensitive persistent-access action. Never save the
   key in either repository.

Return to Codex: staging GCP project ID, bucket name, region, service-account
email, and bucket-scoped role. Do not send the JSON key in chat.

## C. Render Dashboard

1. Sign in and verify the intended workspace/team.
2. Click **New → Web Service**, connect the backend repository, and select
   branch `feat/v2-3-phase4-field-shadow` at the validated commit. Do not select
   or edit the existing `sound-backend` service.
3. Configure:
   - name: `sound-backend-staging`;
   - runtime: Python;
   - region: same/nearest region to Supabase (the template uses Singapore);
   - build: `pip install -r requirements.txt`;
   - start: `uvicorn main:app --host 0.0.0.0 --port $PORT --workers 1`;
   - health path: `/health`;
   - auto-deploy: off for the initial controlled run.
4. Under **Environment**, enter only the variables in
   `staging_environment_variables.md`. Never copy a production environment
   group. `DATABASE_URL`, GCS identity, and all tokens must be staging-only.
5. Before clicking **Create Web Service**, verify:
   - service name is not `sound-backend`;
   - `APP_ENV=staging`;
   - Supabase project ref/host is the approved staging target;
   - GCS bucket contains `staging` and is not `sound-detector`;
   - token fingerprints differ from production without revealing values.
6. After deploy, record the actual `onrender.com` hostname and commit SHA. That
   exact hostname becomes the Flutter validator's approved allowlist input.

Return to Codex: workspace/team name, service ID/name, hostname, region, and
deployed commit SHA. Do not return secret values.

## D. Health gate before APK

1. `GET /health` must return 2xx and no DB init error.
2. `GET /runtime-status` must report PostgreSQL, the expected feature flags,
   WebSocket routes configured, GCS configured when audio is in scope, and the
   expected Render service/commit metadata.
3. `GET /database-status` must report every required staging table. Compare its
   host/project identity using the Render secret configuration because the
   endpoint intentionally does not expose the database hostname.
4. Open a staging `/ws/dashboard` connection and verify the handshake without
   sending Observation traffic.
5. Keep `STAGING_DB_LATENCY_PROBE_ENABLED=false` until the bounded latency run.

Only after all checks pass may the actual Render hostname be approved for the
Flutter config and APK build.
