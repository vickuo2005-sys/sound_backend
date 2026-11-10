# 第一個節點與 Dashboard WebSocket

先啟動自己的 Backend，確認 `NODE_WEBSOCKET_ENABLED=true`。以下用合成節點 `node_A01`。用同一個 ID 作 URL path、hello／heartbeat 的 `device_id`、HTTP event 的 `device_id`。Dashboard 會過濾一些含 TEST、SMOKE、DEBUG、CHECK 等字樣的診斷 ID。

```text
本機  ws://127.0.0.1:8786/ws/node/node_A01
部署  wss://<YOUR_BACKEND_HOST>/ws/node/node_A01
```

第一包是 JSON text frame。三個欄位已足夠送出最小 hello。程式會為省略的 message ID、send timestamp 與 payload 提供預設。

```json
{
  "protocol_version": 1,
  "message_type": "hello",
  "device_id": "node_A01"
}
```

Backend 在接受 WebSocket 後等第一包最多 10 秒。成功回 `hello_ack`，payload 包含 `connection_id`、`generation`、`heartbeat_interval_seconds` 與 `server_time_ms`。無效 hello 或 path ID 不符回 `protocol_error` 並關閉 1008。節點 WS 關閉旗標會拒絕連線。Heartbeat 預設建議每 5 秒，10 秒內 `ONLINE`，超過 10 到 20 秒 `DEGRADED`，超過 20 秒或斷開為 `OFFLINE`。`/nodes/live` 只列目前 live rows，已離線節點可能退出該清單。固定節點仍可在 Dashboard 保留。

## 可執行範例

把此區塊另存 `first_node.py`，以本機 venv 執行 `python first_node.py`。部署驗收可加 `--base-url https://<YOUR_BACKEND_HOST>`。保持程式運行，再在另一個終端送 event 或開瀏覽器查節點管理。用 `--device-id node_A02` 另啟第二個節點。

```python
import argparse
import asyncio
import json
from urllib.parse import urlsplit

import websockets

parser = argparse.ArgumentParser()
parser.add_argument("--base-url", default="http://127.0.0.1:8786")
parser.add_argument("--device-id", default="node_A01")
parser.add_argument("--heartbeats", type=int, default=24)
args = parser.parse_args()
base = urlsplit(args.base_url)
scheme = "wss" if base.scheme == "https" else "ws"

def envelope(kind, payload=None):
    return json.dumps({
        "protocol_version": 1,
        "message_type": kind,
        "device_id": args.device_id,
        "payload": payload or {},
    })

async def main():
    async with websockets.connect(f"{scheme}://{base.netloc}/ws/dashboard", open_timeout=10) as dashboard:
        async with websockets.connect(f"{scheme}://{base.netloc}/ws/node/{args.device_id}", open_timeout=10) as node:
            await node.send(envelope("hello", {"app_version": "rebuild", "recording": True, "detection_enabled": True}))
            ack = json.loads(await asyncio.wait_for(node.recv(), 10))
            assert ack["message_type"] == "hello_ack"
            assert ack["device_id"] == args.device_id
            interval = float(ack["payload"]["heartbeat_interval_seconds"])
            print("hello_ack", args.device_id, "interval", interval)
            for _ in range(args.heartbeats):
                await node.send(envelope("heartbeat", {"recording": True, "detection_enabled": True}))
                async with asyncio.timeout(10):
                    while True:
                        message = json.loads(await dashboard.recv())
                        state = message.get("node") or {}
                        if message.get("type") == "node_heartbeat" and state.get("device_id") == args.device_id:
                            assert state["availability_status"] == "ONLINE"
                            print("node_heartbeat ONLINE", args.device_id)
                            break
                await asyncio.sleep(interval)

asyncio.run(main())
```

在 `/nodes/live` 查看同一 ID 及 `availability_status=ONLINE`，在 Dashboard 節點頁比對上線與監聽。可使用 `/device-locations` 設定固定位置，或讓事件攜帶節點座標。`--heartbeats` 控制合成節點的連線時間。關閉 script 後可觀察斷線與固定位置保留。

`/ws/node/{device_id}` 用於 hello／heartbeat、狀態、命令 ACK／result 與串流控制。`event` 不在允許的 message type 清單。正式 event ingest 用 [HTTP /events](FIRST_EVENT_GUIDE.md)。Gateway echo `POST /api/test-gateway` 使用 upload token，驗收 JSON 往返及接收時間。實際 Gateway 需要按 [API Contract](API_CONTRACT.md) 把 vendor 欄位轉成正式 event contract。
