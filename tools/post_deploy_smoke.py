import argparse
import asyncio
import json
from urllib.parse import urljoin, urlparse

import httpx
import websockets


READ_ONLY_ENDPOINTS = [
    "/health",
    "/dashboard",
    "/nodes/live",
    "/audio-streams",
    "/time-sync",
    "/event-groups",
    "/localization-results",
    "/tracks",
]


async def check_websocket(base_url: str, device_id: str, timeout: float) -> dict:
    parsed = urlparse(base_url)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    ws_url = f"{scheme}://{parsed.netloc}/ws/node/{device_id}"
    result = {"url": ws_url, "ok": False}
    try:
        async with websockets.connect(ws_url, open_timeout=timeout) as ws:
            await ws.send(
                json.dumps(
                    {
                        "protocol_version": 1,
                        "message_type": "hello",
                        "device_id": device_id,
                        "message_id": "smoke-hello",
                        "sent_at_ms": 1,
                        "payload": {"app_version": "smoke-test"},
                    }
                )
            )
            response = await asyncio.wait_for(ws.recv(), timeout=timeout)
            result["response"] = json.loads(response)
            result["ok"] = result["response"].get("message_type") == "hello_ack"
    except Exception as exc:
        result["error"] = str(exc)
    return result


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--device-id", default="node_SMOKE")
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--allow-websocket", action="store_true")
    parser.add_argument("--allow-audio-test", action="store_true")
    args = parser.parse_args()

    report = {
        "base_url": args.base_url,
        "checks": [],
        "websocket": None,
        "audio_test": "not_run",
    }
    ok = True

    async with httpx.AsyncClient(timeout=args.timeout, follow_redirects=True) as client:
        for endpoint in READ_ONLY_ENDPOINTS:
            url = urljoin(args.base_url.rstrip("/") + "/", endpoint.lstrip("/"))
            item = {"endpoint": endpoint, "url": url}
            try:
                response = await client.get(url)
                item["status_code"] = response.status_code
                item["ok"] = 200 <= response.status_code < 500
                if endpoint == "/health":
                    item["ok"] = response.status_code == 200
                ok = ok and item["ok"]
            except Exception as exc:
                item["ok"] = False
                item["error"] = str(exc)
                ok = False
            report["checks"].append(item)

    if args.allow_websocket:
        report["websocket"] = await check_websocket(
            args.base_url,
            args.device_id,
            args.timeout,
        )
        ok = ok and bool(report["websocket"].get("ok"))

    if args.allow_audio_test:
        report["audio_test"] = "manual_only_not_performed"

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

