# Drone Audio Benchmark V1

## V1.2: explicitly measure the user's earlier 300 ms reference

Local CSV now includes app_version, pipeline_version and protocol_version on every row, including legacy sessions (default protocol v1); JSON retains complete session metadata. An export regression test checks historical-session labeling, column alignment and omission of session credentials.

The user reports previously reaching 300 ms on Redmi 13C; that observation is a reference to retest, not a confirmed result from this benchmark. The sequence is now 1500, 1000, 750, 500, 350, **300**, 250, 200, 150, 100 ms, with 300 included in the actual native Hop guard (4800 PCM samples). Protocol is `benchmark.protocol.v1.2`; pipeline remains `native-wav-ai.v2` and criteria remain `benchmark.v1`. Benchmark flavor versionCode is 5, suffix `-benchmark-v1.2` (ARM64 split code 2005); production/staging version metadata is unchanged. Sideloader can update either prior pilot using the same certificate, preserving local results. The V1.1 improvements below remain active. At most 20 measured runs (10 surveys plus 10 confirmations) may be exported/uploaded; backend support and an explicit existing-PostgreSQL constraint migration are included in companion PR #7. No production schema change is performed automatically.

## V1.1 update after Redmi field test

The original Redmi 23108RN04Y session completed 43/43 inferences with no drops, but measured native WAV save P95 of 2197 ms (1500 ms hop) and 924 ms (1000 ms hop). The original shared complete-window writer performed 96000 single-byte writes per 3-second PCM16 window. V1.1 uses byte-identical little-endian encoding with one bulk write, shared by monitoring and benchmark native code. No monitoring APK is deployed by this change. All 65536 signed PCM16 values and bulk file I/O behavior have JVM tests.

V1.1 records pipeline `native-wav-ai.v2` and protocol `benchmark.protocol.v1.1`; keep original v1 results separate. The classifier/model and PASS/recommendation criteria (`benchmark.v1`) are unchanged. Warmup is now at least 15 seconds AND 8 samples, with a 45-second timeout. Latency failure alone no longer stops descending to smaller hops. Only two consecutive runs with at least 30 generated windows and >=25% observed window loss stop descent. Confirmation latency early-stop requires >=30 samples; interruptions/severe thermal still stop immediately. The benchmark flavor alone increases versionCode to 4 and versionName suffix to `-benchmark-v1.1`; sideload over the old APK using the same signing key to preserve saved sessions. Actual performance improvement still requires the same phone to retest. The following V1 descriptions of three-sample warmup and two-failure descent early-stop are historical; this section supersedes them.

Independent flavor/application ID: `com.example.sound_detector_clean.benchmark`. Entry point: `lib/benchmark_main.dart`. The monitoring entry point, production/staging flavors, event uploads, positioning and GCS paths are not used by the benchmark entry point. The benchmark manifest removes GPS, phone-state, shared storage, boot receiver, monitoring service and unrelated runtime permissions.

## Build and distribute

```sh
flutter pub get
flutter analyze
flutter test
flutter build apk --release --flavor benchmark --split-per-abi --target-platform android-arm64 -t lib/benchmark_main.dart
```

The default build is offline: no collection URL and no network upload. Set `--dart-define=BENCHMARK_BASE_URL=https://your-reviewed-api.example` for a later collection-enabled build after the backend migration/API is deployed. The same existing FastAPI hostname can be used. No administrator secret belongs in this define or in the APK.

Artifact: `build/app/outputs/flutter-apk/app-arm64-v8a-benchmark-release.apk`. ARM64 Android 7+ (minSdk 24). Omit `--target-platform android-arm64` to also build per-ABI APKs for older ARMv7 phones. When no release key exists, this repository's existing signing rule uses the local debug certificate even for release mode: suitable for pilot sideloading, not a production release identity. Keep a stable private signing key outside Git for subsequent releases. No key or token is committed.

Send the APK privately via Drive or another file link. Testers download, allow installation from the sending app if Android asks, install “Drone Audio Benchmark”, open it, consent to the displayed collection scope, grant microphone permission, and press 開始測試. They keep the app foreground until completion. They press 匯出測試結果 to share CSV and JSON back. The exports include all sessions stored on that phone and never include session credentials or audio. Installation/startup/microphone access/inference/sharing still require physical-device verification.

## Pipeline and criteria

