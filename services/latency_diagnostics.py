"""Bounded, in-process staging latency metrics.

All durations use time.monotonic(), never device or server wall-clock deltas.
No event IDs, audio, node positions, or raw request bodies are retained.
Each Uvicorn worker owns its own registry; this is not a distributed metric store.
"""
from __future__ import annotations

from collections import defaultdict, deque
from contextlib import contextmanager
from datetime import datetime, timezone
import math
import os
import threading
from time import monotonic
from typing import Iterator


STAGES = (
    "ingest_total", "event_db", "fixed_location",
    "postgres_pool_wait", "postgres_connection_check", "fusion_db_lock_wait",
    "queue_wait", "fusion", "region_tracking", "active_alert_tracking",
    "localization_group_load", "localization_compute", "tdoa_solver",
    "localization_save", "localization_tracking", "localization_total",
    "post_ingest_total", "ws_event_group", "ws_track_update",
    "ws_localization_result", "broadcast_total", "queued_to_broadcast",
)


def percentile(sorted_values: list[float], quantile: float) -> float | None:
    if not sorted_values:
        return None
    index = (len(sorted_values) - 1) * quantile
    lo, hi = int(math.floor(index)), int(math.ceil(index))
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (index - lo)


class LatencyRegistry:
    def __init__(
        self, *, enabled: bool = False, capacity: int = 512,
        window_seconds: float = 900.0,
    ) -> None:
        self.enabled = bool(enabled)
        self.capacity = max(10, min(int(capacity), 5000))
        self.window_seconds = max(30.0, float(window_seconds))
        self._lock = threading.Lock()
        self._samples: dict[str, deque[tuple[float, float]]] = {
            name: deque(maxlen=self.capacity) for name in STAGES
        }
        self._errors: dict[str, int] = defaultdict(int)
        self._pending = 0
        self._running = 0

    def record(self, stage: str, milliseconds: float) -> None:
        if not self.enabled or stage not in self._samples:
            return
        if not isinstance(milliseconds, (int, float)) or not math.isfinite(milliseconds) or milliseconds < 0:
            return
        now = monotonic()
        with self._lock:
            self._samples[stage].append((now, float(milliseconds)))

    @contextmanager
    def measure(self, stage: str) -> Iterator[None]:
        if not self.enabled:
            yield
            return
        started = monotonic()
        try:
            yield
        finally:
            self.record(stage, (monotonic() - started) * 1000.0)

    def failed(self, stage: str) -> None:
        if not self.enabled or stage not in STAGES:
            return
        with self._lock:
            self._errors[stage] += 1

    def enqueued(self) -> float:
        now = monotonic()
        if self.enabled:
            with self._lock:
                self._pending += 1
        return now

    def started(self, enqueued_at: float) -> None:
        if not self.enabled:
            return
        self.record("queue_wait", max(0.0, (monotonic() - enqueued_at) * 1000.0))
        with self._lock:
            self._pending = max(0, self._pending - 1)
            self._running += 1

    def finished(self) -> None:
        if not self.enabled:
            return
        with self._lock:
            self._running = max(0, self._running - 1)

    def cancelled(self) -> None:
        if not self.enabled:
            return
        with self._lock:
            self._pending = max(0, self._pending - 1)

    def snapshot(self) -> dict:
        now = monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            data = {
                name: [duration for timestamp, duration in samples if timestamp >= cutoff]
                for name, samples in self._samples.items()
            }
            pending, running = self._pending, self._running
            errors = dict(self._errors)
        stages = {}
        for name, values in data.items():
            if not values:
                continue
            values.sort()
            stages[name] = {
                "count": len(values),
                "p50_ms": round(percentile(values, .50), 2),
                "p95_ms": round(percentile(values, .95), 2),
                "p99_ms": round(percentile(values, .99), 2),
                "max_ms": round(values[-1], 2),
            }
        return {
            "enabled": self.enabled,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "window_seconds": self.window_seconds,
            "capacity_per_stage": self.capacity,
            "queue": {"pending": pending, "running": running},
            "stages": stages,
            "errors": errors,
            "notes": [
                "In-memory per server process; restart clears the history.",
                "Stages represent observed durations, not additive end-to-end totals.",
                "Browser receive-to-paint is measured independently with performance.now().",
            ],
        }


registry = LatencyRegistry(
    enabled=os.getenv("LATENCY_DIAGNOSTICS_ENABLED", "false").lower() == "true",
    capacity=int(os.getenv("LATENCY_DIAGNOSTICS_CAPACITY", "512")),
)
