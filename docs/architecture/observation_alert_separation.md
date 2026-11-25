# Observation / Alert 分離設計（第一輪，無 migration）

## 結論與目前行為 audit

答案是 **YES**：目前 10 秒 target cooldown 會造成 tracking observation starvation。

Flutter 在 AI 完成後先呼叫 `EventAdmissionController.evaluate()`。同一裝置、同一 target bucket 距離上次接受事件未滿 10 秒時，程式會刪除暫存音檔並直接 `return`。`event_id`、`AudioEvent` 與 `startEventCloudPipeline()` 都在這個 return 之後才建立或執行。因此被 cooldown 擋下的有效 detection：

- 不會呼叫 Backend `/events`；
- 不會寫入 `events`；
- 不會進入 fusion；
- 不會形成 tracking measurement；
- 不只是「不通知使用者」，而是 observation 完全消失。

以 1.5 秒 hop、10 秒 cooldown 計算，一個持續目標在理想情況下每 10 秒約產生 6–7 個有效 AI observations，但目前通常只有第一個進 Backend。約 85% 的中間觀測可能在 App 端消失，實際比例受 window/hop 與 AI 結果影響。

這份文件只定義下一版語意。第一輪不改 production cooldown、不建立資料表、不執行 migration。

## 四層模型

### 1. Observation

每個通過 AI validity threshold 的 1.5 秒 hop 都是一筆 immutable observation。它是 fusion/tracking 的輸入，不等同 user alert，也不應受 alert cooldown 控制。

```json
{
  "message_type": "observation.v1",
  "observation_id": "obs_<uuid-or-device-sequence>",
  "device_id": "node_A01",
  "observed_at": "2026-08-25T00:00:00Z",
  "event_time_ms": 1787590000000,
  "sequence": 18422,
  "process_session_id": "<app-process-id>",
  "hop_duration_ms": 1500,
  "label": "drone",
  "confidence": 0.93,
  "aircraft_probability": 0.04,
  "rms_peak": 0.51,
  "estimated_peak_db": 78.4,
  "location": {
    "latitude": 25.033,
    "longitude": 121.565,
    "accuracy_m": 8.0
  },
  "time_sync": {
    "version": 1,
    "quality": "good",
    "offset_ms": 12.1,
    "rtt_ms": 31.0,
    "age_ms": 4500
  },
  "audio_ref": null,
  "model_id": "v1_1_0_flower_drone_audio",
  "model_name": "V1.1.0 花收音 5 類模型",
  "ai_inference_time_ms": 42,
  "window_duration_ms": 3000,
  "hop_duration_ms": 1500,
  "sample_rate_hz": 16000,
  "trace_id": "obs_<same-as-observation-id>",
  "alert_candidate": true,
  "schema_version": 1
}
```

`event_time_ms` 是 measurement event time。App monotonic clock 只可計算 App 內 duration，不可作跨裝置 fusion timestamp。

### 2. Fused Event

Backend 依 event time、位置、label 與節點集合，將一至多個 observations 附加至 fused event。這一層可接受 late attach，並以 revision 表示區域估計更新。

```json
{
  "message_type": "fused_event.v1",
  "fused_event_id": "<event_groups.id>",
  "revision": 4,
  "label": "drone",
  "first_event_time_ms": 1787590000000,
  "last_event_time_ms": 1787590004500,
  "observation_ids": ["obs_1", "obs_2", "obs_3"],
  "reporting_device_ids": ["node_A01", "node_A02"],
  "region": {
    "type": "multi_node_region",
    "center_lat": 25.0331,
    "center_lng": 121.5652,
    "uncertainty_radius_m": 42.0
  },
  "schema_version": 1
}
```

### 3. Track Update

Tracker 只消費 observation/fused-event 產生的 event-time measurement。短 reorder buffer 可存在這條 post-ingest path；它不得位於 `/events` ACK 或首次 `event_trigger` 前方。

```json
{
  "message_type": "track_update.v1",
  "track_id": "<target_tracks.id>",
  "track_revision": 18,
  "measurement_event_time_ms": 1787590004500,
  "source_fused_event_id": "<event_groups.id>",
  "source_observation_ids": ["obs_2", "obs_3"],
  "filtered_lat": 25.0332,
  "filtered_lng": 121.5654,
  "speed_mps": 18.2,
  "heading_deg": 74.0,
  "discarded": false,
  "schema_version": 1
}
```

### 4. Alert

Alert 是 UI/使用者通知。它可以維持每裝置/目標 10 秒 cooldown。Cooldown 只決定是否建立或更新 alert，不決定 observation 是否上傳。

