"""Summarize one real Android + staging + browser latency scenario.

The App log must contain ``[POST_INFERENCE_LATENCY_JSON]`` records emitted by
real AI completions. Dashboard JSON is an export of
``window.__postInferenceLatencySamples``. This tool never invents AI times.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable


APP_MARKER = "[POST_INFERENCE_LATENCY_JSON]"


def percentile(values: Iterable[float], quantile: float) -> float | None:
    ordered = sorted(values)
    if not ordered:
        return None
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * quantile)))
    return round(ordered[index], 2)


def summarize(values: list[float]) -> dict[str, Any]:
    return {
        "count": len(values),
        "p50_ms": percentile(values, 0.50),
        "p95_ms": percentile(values, 0.95),
        "p99_ms": percentile(values, 0.99),
        "max_ms": round(max(values), 2) if values else None,
    }


def numeric(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if number >= 0 else None


def read_app_samples(path: Path) -> list[dict[str, Any]]:
    samples = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        marker_index = line.find(APP_MARKER)
        if marker_index < 0:
            continue
        raw = line[marker_index + len(APP_MARKER) :].strip()
        try:
            sample = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if sample.get("monotonic_trace_valid") is True:
            samples.append(sample)
    return samples


def read_json_samples(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("samples", "results"):
            if isinstance(payload.get(key), list):
                return [item for item in payload[key] if isinstance(item, dict)]
    raise ValueError(f"Unsupported sample JSON shape: {path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--nodes", type=int, required=True)
    parser.add_argument("--app-log", type=Path, required=True)
    parser.add_argument("--dashboard-json", type=Path, required=True)
    parser.add_argument("--db-probe-json", type=Path)
    parser.add_argument("--minimum-samples", type=int, default=50)
    args = parser.parse_args()

    app_samples = read_app_samples(args.app_log)
    dashboard_samples = read_json_samples(args.dashboard_json)
    dashboard_by_trace = {
        str(sample.get("trace_id") or sample.get("event_id")): sample
        for sample in dashboard_samples
    }
    joined = [
        (sample, dashboard_by_trace[str(sample.get("trace_id") or sample.get("event_id"))])
        for sample in app_samples
        if str(sample.get("trace_id") or sample.get("event_id")) in dashboard_by_trace
    ]

    stages = {
        "app_ai_finish_to_http_start": [
            value
            for sample in app_samples
            if (value := numeric(sample.get("ai_finish_to_http_start_ms"))) is not None
        ],
        "app_http_rtt": [
            value
            for sample in app_samples
            if (value := numeric(sample.get("http_rtt_ms"))) is not None
        ],
        "server_db": [
            value
            for sample in app_samples
            if (value := numeric(sample.get("server_db_ms"))) is not None
        ],
        "server_non_db": [
            value
            for sample in app_samples
            if (value := numeric(sample.get("server_non_db_ms"))) is not None
        ],
        "browser_ws_receive_to_render": [
            value
            for _, sample in joined
            if (value := numeric(sample.get("ws_receive_to_render_ms"))) is not None
        ],
        # This field uses UTC epoch correlation, never cross-device monotonic
        # subtraction. Record clock-sync quality alongside any conclusion.
        "ai_finish_to_final_render_epoch_correlated": [
            value
            for _, sample in joined
            if (
                value := numeric(sample.get("ai_finished_to_dashboard_render_ms"))
            )
            is not None
        ],
    }

    probe_summary = None
    if args.db_probe_json:
        probe_samples = read_json_samples(args.db_probe_json)
        probe_summary = {
            name: summarize(
                [
                    value
                    for sample in probe_samples
                    if (value := numeric(sample.get(field))) is not None
                ]
            )
            for name, field in {
                "render_db_pool_acquire": "db_acquire_ms",
                "render_supabase_select_1_rtt": "db_ping_ms",
                "render_db_probe_total": "db_probe_total_ms",
            }.items()
        }

    counts = {
        "app": len(app_samples),
        "dashboard": len(dashboard_samples),
        "joined": len(joined),
    }
    warnings = []
    if len(app_samples) < args.minimum_samples:
        warnings.append("app sample count below required minimum")
    if len(joined) < args.minimum_samples:
        warnings.append("joined App/Dashboard sample count below required minimum")

    print(
        json.dumps(
            {
                "nodes": args.nodes,
                "counts": counts,
                "stages": {name: summarize(values) for name, values in stages.items()},
                "db_probe": probe_summary,
                "warnings": warnings,
                "clock_note": (
                    "App and browser monotonic clocks are only used for local durations; "
                    "the final epoch-correlated value requires verified device/browser UTC sync."
                ),
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