The native benchmark uses the same 16 kHz mono AudioRecord, 3000 ms circular window, WAV header/sample writer and MethodChannel event as monitoring; the classifier uses the same Dart isolate preprocessing and TFLite run call. Benchmark adds exact PCM boundary snapshotting for small hops, a bounded native writer queue, and a guarded stop/join/writer barrier before changing hop. The monitoring flavor retains its original boundary generation path and default 1500 ms hop. Native start returns the actual configured hop and run UUID, which Dart checks.

Each hop runs 3 warmup inferences, safely stops/drains, then starts a fresh survey. At least 30 measured samples are needed; survey timeout 90 seconds. After two consecutive failed hops, stop descending. Starting with the smallest passing survey hop, confirm for at least 120 seconds and 60 samples, up to 180 seconds, backing off to larger surveyed candidates if necessary. Continue backing off until the conservative recommendation margin passes. All queues/counters are reset per UUID. Native write occupancy and Dart running/pending occupancy are bounded at 2 each; drops are generated minus processed after draining. This also fixes the original queue's “first pending counts as skipped” behavior for benchmark reports.

`benchmark.v1` uses inference success >=99%, drops <=1%, pipeline P95 < hop, maximum bounded stage occupancy <=2, no severe thermal status (>=3), no errors, and minimum sample/duration requirements. Recommendation adds P95 <0.8*hop. `stats.dart` implements configurable-version criteria centrally. Survey-only results may establish an operating hop, but never a stable/recommended hop. Two-minute confirmation is not a claim of indefinite stability, and hop is not actual sound onset-to-detection latency.

Timing is real. Android elapsedRealtime is queried before inference and after it. Pipeline latency is the conservative same-clock upper bound from native window-ready to the post-inference acknowledgment, including channel overhead. Bridge upper bound includes Flutter pending time and channel return time. These durations overlap and cannot be summed. Flutter queue/preprocessing/interpreter invocation use Stopwatch. All seven timing metrics receive nearest-rank P50/P95/P99/average/max in JSON exports; CSV contains raw samples. CPU is process CPU time, not percentage. Android thermal is unsupported/null before API 29. Silence from another recorder is checked on API 29+; older OS interruption behavior needs device testing.

Pinned choice: existing default `preclassifier`, version `1`. Runtime SHA-256 is computed from loaded model bytes; current asset SHA-256 is `bedaf0d4dd5e71604457e6ecf2496fc631595332743749f0a9d0e4df48c454a4`. Metadata SHA-256, actual input/output tensor shapes, preprocessing pipeline version and TFLite default option identifier are recorded. TFLite Flutter 0.12.1 and existing Interpreter.fromAsset defaults are retained. Existing classifier fallback remains available to monitoring; benchmark uses strict load and cannot silently substitute a model. Existing metadata notes class mapping should be verified before using labels for operational detection; this benchmark evaluates processing performance.

## Durability, privacy and interruptions

Separate SQLite outbox uses transactions. Completed runs are checkpointed; an active measured run is checkpointed every 5 seconds, so process death can lose at most the uncheckpointed tail. Recovery marks the active run interrupted and prevents it passing. In-progress checkpoints are not uploaded. Completed/cancelled/failed sessions remain local regardless of network state. Maximum 100 sessions / conservative 50 MiB logical budget; new records are refused rather than evicting unexported results. Export includes every saved local session. Clearing Android app data/uninstalling removes local results, so export before doing either.

When an HTTPS endpoint is configured, retries run while the app is open and on resume: at most 10 attempts, exponential backoff from 60 seconds up to 6 hours, persisted next-attempt time, at most 5 sessions per sweep. There is no background worker after the app exits; reopening resumes the outbox. Responses must explicitly acknowledge `stored: true` with the matching UUID for session and batch before the UI reports success. Exhausted retries preserve exportable results. Redirects are disabled. Session secrets are random per session, kept in private local storage, and omitted from exports.

No raw audio/GPS/accounts/hardware IDs are collected or uploaded. A user checkbox precedes microphone permission. WAV files are deleted after inference or queue replacement; app creation/new runs remove crash leftovers. Storage is app-scoped. Lifecycle pause/lock cancels the test; native onPause also stops capture. Screen stays awake while foreground. AudioRecord errors, microphone silencing, severe thermal, cancellation and clock/pipeline failures prevent passing. Real device lock/call/permission-revocation/storage failure and OEM audio-sharing behavior remain acceptance tests.

## Test commands

```sh
flutter analyze
flutter test
cd android
./gradlew :app:testBenchmarkReleaseUnitTest
```

Do not run two Gradle builds concurrently against the same worktree. Tests use explicitly synthetic fixtures, never reported as physical benchmark data. Review the final delivery report for actual build and test outcomes.