```json
{
  "message_type": "alert.v1",
  "event_id": "event_<legacy-compatible-id>",
  "triggering_observation_id": "obs_1",
  "fused_event_id": "<event_groups.id-or-null>",
  "track_id": "<target_tracks.id-or-null>",
  "label": "drone",
  "alerted_at": "2026-08-24T15:00:00Z",
  "cooldown_key": "node_A01:target",
  "cooldown_ms": 10000,
  "schema_version": 1
}
```

## ID 關係

- `observation_id`：每個 AI hop 唯一；重送時保持相同 ID，作為 idempotency key。
- `event_id`：保持現有 `/events` 與 Dashboard alert 的相容 ID，不重新定義成 observation ID。它指向觸發該 alert 的 `triggering_observation_id`。
- `fused_event_id`：對應現有 `event_groups.id`；一個 fused event 可包含多個 `observation_id`。
- `track_id`：對應 `target_tracks.id`；一條 track 可包含多個 fused events 與多個 track points。
- 關係為 `Observation N:M Fused Event`（正常為 N:1，但允許 revision/重算）、`Fused Event N:1 Track`、`Alert N:1 Observation`，Alert 對 Fused Event/Track 可先為 null、之後補 attach。

現有 `events.event_id` 不應在同一次 migration 中改語意；否則舊 App retry、Dashboard WebSocket handler 與 API consumer 都可能失去 idempotency。

## 資料流與 latency 邊界

```text
AI valid hop
  ├─ Observation upload ──> persist/dedupe ──> fusion ──> reorder ──> tracker
  └─ Alert admission (10 s)
       ├─ accepted ──> current /events + immediate event_trigger
       └─ suppressed ──> no alert, observation path仍繼續
```

首次 Dashboard `event_trigger` 維持目前 durable event UPSERT 後立即 schedule 的路徑。它絕對不等待 fusion、tracking 或 reorder buffer。

## 未來 DB schema 影響（本輪不執行）

建議後續 migration 分開推出：

1. 新增 `observations`：`observation_id` unique、`device_id`、`event_time_ms`、`sequence`、AI/signal/location/time-sync JSON、`created_at`。索引 `(device_id, event_time_ms)` 與 `(event_time_ms)`。
2. 現有 `event_group_observations` 新增 `observation_id` FK；過渡期保留目前 `event_id` 欄位。
3. 現有 `target_track_points` 新增 `source_observation_ids` JSONB 或 join table，以及明確 `discard_reason`。
4. Alert 第一階段沿用 `events`；只有在查詢與 retention 需求明確後才考慮獨立 `alerts` table。

不建議把每個 1.5 秒 observation 當成完整現有 `events` row：音訊、Dashboard alert 欄位與裝置狀態副作用會放大寫入與 UI 噪音。

## Backward compatibility

- 舊 App 繼續只送 `/events`，Backend 視為「legacy alert + implicit observation」。
- 新 App 在 feature flag 開啟時送 `observation.v1`，並仍以現有 `/events` 送通過 10 秒 cooldown 的 alert。
- Dashboard 在理解 `observation` 前不接收 observation WebSocket message；只接收既有 `event_trigger`、`event_group`、`track_update`。
- Backend 對 observation ID 做 upsert/dedupe，App retry 不得產生新 ID。
- 不改現有 `event_id`、`event_trigger` 或 API response shape；新增欄位皆 optional。

## Network bandwidth estimate

假設每 1.5 秒一筆 observation：每節點 0.667 observations/s、2,400 observations/hour。

- compact JSON 約 0.8–1.2 KB：每節點約 1.9–2.9 MB/hour，約 46–69 MB/day。
- gzip 後 payload 約 0.35–0.6 KB：每節點約 0.84–1.44 MB/hour，約 20–35 MB/day。
- 4 節點 gzip payload 約 3.4–5.8 MB/hour；若每筆各自建立 HTTP request，headers/TLS overhead 可能再增加約 1–3 MB/hour/node。

應沿用 persistent HTTP connection。後續可評估小批次 observation upload，但 batching 不得延遲第一筆 alert，也必須有明確最大等待時間；此需求不構成導入 Redis Streams 或其他 broker 的理由。

## Feature flags 與 rollout

- App：`OBSERVATION_UPLOAD_ENABLED=false`
- Backend：`OBSERVATION_INGEST_ENABLED=false`
- Backend：`OBSERVATION_FUSION_ENABLED=false`
- App/Backend 語意切換：`OBSERVATION_ALERT_SEPARATION_ENABLED=false`
- Tracker 實驗：`TRACKING_REORDER_BUFFER_ENABLED=false`

建議順序：先 App 本地產生 observation ID 與 dry-run counter；再 staging observation ingest；再 fusion shadow compare；最後才讓 tracker 消費。Alert cooldown 全程保持 10 秒。

## Rollback

任一階段發生頻寬、DB write、dedupe 或 tracking regression 時：

