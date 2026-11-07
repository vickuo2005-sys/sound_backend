# HTTP／WebSocket／Gateway contract

以 2026-11-07 baseline 的 [`../main.py`](../main.py)、[`../app/protocol/`](../app/protocol/) 為準。Production／staging base URL 見 [Deployment](DEPLOYMENT.md)。本次不新增 route、不修改 schema、不執行 test ingest。

## 常用讀取介面

| API | 參數／結果 | 驗證注意 |
|---|---|---|
| `GET /health` | `status`、`database_init`、時間 | liveness；200 不證明 DB 可查詢，schema init 可能被跳過 |
| `GET /runtime-status` | `build.render_git_commit`／branch／service、非 secret flags、runtime 狀態 | 只保存必要摘要，不公開整份 runtime dump |
| `GET /events` | `limit=20`，1–100；`status`、`count`、`events` | DB 錯誤時可能 HTTP 200 + `status=degraded` |
| `GET /tracks` | `limit=20`，1–100；`points_limit=20`，0–100；可選 `status`／`label` | 可能 HTTP 200 + degraded；非 freeze 時可觸發 stale-track 關閉維護，不是純 DB SELECT |
| `GET /event-groups` | `limit=20`，1–100；可選 `status`／`label` | `event_groups`；錯誤可能 500 |
| `GET /device-status` | 節點、監聽／上傳／連線相關狀態 | 離線固定節點仍可顯示，不等同 online |
| `GET /device-locations` | 固定節點位置 | 不等於無人機座標 |
| `GET /events/{event_id}/context` | 事件與回放 context | 舊資料可能缺音訊或 group／track |
| `GET /events/export.csv` | CSV | 僅匯出必要資料，輸出另作權限／內容審查 |
| `GET /dashboard` | 新版或 fallback HTML，由 flag 決定 | 200 仍須確認渲染、Console 與連線 |

其他介面（包含 admin／delete）完整列於文末。表列代表 route 存在，不表示本次已測所有參數或允許在 production 呼叫。

## Canonical event ingest

`POST /events` 使用 `SoundEvent`。必要欄位為 `event_id`、`device_id`、`timestamp`；`timestamp` 應為帶時區 ISO-8601，epoch milliseconds 則放入 `device_event_time_ms` 等 timing 欄位。上傳授權使用 `x-upload-token`；secret 僅由受控環境提供，文件不提供值。

下例為合成契約示例，不代表真實飛行測量，也不在 production 執行：

```json
{
  "event_id": "gateway-node-01-session-demo-000042",
  "device_id": "gateway-node-01",
  "timestamp": "2026-11-07T00:00:00Z",
  "device_event_time_ms": 1794009600000,
  "label": "Drone",
  "latitude": 25.039,
  "longitude": 121.5752,
  "classification": {
    "schema_version": "classification.v1",
    "model_id": "vendor-demo-model",
    "model_version": "1",
    "model_label": "Drone",
    "confidence": 0.92,
    "class_scores": {
      "Airplane": 0.03,
      "Car": 0.03,
      "Drone": 0.92,
      "Electric_saw": 0.01,
      "Rainfall": 0.01
    },
    "operational_class": "drone",
    "aircraft_probability": 0.95,
    "is_target": true
  }
}
```

Classification block 是 optional；啟用時五類 scores 必須齊全、有限且介於 0–1，top label／confidence 必須一致，server 會重建 operational fields。`latitude`／`longitude` 是回報來源位置，不能假定為真實無人機座標。詳細 schema 見 [`../services/classification.py`](../services/classification.py)。

成功回應包含 `status=success`、`message=Event received`、原 `event_id` 與 `db_id`，可能附 classification／latency metadata。這是初始持久化成功回應，不保證 fusion、tracking、GCS 或每個 Dashboard 都已完成。

### 冪等與重送

