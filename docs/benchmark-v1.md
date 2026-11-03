# Drone Audio Benchmark V1 API

V1.1 compatibility: Session accepts both `native-wav-ai.v1` (original per-byte writer) and `native-wav-ai.v2` (byte-identical bulk WAV writer), and adds `protocol_version` (old sessions default to `benchmark.protocol.v1`; new clients send `benchmark.protocol.v1.1`). CSV exports retain both fields, so results from different implementations/protocols can be kept separate. No SQL change is needed because metadata is stored as validated JSON. Criteria remain `benchmark.v1`; new clients use >=15 seconds and >=8 samples for warmup and require >=30 samples before latency overload early-stop. Latency-budget failures alone do not stop descending; two consecutive runs with >=30 generated windows and >=25% loss do. No measured improvement is claimed before physical retesting.

This is an opt-in addition to FastAPI. Existing event, fusion, tracking, TDOA and dashboard code paths are unchanged. `main.py` mounts `/benchmark/*`; `uvicorn benchmark_app:app` can also run the isolated API without importing the monitoring application. No automatic migration or deployment occurs.

## Database and configuration

Use a dedicated PostgreSQL database or at least a dedicated role restricted to the two benchmark tables. The same deployed FastAPI service and HTTPS hostname can serve monitoring and benchmark requests. `BENCHMARK_DATABASE_URL` may point to the existing PostgreSQL database after an operator explicitly applies the migration; it is deliberately never inferred from `DATABASE_URL`.

1. Back up and review the target database and permissions.
2. Explicitly apply `psql "$BENCHMARK_DATABASE_URL" -v ON_ERROR_STOP=1 -f migrations/v7_benchmark.sql`. The migration creates only `benchmark_sessions`, `benchmark_runs`, and their index, inside a transaction. Reapplying it is safe. Never run it against production without authorization.
3. Configure `BENCHMARK_ENABLED=true`, `BENCHMARK_DATABASE_URL`, and a random `BENCHMARK_ADMIN_TOKEN` of at least 32 characters on the server. The admin token must never be put in the APK.
4. Deploy the reviewed branch only when authorized. Test `/benchmark/*` over HTTPS before distributing an upload-enabled APK.

SQLite (`sqlite:///absolute/path/benchmark.db`) is supported for isolated development and automated tests. Apply the same SQL explicitly with sqlite3.executescript. The server never creates tables on startup. Use PostgreSQL for shared collection.

## Authentication and API

Clients generate a UUID v4 session ID and 32 random bytes encoded as 64 lowercase hex characters. The per-session credential is sent as `Authorization: Bearer <session-secret>`. Only its SHA-256 is stored on the server. A UUID alone cannot overwrite another tester's session. There is no public endpoint for listing or reading another tester's results.

* `POST /benchmark/sessions`: immutable device/model metadata; required fields and limits are in the generated OpenAPI schema (`/openapi.json`, `Session`). Includes brand/model/Android/ABI/cores/RAM/app version, model ID/version/SHA-256, metadata SHA-256, actual tensor shapes, inference settings, pipeline version and start time. Repeat the identical session with its original secret to retry safely. Returns HTTP 200 with `stored: true` and `session_id` only after transaction commit.
* `POST /benchmark/results/batch`: final `Batch` containing session UUID, completion time, status/reason, `criteria_version: benchmark.v1`, and up to 18 survey/confirmation runs with raw per-window duration samples. Server independently recomputes stability and recommendations. Each run's generated count must equal processed + dropped; processed must equal raw sample count. The completed batch is immutable; identical retries are idempotent, conflicting retries return 409. Returns HTTP 200 with `stored: true`, UUID, canonical result SHA-256 and computed Hop decisions after commit.
* `GET /benchmark/admin/export.csv`: `Authorization: Bearer <BENCHMARK_ADMIN_TOKEN>`. UTF-8 BOM CSV, one row per run (also includes sessions without runs). Includes device/model identity, status, all seven timing metrics with P50/P95/P99/average/max, counts, CPU time, thermal/backlog, pass/fail reasons and Hop decisions. CSV formula-like cell contents are escaped.

Upload example structure (see OpenAPI for full required fields): `{"session_id":"...","completed_at":"...Z","status":"completed","reason":"completed","criteria_version":"benchmark.v1","runs":[...]}`. Do not add GPS, audio, account IDs, hardware identifiers or arbitrary fields: unknown fields are rejected.

Administrator export (server token supplied via your secret manager/environment):

```sh
curl --fail --header "Authorization: Bearer $BENCHMARK_ADMIN_TOKEN" \
  "$BENCHMARK_BASE_URL/benchmark/admin/export.csv" --output benchmark-all.csv
```

## Measurement contract

Fixed 16 kHz mono PCM16, 3000 ms window; hops 1500/1000/750/500/350/250/200/150/100 ms. `native-wav-ai.v1` uses the monitoring application's actual AudioRecord, native WAV writer, Dart isolate feature preprocessing and TFLite interpreter. No audio is uploaded. Raw samples contain sequence, Android window-ready monotonic timestamp, native queue/save durations, bridge upper bound, Dart pending delay, preprocessing time, interpreter invocation time, pipeline upper bound and success.

`pipeline_upper_ms` is Android elapsedRealtime at the post-inference MethodChannel acknowledgment minus Android elapsedRealtime at window-ready. It is a conservative upper bound, including return-channel overhead. No Dart timestamp is subtracted from Android time. `bridge_upper_ms` uses a pre-inference acknowledgment and also includes Dart pending delay; timing stages therefore overlap and must not be summed. Dart stage durations use Stopwatch. CPU milliseconds represent process CPU time over the run, not CPU utilization. Thermal is nullable below Android 10.

Nearest-rank percentiles. Survey requires at least 30 processed samples. Confirmation requires at least 60 samples and 120 seconds (maximum 180 seconds). Passing requires success >=99%, dropped/generated <=1%, pipeline P95 < hop, bounded stage occupancy <=2, no thermal status >=3, no errors. Recommendation additionally requires P95 <0.8*hop. Lowest operating hop means >=30 samples, all inference calls successful and no recorded errors; it does not imply stability. Lowest stable and recommended hops require confirmation. Bounded native and Dart queues prevent growing backlog; saturation is reflected in drops. A two-minute confirmation is limited evidence, not a claim about hours of operation. Hop is not onset-to-detection latency.

## Abuse controls and operation

Strict allowlisted payloads, finite/nonnegative timings, count constraints, 4 MiB streamed request limit, 60 valid ingestion/export attempts per source IP per hour per process, at most 10,000 live IP counters, ownership checks, immutable results, and authenticated administrator export. No forwarded IP headers are trusted by the application. Run a single worker for the in-process quota or add shared rate limiting at a trusted reverse proxy before scaling. Configure ingress request size/time limits and storage quotas. Anonymous clients can fabricate measurements; this research collector does not provide device attestation. Export buffers the CSV in memory; use bounded research cohorts, and add streaming/pagination if collection becomes large. Keep admin credentials restricted and do not log Authorization headers.

## Tests

`python -m pytest tests/test_benchmark.py -q` exercises SQLite. To test PostgreSQL, set `BENCHMARK_TEST_POSTGRES_URL` to a **disposable dedicated database**; these fixtures DROP and recreate only the two benchmark tables in that database. Do not point this variable at a shared database. Full regression: `python -m pytest -q`. Optional Redis tests require `requirements-events-redis.txt`.

No production schema or deployed service was changed during development.