1. 關閉 `OBSERVATION_FUSION_ENABLED`，停止 observation 影響 fusion/tracking。
2. 關閉 `OBSERVATION_INGEST_ENABLED` / `OBSERVATION_UPLOAD_ENABLED`，回到目前 `/events` 路徑。
3. 關閉 `TRACKING_REORDER_BUFFER_ENABLED`，tracker 回到現有直接處理。
4. 保留 observation rows 供 forensic 分析；不要在 rollback 自動刪資料。
5. 既有 `event_id`、Dashboard alerts 與 10 秒 cooldown 不變，因此 rollback 不需 DB down-migration。

## 驗收指標

- `valid_ai_observations`、`observations_uploaded`、`observations_deduplicated`
- `observations_attached_to_fusion`、`tracking_measurements_emitted`
- `tracking_late_discarded`、`tracking_duplicate_discarded`
- `alerts_created`、`alerts_suppressed_by_cooldown`
- 比較 `valid_ai_observations : track_points : alerts`；持續目標預期前兩者接近，alerts 約每 10 秒一次。

## V2.3 Phase 3 shadow implementation

第一輪 shadow implementation 保持上述 `observation.v1` ID 與欄位語意，並採以下限制：

- Flutter `OBSERVATION_SHADOW_ENABLED=false` 預設關閉。有效 target 在 alert admission 之前產生 observation，先 transaction 寫入獨立 SQLite queue，再由 retry worker 使用 persistent HTTP client 上傳至 `/observations/shadow`；Alert admission 不等待 SQLite 或 HTTP。完整語意見 `observation_offline_retry.md`。
- `sequence` 從每個 App process/device 的 1 開始單調增加；`process_session_id` 讓 App restart 後的新 sequence domain 不和舊 process 混合。
- Backend `OBSERVATION_SHADOW_ENABLED=false` 與 `OBSERVATION_TRACKING_ENABLED=false` 預設皆關閉。
- Shadow ingest 使用 bounded in-memory registry；不建立、讀取或修改 production observation/event/track table。相同 `observation_id` idempotent；`observed_at`/`event_time_ms` 與 server `received_at` 同時保留。
- Schema 使用 `extra=forbid`，因此 `audio_path`、MP3、GCS、TDOA 或其他未定義欄位會被拒絕，不可能由 shadow payload 觸發 audio pipeline。
- Shadow tracking 使用獨立 executor、per-device process sequence gate、per-region event-time track state，以及每 hop 的 lightweight weighted-region shadow fusion。它不呼叫 Dashboard broadcast，也不共用 control track table。
- Shadow fusion 的 node-position centroid 只用於比較 observation density/order，不宣稱是正式 target localization；沒有 Kalman、moving average、interpolation 或 trajectory smoothing。
- `GET /observations/shadow/metrics` 回傳 ingest sequence diagnostics、shadow tracking point intervals，以及既有 control discard counters。這個 endpoint 和 ingest 一樣需要 upload token。

## V2.3 Phase 4 ordered field shadow

Phase 4 保留 `observation.v1` 與 Phase 3 Alert 邊界，新增 production-oriented、但仍預設關閉的 shadow 元件：

- Sequence identity key 固定為 `(device_id, process_session_id, sequence)`；App restart 建立新的 process session，sequence 可從 1 重來。
- `observed_at`/`event_time_ms` 仍是 measurement time；sequence 只做 dedup、gap、out-of-order 與 bounded missing timeout。
- Sequence gate 之後使用 per-region serialized mailbox。同一 region update 不並行；不同 region 由獨立 worker 平行，禁止 global queue。
- 跨裝置 fusion 依 event-time hop bucket 合併。已存在 bucket 的晚到節點形成明確 revision/late attach；超出 bounded window 的資料增加 `fusion_late_drop_count`，不得 silent corruption。
- Registry、dedup tombstones、sequence keys、mailbox、fusion buckets 與 tracks 都有 TTL/max/cleanup。Backend restart 仍會清空 in-memory shadow state；App queue 可重送，但跨 Backend restart 的 idempotency 仍是已知風險。
- `time_sync` 增加 device wall/monotonic snapshot。Monotonic drift/jump 只在同一 device/process session 內計算，不跨裝置相減。
- App field log 與 Backend metrics 可 reconciliation `raw target -> created -> attempted -> uploaded -> received -> unique -> sequence -> fusion -> tracking -> point`。
- `audio_ref` 仍只能是 null；Phase 4 不寫 production DB、不送 Dashboard、不觸發 audio pipeline。

實際 field 執行與證據門檻見 `docs/performance/phase4_field_runbook.md`。在真實 Android/staging、Alert OFF/ON latency、clock、bandwidth 與長時間 memory 證據完成前，不得進入 filtering/localization tuning。
