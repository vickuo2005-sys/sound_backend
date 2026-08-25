# Phase 4 isolated staging deployment runbook

1. Record clean Git status, branch, and commit for both repositories. Do not
   push as part of this runbook.
2. Confirm the Supabase project ref/database host, Render workspace/service,
   and GCP project/bucket identities are explicitly staging and differ from
   production.
3. Run `python tools/staging/validate_staging_targets.py
   config/staging_targets.local.json`. Treat its result as a shape check; cloud
   UI identity comparison is still mandatory.
4. Run the Supabase precheck, reviewed fresh-database migration order, and
   postcheck. Never use `POSTGRES_SCHEMA_AUTO_INIT=true` for this deployment.
5. Configure Render using `render.staging.yaml` as the non-secret template and
   manually enter all `sync: false` staging values.
6. Verify service name, database target, bucket, and token fingerprints again,
   then deploy one worker.
7. Run read-only `/health`, `/runtime-status`, `/database-status`, and WebSocket
   handshake checks before any Observation or Event traffic.
8. Copy `config/staging.example.json` to the ignored
   `config/staging.local.json`; fill only the actual Render hostname and newly
   generated staging tokens.
9. Validate with the separately approved hostname:

   ```powershell
   dart run tools/validate_field_staging_config.dart `
     config/staging.local.json `
     --approved-host <actual-staging-hostname>
   ```

10. Verify no secret or local config is tracked. Check `adb devices -l` for at
    least one authorized physical device.
11. Build only through:

    ```powershell
    .\tools\build_staging_apk.ps1 `
      -ApprovedStagingHost <actual-staging-hostname>
    ```

12. Install and run the first 1-node, 5–10 real-detection smoke from
    `docs/performance/phase4_field_runbook.md`. Stop on the first failed gate.

Production resources, localhost, emulator, synthetic timestamps, and projected
metrics cannot satisfy any gate.
