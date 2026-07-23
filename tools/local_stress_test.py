import asyncio
import json
import sys
import time
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import main


ARTIFACTS = Path("artifacts/test_results")


async def run() -> dict:
    start = time.perf_counter()
    client = TestClient(main.app)
    report = {
        "node_count": 10,
        "command_count": 10,
        "live_audio_enabled": bool(main.LIVE_AUDIO_ENABLED),
        "checks": [],
    }

    for index in range(report["node_count"]):
        device_id = f"node_STRESS_{index:02d}"
        response = client.post(
            "/location-update",
            json={
                "device_id": device_id,
                "latitude": 25.033 + index * 0.0001,
                "longitude": 121.565 + index * 0.0001,
                "is_listening": True,
                "upload_mode": "detection",
            },
        )
        report["checks"].append(
            {
                "type": "location_update",
                "device_id": device_id,
                "status_code": response.status_code,
            }
        )

    for index in range(report["command_count"]):
        device_id = f"node_STRESS_{index:02d}"
        response = client.post(
            "/device-command",
            json={
                "device_id": device_id,
                "command": "request_status",
                "value": None,
                "issued_by": "local_stress_test",
            },
        )
        report["checks"].append(
            {
                "type": "device_command",
                "device_id": device_id,
                "status_code": response.status_code,
            }
        )

    response = client.get("/device-status")
    report["device_status_code"] = response.status_code
    report["duration_seconds"] = round(time.perf_counter() - start, 3)
    report["ok"] = all(item["status_code"] < 500 for item in report["checks"])
    return report


def main_cli() -> int:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    report = asyncio.run(run())
    json_path = ARTIFACTS / "local_stress_test.json"
    txt_path = ARTIFACTS / "local_stress_test.txt"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    txt_path.write_text(
        "\n".join(
            [
                f"ok: {report['ok']}",
                f"node_count: {report['node_count']}",
                f"command_count: {report['command_count']}",
                f"duration_seconds: {report['duration_seconds']}",
                f"device_status_code: {report['device_status_code']}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {json_path}")
    print(f"Wrote {txt_path}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main_cli())
