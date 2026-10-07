#!/usr/bin/env python3
"""Summarize APP latency diagnostics from Flutter/adb log text.

Usage:
    python tools/analyze_latency_logs.py path/to/logcat.txt

The APP prints lines like:
    [LATENCY] window_hop_ms=500; native_queue_delay_ms=...

This helper gives a quick average/p95 view so we can tell whether delay is
mostly native recording, Flutter/AI processing, metadata upload, or audio upload.
"""

from __future__ import annotations

import re
import statistics
import sys
from pathlib import Path


LATENCY_RE = re.compile(r"\[LATENCY\]\s+(?P<body>.*)")
VALUE_RE = re.compile(r"(?P<key>[a-zA-Z0-9_]+)=(-?\d+(?:\.\d+)?)")
IGNORED_NUMERIC_KEYS = {"status"}


def percentile(values: list[float], percent: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    ordered = sorted(values)
    index = (len(ordered) - 1) * percent
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    weight = index - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def parse(path: Path) -> dict[str, list[float]]:
    metrics: dict[str, list[float]] = {}
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        match = LATENCY_RE.search(line)
        if not match:
            continue
        for value_match in VALUE_RE.finditer(match.group("body")):
            key = value_match.group("key")
            if key in IGNORED_NUMERIC_KEYS:
                continue
            value = float(value_match.group(0).split("=", 1)[1])
            metrics.setdefault(key, []).append(value)
    return metrics


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python tools/analyze_latency_logs.py path/to/logcat.txt")
        return 2

    path = Path(sys.argv[1])
    if not path.exists():
        print(f"Log file not found: {path}")
        return 2

    metrics = parse(path)
    if not metrics:
        print("No [LATENCY] metrics found.")
        return 1

    print("Latency summary")
    print("metric,count,avg_ms,p95_ms,max_ms")
    for key in sorted(metrics):
        values = metrics[key]
        print(
            f"{key},{len(values)},"
            f"{statistics.fmean(values):.1f},"
            f"{percentile(values, 0.95):.1f},"
            f"{max(values):.1f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
