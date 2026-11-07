# Latency Diagnostics staging / Android field runbook

## Deployment gate (must all be independently verified)

This repository contains a blueprint, not proof that a staging service exists.
Record the Render staging service ID, URL, owner and deploy permission. In its
Settings/Environment verify repository and `feat/latency-diagnostics-staging`,
`APP_ENV=staging`, a separate database project/host and database role, separate
GCS bucket/service account, and staging-only upload/admin tokens. Do not store
secret values in the evidence. Compare resource IDs with production read-only;
a service name or the Dashboard's STAGING badge does not establish isolation.
If any item is unknown, stop deployment. Do not create paid resources or use
production as a fallback. PR #5 remains Draft and is never merged.

## Deploy an already approved isolated service

1. Verify local branch is clean, fetch PR #5 HEAD and record full SHA. Run:
   ```sh
   python -m pip install -r requirements.txt -r requirements-dev.txt
   python -m pytest -q tests/test_latency_diagnostics.py tests/test_latency_integration.py
   python -m pytest -q tests/test_dashboard_v2_2_parity.py
   python -m pytest -q
   ```
   Run each `tests/js/test_*.js` using Node. Run `node --check` for each static
   JS file and rendered inline script; run `python -m compileall -q main.py services app tools`.
2. On **the verified staging service only**, select the PR branch and manual
   deployment of the recorded commit. `render.staging.yaml` is the reference:
   auto-deploy is off, one Uvicorn worker, existing resource settings retained.
   Set staging `DASHBOARD_V2_ENABLED=true` to expose the diagnostics panel.
   For solver measurements staging must have `LOCALIZATION_ENABLED=true`;
   record GCC-PHAT/tracking flags and keep them constant within a run.
   Never apply this blueprint to an existing production service.
3. Build: `pip install -r requirements.txt`; start:
   `uvicorn main:app --host 0.0.0.0 --port $PORT --workers 1`.
   Provision/init the **test database** using the project's deployment process
   before testing; retain `POSTGRES_SCHEMA_AUTO_INIT=false`.
4. Require `/health` HTTP 200, healthy status, no database init error;
   `/runtime-status` HTTP 200 with exact `build.render_git_commit`, sample_window
   256, stages, pending_jobs, peak_pending_jobs. Reject stale/mismatched versions.
5. Open `/dashboard`, System status: verify empty samples initially, then
   P50/P95/P99/count/queues and Browser message handler P95 after test traffic.
   Observe the existing 30-second runtime refresh, WS reconnect, node state,
   alerts and map. Confirm no console exceptions; a missing Maps key is not a
   successful Google Maps validation.
6. With only staging Android nodes/tokens configured, trigger a few clearly
   labelled smoke events. Save before/after JSON and verify relevant stage
   counts/last values change (counts saturate at 256). Wait for queues to drain.
   Save Render logs and CPU/memory graphs over the same UTC interval. Require
   no new exceptions, OOM, restarts or connection exhaustion before field work.
   Stop traffic if any occur; any rollback targets staging only.

## Capture 30–50 real multi-node episodes

1. Allocate a run ID and create a private evidence directory. Synchronize host
   and phone clocks; record UTC plus each device's RTT, sync age/quality. UTC
   aligns evidence approximately; it cannot replace within-process monotonic
   timing or prove one-way network latency.
2. Record commit, Android app/model version, participating device IDs/count,
   geometry/spacing, network type (Wi-Fi/cellular), signal conditions, staging
   instance size/workers, localization/GCC flags and DB pool configuration.
   Keep algorithms, resource allocation and configuration fixed for the run.
3. Start the read-only collector below 60 seconds before the first event. Keep
   it running through the test and for 60 seconds after the last event. Use
   a fresh output filename for every run; it refuses overwriting evidence.
   ```sh
   python tools/collect_latency_diagnostics.py --base-url https://VERIFIED-STAGING-HOST --expected-commit FULL_40_CHARACTER_SHA --isolation-confirmed --samples 720 --interval 5 --output artifacts/RUN_ID/runtime.jsonl
   ```
   `--isolation-confirmed` records operator intent; it does not discover or
   verify isolation. The collector makes GET requests only, rejects redirects
   and stops on health/version/schema errors. It records aggregate metrics,
   not CPU/memory or individual latency samples. Its HTTP duration is the
   collector round trip, not event latency.
4. Use the real Android microphone/inference/upload path with at least the
   eligible node count required by the current solver (typically 3+ with valid
   timing/geometry). Record excluded/fallback episodes rather than discarding
   them. Plan 40 episodes: 10 warm baseline, 20 representative conditions,
   10 closer-spaced events within safe staging load. Label warmup separately;
   do not assert statistical precision for P99 from this small sample.
5. For each episode save event/trace/group IDs from existing responses/logs,
   UTC start/end, device count and network conditions in `episodes.csv`. Capture
   existing optional latency traces when present; do not inject simulated
   records to reach the target. Save browser handler P95/count at the same
   timestamp using the visible panel, and note errors/reconnects.
6. At approximately 5-second intervals, or the console's available resolution,
   export Render CPU/memory and test PostgreSQL active/idle/waiting/total/max
   connections. Put values in `resources.csv` with actual observation UTC and
   source. Use empty cells plus a reason when unavailable, never zeros. Prefer
   existing monitoring; any SQL observation must use the isolated test DB and
   read-only credentials. Record Render log start/end and restart/OOM markers.
7. Finish by checking queue drain, matching commit, and no restarts. Preserve
   raw JSONL, episode/resource CSVs, log export and screenshots under the run ID.

### Collection formats (header-only templates, no fabricated measurements)

`episodes.csv`:
```csv
run_id,episode_id,start_utc,end_utc,event_ids,trace_ids,group_id,device_ids,device_count,network_type,network_conditions,android_version,model_version,backend_commit,sync_rtt_ms,sync_age_ms,sync_quality,result_status,browser_handler_p95_ms,browser_sample_count,notes
```

`resources.csv`:
```csv
run_id,observed_at_utc,source,render_service_id,cpu_percent,memory_mb,memory_limit_mb,db_active,db_idle,db_waiting,db_total,db_max_connections,restarts,oom_events,missing_reason
```

`run.json`: record operator, run ID, UTC bounds, service/database/bucket IDs
(no credentials), isolation evidence reference, commit, node versions, topology,
feature flags, resource/pool settings, collector interval and test category
(`real_android`, `local_synthetic` or `staging_smoke`). Do not mix categories.

## Analysis checklist

- A 256-sample rolling count is not a cumulative event counter. Adjacent
  snapshots overlap; do not concatenate their quantiles or count them as
  independent observations. A deploy/restart begins a new measurement epoch.
- Stages have different eligibility and error populations. Never sum stage
  P95s into an end-to-end P95, subtract marginal quantiles to infer a component,
  or compare different stages as though they measure the same events.
- Sustained queue wait/pending with CPU saturation suggests worker/CPU pressure;
  fusion time plus DB waits suggests DB/advisory-lock contention; long solver
  time suggests solver CPU cost; compute much longer than solver suggests
  other localization work (including GCC audio). These are hypotheses needing
  correlated evidence, not conclusions from this runbook.
- Slow broadcast can reflect slow clients. Browser message timing covers the
  synchronous handler after successful JSON parsing, before diagnostic panel
  redraw; it excludes rendering/paint, parsing, network and deferred work.
- Current aggregates cannot supply per-episode stage distributions or exact
  end-to-end latency. If existing event traces lack the necessary spans, mark
  that result unavailable; do not manufacture it from aggregate P95s.
- Without real measurements no production bottleneck or capacity claim is valid.
