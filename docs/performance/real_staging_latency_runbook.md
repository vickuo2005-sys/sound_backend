# Real staging post-inference latency runbook

## Preconditions

- 實體 Android 裝置可由 `adb devices -l` 看見。
- `config/staging.local.json` 必須是 `APP_ENV=staging`、HTTPS staging host，且只含 staging token。不要用 production host/token。
- Render staging service 使用 Supabase PostgreSQL、單一 Uvicorn worker，並開啟：
  - `POST_INFERENCE_LATENCY_TRACING_ENABLED=true`
  - `FAST_EVENT_INGEST_ENABLED=true`
  - `STAGING_DB_LATENCY_PROBE_ENABLED=true`（只在 bounded validation 期間）
- Android 與操作 Dashboard 的電腦使用同一 Wi-Fi；兩者 UTC time sync 必須正常。

目前 App 的 `config/staging.local.json` 指向 production host 且 `APP_ENV=development`，因此在修正為真正 staging 設定前禁止執行本 runbook。

## Build 與收集 App local monotonic metrics

```powershell
.\tools\validate_flutter_config.ps1 `
  -ConfigPath config\staging.local.json `
  -Environment staging
.\tools\build_staging_apk.ps1 -ConfigPath config\staging.local.json
adb install -r build\app\outputs\flutter-apk\app-staging-release.apk
adb logcat -c
adb logcat | Tee-Object staging-1-node-adb.log
```

App 每個真實 AI result 會輸出一筆 `[POST_INFERENCE_LATENCY_JSON]`，包含同一 App process monotonic clock 的：

- `ai_finished_at_monotonic`
- `metadata_fast_path_called_at_monotonic`
- `http_request_started_at_monotonic`
- `http_response_received_at_monotonic`

若 retry 跨 App process，`monotonic_trace_valid=false`，分析器會排除該筆。

## Scenario

每個 scenario 都重新清空 log 與 Dashboard sample buffer：

1. 1 node，50 個真實 target AI completions。
2. 2 nodes，合計至少 50 個 joined samples。
3. 4 nodes，合計至少 50 個 joined samples。
4. 前三個皆完成後，才選做 Android 行動網路 scenario。

不得用 `tools/benchmark_post_inference_latency.py` 取代此步驟；該工具的 AI timestamp 是 localhost benchmark 專用 synthetic marker。

## Dashboard export

保持 staging Dashboard 開啟。每個 scenario 完成後，在 DevTools Console 執行：

```javascript
copy(JSON.stringify(window.__postInferenceLatencySamples, null, 2))
```

將內容保存為例如 `staging-1-node-dashboard.json`。Browser local duration 使用 `performance.now()`：`ws_received_at_monotonic` 到 `render_complete_at_monotonic`。不要將它和 App monotonic clock 相減。

## Render ↔ Supabase RTT probe

這是讀取 `SELECT 1` 的 staging-only probe，不建立 event，也不使用 synthetic AI time：

```powershell
python tools\measure_staging_db_latency.py `
  --base-url https://<staging-host> `
  --upload-token <staging-token> `
  --samples 50 > staging-db-probe.json
```

`db_acquire_ms` 是 pool acquisition；`db_ping_ms` 是 Render process 到 Supabase 的 query/fetch round trip；event request 的 `server_db_ms` 則包含實際 event UPSERT/commit。

## Percentiles

```powershell
python tools\analyze_staging_latency.py `
  --nodes 1 `
  --app-log staging-1-node-adb.log `
  --dashboard-json staging-1-node-dashboard.json `
  --db-probe-json staging-db-probe.json `
  --minimum-samples 50
```

對 1/2/4 nodes 分別保存輸出。每段輸出 count、p50、p95、p99、max：

- AI finish → HTTP start（App monotonic）
- HTTP RTT（App monotonic）
- Server DB（Server-Timing）
- Server non-DB（Server-Timing ingest − db）
- WS receive → render（Browser monotonic）
- AI finish → final render（UTC epoch correlation；只有確認 Android/Browser clock sync 後才可採信）
- Render DB pool acquire / Supabase `SELECT 1` RTT

所有原始樣本與 percentile 結果都要保留。不要 smoothing、移動平均或刪除 tail sample。