- `event_id` 是 `events` DB UPSERT 的唯一識別。重送保留同一 ID、原量測時間及來源；不要為每次 retry 產生新 ID。
- 同 ID 可更新 metadata（例如後到的音訊欄位），不是 immutable insert。既有事件不重排新的 canonical post-ingest，但其他 cache／狀態／WebSocket 更新仍可能發生。
- Gateway 可用穩定 node＋持久 session＋sequence 產生 ID；必須防止重開機後重用舊 ID。此組合是 adapter 設計建議，尚未成為新的 API 欄位保證。
- timeout／斷線可能發生在 DB commit 之後；以原 ID 重試並核對資料，不宣稱端到端 exactly-once。尤其 fusion／tracking／DB／WS 之間沒有統一原子 ACK。
- Gateway 建議持久 outbox、bounded exponential backoff＋jitter，對 408／429／暫時性 5xx／transport failure 有界重送；401／403／422 先修正認證或 payload，不能無限重試。這是待實作的 Gateway contract，並非 Backend 已代管供應商 queue。
- Observation shadow 與 Redis 的冪等／ACK 是不同層級；in-memory dedupe 不跨 Backend restart 保證。見 [Consumer idempotency](event_consumer_idempotency.md) 與 [Observation retry](architecture/observation_offline_retry.md)。

## Wi-SUN Gateway connectivity test

`POST /api/test-gateway`：驗證 upload token 後接受任意 JSON object、記錄 payload keys 與接收時間並 echo；不寫 DB、不觸發正式事件／定位／tracking。用途為 local／staging 的供應商連通測試。Route 本身沒有「僅 staging」的環境限制，不能把操作政策當作 server 技術隔離。

```json
{
  "node_id": "gateway-node-01",
  "event_time_ms": 1794009600000,
  "label": "Drone",
  "confidence": 0.92,
  "active": true,
  "sequence": 42,
  "latitude": 25.039,
  "longitude": 121.5752
}
```

回應為 `status=ok`、`message=gateway payload received`、`received_at_ms`、`received` 原 object。目前 `node_id/event_time_ms/label/confidence` 是預計 adapter 核心欄位，`active/sequence/latitude/longitude` 為建議欄位；此 test endpoint **不驗證其業務 schema**。

正式 adapter 尚需將 `node_id → device_id`、量測時間轉為 `timestamp`／timing metadata、confidence 轉為完整 classification contract。只把此 JSON 直接送 `/events` 不是已完成整合。HTTP echo、Wi-SUN delivery ACK、Gateway outbox ACK、DB ingest ACK、Dashboard 顯示是不同層級。

## WebSocket

| Path | 用途／限制 |
|---|---|
| `/ws/dashboard` | 正式 Dashboard 即時更新；例如 `event_trigger`、`event_audio_update`、節點／track updates。重連後以 HTTP snapshot 補齊並保留 event-order guard；不是 durable message queue |
| `/ws/node/{device_id}` | node 控制／heartbeat，受 flag 控制；10 秒內先送 matching device 的 `hello`，再處理 hello ACK、heartbeat、command ACK／result |
| `/ws/audio/{device_id}` | optional binary live audio；受 stream token／協定／flag／backpressure 控制 |
| `/ws/audio-monitor/{stream_id}` | 音訊訂閱；需對應 subscriber token，不能把 token 放文件或 URL |

Node hello envelope 範例（非認證 secret）：

```json
{
  "protocol_version": 1,
  "message_type": "hello",
  "device_id": "gateway-node-01",
  "message_id": "demo-hello-0001",
  "sent_at_ms": 1794009600000,
  "payload": {"app_version": "vendor-adapter-demo"}
}
```

`/device-command`、REST polling、command ACK／result 與 audio frames 詳見 [Node protocol](architecture/node_control_protocol.md)、[Binary audio](architecture/audio_binary_protocol.md)。控制 ACK 不等於命令成功執行；要看 result／final status。本文不以所有 mutation 都共享同一認證政策為前提，各 route 仍以 source 檢查為準。

## Error 與診斷

錯誤可能包含 401、422、功能／維護停用的 503、DB 失敗的 500；部分讀取 route 為 HTTP 200 + degraded。檢查 HTTP code、JSON status、build、資料來源與 logs，不能只看 health。不要把回傳的 raw error detail、音訊 signed URL、stream token 或整份 runtime snapshot 複製進 Git。

