# 第一筆 HTTP event、融合與軌跡

對自己的驗收環境使用 `POST /events`，提供 `Content-Type: application/json` 和 `x-upload-token`。`SoundEvent` 只要求三個字串欄位 `event_id`、`device_id`、`timestamp`。timestamp 應使用當下帶時區 ISO-8601。`label` 和節點座標對一般寫入可省略，驗收 fusion／track 時提供 `Drone` 與座標。用 [First Node](FIRST_NODE_GUIDE.md) 的相同 device ID。失敗重送保留同一 event ID，PostgreSQL 以該欄位 UPSERT。

```json
{
  "event_id": "rebuild-unique-event-01",
  "device_id": "node_A01",
  "timestamp": "2026-11-09T01:00:00Z"
}
```

上例時間為示意。以下 script 使用當前時間和 UUID。把區塊存為 `first_event.py`。在 venv 執行 `python first_event.py`。SQLite launcher 可加 `--token-file .local-runtime/upload-token.txt`，其他路徑在 prompt 輸入自己設定的 token。程式只輸出事件 ID／DB ID 與驗收用識別值。

```python
import argparse
from datetime import datetime, timezone
from getpass import getpass
from pathlib import Path
from time import monotonic, sleep
from uuid import uuid4

import httpx

parser = argparse.ArgumentParser()
parser.add_argument("--base-url", default="http://127.0.0.1:8786")
parser.add_argument("--token-file", type=Path)
parser.add_argument("--fusion", action="store_true")
args = parser.parse_args()
token = args.token_file.read_text(encoding="utf-8").strip() if args.token_file else getpass("Your test upload token: ")
assert token, "Upload token is empty"

with httpx.Client(base_url=args.base_url, timeout=15, trust_env=False) as client:
    def read(path):
        response = client.get(path)
        response.raise_for_status()
        payload = response.json()
        assert payload.get("status") != "degraded", f"{path} degraded"
        return payload

    def send(device_id, latitude, longitude):
        event_id = f"rebuild-{uuid4()}"
        response = client.post("/events", headers={"x-upload-token": token}, json={
            "event_id": event_id,
            "device_id": device_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "latitude": latitude,
            "longitude": longitude,
            "label": "Drone",
        })
        response.raise_for_status()
        result = response.json()
        assert result["status"] == "success" and result["event_id"] == event_id
        print("accepted", result["event_id"], "db_id", result["db_id"])
        return event_id

    first = send("node_A01", 25.039, 121.5752)
    event_ids = {first}
    if args.fusion:
        sleep(1)
        event_ids.add(send("node_A02", 25.0393, 121.5755))
    stored_ids = {item["event_id"] for item in read("/events?limit=100")["events"]}
    assert event_ids <= stored_ids
    print("events visible via GET")
    if args.fusion:
        deadline = monotonic() + 20
        while monotonic() < deadline:
            groups = read("/event-groups?limit=20")["event_groups"]
            for group in groups:
                if group.get("node_count", 0) < 2 or group.get("region_type") != "segment":
                    continue
                group_id = group["id"]
                detail = read(f"/event-groups/{group_id}")["group"]
                members = {item.get("event_id") for item in detail["observations"]}
                if not event_ids <= members:
                    continue
                tracks = read(f"/event-groups/{group_id}/tracks")["tracks"]
                if tracks and any(track["point_count"] > 0 for track in tracks):
                    print("fusion and persisted track", group_id, tracks[0]["id"])
                    break
            else:
                sleep(0.5)
                continue
            break
        else:
            raise SystemExit("No two-node region with persisted track. Check schema, positions, time window and flags.")
```

使用 `--fusion` 前，在自己的新驗收庫啟動 `node_A01` 與 `node_A02`。兩筆目標聲音使用不同位置與相近、遞增的時間。上例用新庫避免先前群組影響結果，並核對兩個 event IDs 都屬於找到的 group。區域與軌跡在 post-ingest 背景處理後才會出現。

## 核對 DB 與 Dashboard

成功回應 HTTP 200，`status=success`、`message=Event received`、同一 `event_id` 與整數 `db_id`。缺少或錯誤 token 預期 401（已配置 token 的情況），缺必要欄位預期 422。DB 寫入失敗查看 backend logs。`GET /events` 可能以 HTTP 200 回 degraded，必須看 JSON。

在自己的 PostgreSQL psql session 查詢。以實際列印的 ID 取代下方示意值。

```sql
SELECT id, event_id, device_id, label FROM events
WHERE event_id = '<YOUR_EVENT_ID>';

SELECT event_id, group_id FROM event_group_observations
WHERE event_id IN ('<FIRST_EVENT_ID>', '<SECOND_EVENT_ID>');

SELECT track_id, group_id FROM target_track_points
WHERE group_id = '<YOUR_GROUP_ID>';
```

SQLite 使用同樣的事件查詢，DB 路徑在 `.local-runtime/sound_events.db`。在 V2 Dashboard 打開事件查詢，按節點、時間與 label 找出同筆事件。用 GET／SQL 核對完整 ID。保持 `/ws/dashboard` 連線，觀察 `event_trigger`，刷新後確認資料可從 DB 重讀。接著檢查 `/event-groups` 的 node count／region、`/tracks?limit=20&points_limit=100` 的 points，與 Dashboard「位置與軌跡」。單節點事件不足以觸發多節點 track。空 track 請先檢查 label、座標、事件時間、DB schema、`TRACKING_ENABLED` 以及背景處理錯誤。
