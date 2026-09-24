from __future__ import annotations

import math
import threading
from collections import deque
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class StageSummary:
    count: int
    mean_ms: float
    p50_ms: float
    p95_ms: float
    p99_ms: float
    max_ms: float
    last_ms: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "count": self.count,
            "mean_ms": self.mean_ms,
            "p50_ms": self.p50_ms,
            "p95_ms": self.p95_ms,
            "p99_ms": self.p99_ms,
            "max_ms": self.max_ms,
            "last_ms": self.last_ms,
        }


class LatencyDiagnostics:
    """Small in-process latency sampler for staging/field validation.

    This intentionally avoids database writes and external telemetry so the
    diagnostic path does not create the latency it is trying to measure.
    Samples are process-local and reset on deploy/restart.
    """

    def __init__(self, max_samples_per_stage: int = 256) -> None:
        self.max_samples_per_stage = max(16, int(max_samples_per_stage))
        self._lock = threading.RLock()
        self._samples: dict[str, deque[float]] = {}
        self._pending: dict[str, int] = {}
        self._peak_pending: dict[str, int] = {}

    @staticmethod
    def _percentile(values: list[float], percentile: float) -> float:
        if not values:
            return 0.0
        ordered = sorted(values)
        if len(ordered) == 1:
            return ordered[0]
        rank = (len(ordered) - 1) * max(0.0, min(1.0, percentile))
        low = int(math.floor(rank))
        high = int(math.ceil(rank))
        if low == high:
            return ordered[low]
        weight = rank - low
        return ordered[low] * (1.0 - weight) + ordered[high] * weight

    def record(self, stage: str, duration_ms: float | int | None) -> None:
        try:
            value = float(duration_ms) if duration_ms is not None else None
        except (TypeError, ValueError):
            return
        if value is None or not math.isfinite(value) or value < 0:
            return
        key = str(stage or "").strip()
        if not key:
            return
        with self._lock:
            bucket = self._samples.setdefault(
                key, deque(maxlen=self.max_samples_per_stage)
            )
            bucket.append(value)

    def job_enqueued(self, kind: str) -> None:
        key = str(kind or "unknown")
        with self._lock:
            pending = self._pending.get(key, 0) + 1
            self._pending[key] = pending
            self._peak_pending[key] = max(self._peak_pending.get(key, 0), pending)

    def job_started(self, kind: str, queue_wait_ms: float) -> None:
        key = str(kind or "unknown")
        self.record(f"{key}_queue_wait", queue_wait_ms)
        with self._lock:
            self._pending[key] = max(0, self._pending.get(key, 0) - 1)

    def job_finished(self, kind: str, duration_ms: float | None = None) -> None:
        if duration_ms is not None:
            self.record(f"{str(kind or 'unknown')}_worker", duration_ms)

    def _summary(self, values: list[float]) -> StageSummary:
        return StageSummary(
            count=len(values),
            mean_ms=sum(values) / len(values),
            p50_ms=self._percentile(values, 0.50),
            p95_ms=self._percentile(values, 0.95),
            p99_ms=self._percentile(values, 0.99),
            max_ms=max(values),
            last_ms=values[-1],
        )

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            stages = {
                key: self._summary(list(values)).as_dict()
                for key, values in sorted(self._samples.items())
                if values
            }
            return {
                "sample_window": self.max_samples_per_stage,
                "stages": stages,
                "pending_jobs": dict(self._pending),
                "peak_pending_jobs": dict(self._peak_pending),
                "note": "Process-local rolling samples; reset on deploy/restart.",
            }

    def reset(self) -> None:
        with self._lock:
            self._samples.clear()
            self._pending.clear()
            self._peak_pending.clear()


latency_diagnostics = LatencyDiagnostics()
