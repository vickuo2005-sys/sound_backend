# V2.3 Phase 4 real Android staging runbook

This runbook only produces valid evidence when a physical Android device and a
dedicated staging Backend are available. Localhost, emulator, replayed AI time,
or a production host must not be labelled field/staging evidence.

## Safety gate

1. Confirm `adb devices -l` lists the expected physical devices.
2. Create ignored Flutter `config/staging.local.json` with `APP_ENV=staging`, a
   real staging-only HTTPS host, staging upload/device tokens, and
   `OBSERVATION_SHADOW_ENABLED=true`.
3. Run `dart run tools/validate_field_staging_config.dart
   config/staging.local.json --approved-host <actual-staging-hostname>`.
   The validator prints token-presence booleans only. It rejects the known
   production host, localhost, missing tokens, and a disabled shadow flag.
4. Backend staging must separately enable `OBSERVATION_SHADOW_ENABLED=true` and
   `OBSERVATION_TRACKING_ENABLED=true`. `TRACKING_REORDER_BUFFER_ENABLED` stays
   false. Enabling or deploying staging is a separately authorized operation.
5. Copy `config/phase4_field_manifest.example.json` outside the repository and
   fill physical-device/network/scenario metadata. Never put tokens in it.

If any gate fails, stop. Do not fall back to the existing development config.

## Raw evidence capture

- Preserve unfiltered `adb logcat -v epoch` output. Flutter emits one
  `[OBSERVATION_SHADOW_FIELD_JSON]` record per upload attempt.
- Poll authenticated `GET /observations/shadow/metrics` every 30 seconds and
  retain the complete JSON snapshots, including the first and last snapshot.
- Preserve Dashboard latency export and DB probe JSON separately. Do not edit
  raw files; derived reports belong in a different directory.
- Use one directory per scenario with manifest, App log, Backend metrics,
  Dashboard export, DB probes, and test notes.

Analyze a scenario with:

```powershell
python -m tools.analyze_phase4_field_shadow `
  --manifest <field-manifest.json> `
  --app-log <adb-log.txt> `
  --backend-metrics <backend-metrics.json>
```

The analyzer rejects a non-staging/production/synthetic manifest. Bandwidth
projections are generated only from captured payload/request samples.

## Required scenarios

1. One node, sustained target, 5 minutes.
2. Two nodes, sustained target, 5 minutes.
3. Four nodes, sustained target, 5 minutes.
4. A01 to A02 to A03 moving target.
5. Target absent for 30 seconds, then returns.
6. Wi-Fi jitter.
7. Temporary network loss.
8. App background to foreground.
9. Node offline then reconnect.
10. Backend restart and explicit best-effort state-loss observation.

For memory, retain snapshots for at least 30 minutes, preferably one hour.
Confirm registry, dedup, sequence state, mailbox pending, and track entries
reach a bound/plateau rather than continuously increasing.

## Alert latency OFF/ON

For 1, 2, and 4 nodes, capture Shadow OFF and Shadow ON separately with at
least 50 joined App/Dashboard events per mode. First produce reports with
`tools/analyze_staging_latency.py`, then compare them:

```powershell
python -m tools.compare_shadow_alert_latency `
  --off-report <shadow-off-report.json> `
  --on-report <shadow-on-report.json> `
  --minimum-samples 50
```

The output is `Shadow ON - Shadow OFF` for p50/p95/p99/max at every stage.
Incomplete samples never produce a pass/fail regression claim.

## Render to Supabase DB probe

Temporarily enable `STAGING_DB_LATENCY_PROBE_ENABLED` only on staging. Capture
`db_acquire_ms`, `db_ping_ms`, and event UPSERT/commit timing with p50/p95/p99/max.
Disable the probe immediately after the bounded run.

## Rollback

Set the App and Backend `OBSERVATION_SHADOW_ENABLED=false`, then set Backend
`OBSERVATION_TRACKING_ENABLED=false`. The App sends no observation request,
the endpoint returns 404, and the existing `/events`, audio, cooldown, and
Dashboard path remains unchanged. No DB down-migration is required because
Phase 4 adds no production schema.
