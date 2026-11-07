"""Benchmark /events ingest latency against localhost only.

Example:
    python tools/benchmark_post_inference_latency.py \
        --base-url http://127.0.0.1:8000 --upload-token local-token

The browser-side render metrics are exposed separately as
window.__postInferenceLatencyStats in the Dashboard.
"""

from __future__ import annotations

import argparse
import json
import math
import time
import uuid
from datetime import datetime, timezone
from typing import Iterable
from urllib.parse import urlparse

import httpx


def percentile(values: Iterable[float], quantile: float) -> float | None:
    ordered = sorted(values)
    if not ordered:
        return None
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * quantile)))
    return round(ordered[index], 2)


def summarize(values: list[float]) -> dict:
    return {
        "count": len(values),
        "p50_ms": percentile(values, 0.50),
        "p95_ms": percentile(values, 0.95),
        "p99_ms": percentile(values, 0.99),
        "max_ms": round(max(values), 2) if values else None,
    }


def parse_server_timing(value: str) -> dict[str, float]:
    output: dict[str, float] = {}
    for item in value.split(","):
        parts = [part.strip() for part in item.split(";") if part.strip()]
        if not parts:
            continue
        duration = next((part[4:] for part in parts[1:] if part.startswith("dur=")), None)
        if duration is None:
            continue
        try:
            numeric = float(duration)
        except ValueError:
            continue
        if math.isfinite(numeric):
            output[parts[0]] = numeric
    return output


def run_scenario(
    client: httpx.Client,
    *,
    base_url: str,
    upload_token: str,
    node_count: int,
    event_count: int,
    device_prefix: str,
) -> dict:
    request_ms: list[float] = []
    server_metrics: dict[str, list[float]] = {
        "db": [],
        "fixed_location": [],
        "ingest": [],
    }
    for index in range(event_count):
        event_id = f"benchmark-{node_count}-{uuid.uuid4()}"
        device_id = f"{device_prefix}{(index % node_count) + 1:02d}"
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        payload = {
            "event_id": event_id,
            "trace_id": event_id,
            "latency_trace": {
                "trace_id": event_id,
                "ai_finished_at": now_ms,
                "http_request_started_at": now_ms,
            },
            "device_id": device_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "label": "aircraft",
            "latitude": 25.04,
            "longitude": 121.53,
            "device_event_time_ms": now_ms,
        }
        started = time.perf_counter()
        response = client.post(
            f"{base_url.rstrip('/')}/events",
            headers={"x-upload-token": upload_token},
            json=payload,
        )
        request_ms.append((time.perf_counter() - started) * 1000.0)
        response.raise_for_status()
        for name, duration in parse_server_timing(
            response.headers.get("server-timing", "")
        ).items():
            if name in server_metrics:
                server_metrics[name].append(duration)

    return {
        "nodes": node_count,
        "events": event_count,
        "metadata_http": summarize(request_ms),
        "backend_db": summarize(server_metrics["db"]),
        "backend_fixed_location": summarize(server_metrics["fixed_location"]),
        "backend_ingest": summarize(server_metrics["ingest"]),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--upload-token", required=True)
    parser.add_argument("--events", type=int, default=50)
    parser.add_argument("--nodes", default="1,2,4")
    parser.add_argument("--device-prefix", default="benchmark_node_")
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args()

    hostname = (urlparse(args.base_url).hostname or "").lower()
    if hostname not in {"localhost", "127.0.0.1", "0.0.0.0"}:
        raise SystemExit(
            "This synthetic timestamp benchmark is localhost-only. "
            "Use the real Android staging runbook for remote services."
        )

    node_counts = [int(value) for value in args.nodes.split(",") if value.strip()]
    with httpx.Client(timeout=args.timeout) as client:
        scenarios = [
            run_scenario(
                client,
                base_url=args.base_url,
                upload_token=args.upload_token,
                node_count=node_count,
                event_count=max(1, args.events),
                device_prefix=args.device_prefix,
            )
            for node_count in node_counts
        ]
    print(json.dumps({"scenarios": scenarios}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