## 完整 route inventory

由 baseline `main.py` 的 route decorators 盤點，48 個 HTTP routes、4 個 WebSocket routes；FastAPI 自動產生的 `/docs`／`/openapi.json` 不計入。HTTP mutation／admin routes 只列名，不在本次執行。另注意 `/device-command/{device_id}` polling 也有 heartbeat／命令狀態語義，不應當作完全無副作用的 smoke。

| Method | Path | Handler（main.py） |
|---|---|---|
| POST | `/api/test-gateway` | `test_gateway_ingest` |
| GET | `/` | `root` |
| GET | `/health` | `health` |
| GET | `/runtime-status` | `runtime_status` |
| GET | `/database-status` | `database_status` |
| GET | `/time-sync` | `time_sync` |
| POST | `/diagnostics/db-latency` | `measure_staging_database_latency` |
| POST | `/observations/shadow` | `ingest_shadow_observation` |
| GET | `/observations/shadow/metrics` | `shadow_observation_metrics` |
| POST | `/events` | `create_event` |
| GET | `/target-estimates` | `target_estimates` |
| GET | `/event-groups` | `event_groups` |
| GET | `/event-groups/{group_id}` | `event_group_detail` |
| GET | `/event-groups/{group_id}/localization` | `event_group_localization` |
| POST | `/event-groups/{group_id}/localize` | `event_group_localize` |
| GET | `/localization-results` | `localization_results` |
| GET | `/event-groups/{group_id}/tracks` | `event_group_tracks` |
| GET | `/tracks` | `tracks` |
| GET | `/tracks/{track_id}` | `track_detail` |
| GET | `/tracks/{track_id}/points` | `track_points` |
| POST | `/admin/rebuild-tracks` | `rebuild_tracks_admin` |
| DELETE | `/admin/tracks/single-point` | `delete_single_point_tracks_admin` |
| DELETE | `/admin/tracks/implausible` | `delete_implausible_tracks_admin` |
| POST | `/tracks/{track_id}/close` | `close_track_endpoint` |
| POST | `/localization-results/{result_id}/track` | `localization_result_track` |
| GET | `/events` | `list_events` |
| GET | `/events/{event_id}/context` | `event_context` |
| DELETE | `/events/{event_id}` | `delete_event` |
| POST | `/location-update` | `update_location` |
| GET | `/device-status` | `device_status` |
| DELETE | `/device-status/{device_id}` | `delete_device_status` |
| GET | `/device-locations` | `device_locations` |
| GET | `/device-locations/{device_id}` | `device_location_detail` |
| PUT | `/device-locations/{device_id}` | `put_device_location` |
| DELETE | `/device-locations/{device_id}` | `clear_device_location` |
| POST | `/device-command` | `device_command` |
| GET | `/device-command/{device_id}` | `device_command_poll` |
| POST | `/device-command-ack` | `device_command_ack` |
| GET | `/events/export.csv` | `export_events_csv` |
| GET | `/events/{event_id}/audio-content` | `event_audio_content` |
| GET | `/events/{event_id}/audio-url` | `event_audio_url` |
| GET | `/events/{event_id}/tdoa-clip-url` | `event_tdoa_clip_url` |
| GET | `/nodes/live` | `nodes_live` |
| GET | `/audio-streams` | `audio_streams` |
| WEBSOCKET | `/ws/node/{device_id}` | `node_control_websocket` |
| WEBSOCKET | `/ws/audio/{device_id}` | `audio_stream_websocket` |
| WEBSOCKET | `/ws/audio-monitor/{stream_id}` | `audio_monitor_websocket` |
| WEBSOCKET | `/ws/dashboard` | `dashboard_websocket` |
| GET | `/dashboard/legacy` | `dashboard_v4_clean` |
| GET | `/dashboard` | `dashboard` |
| POST | `/upload-audio` | `upload_audio` |
| POST | `/upload-tdoa-clip` | `upload_tdoa_clip` |
