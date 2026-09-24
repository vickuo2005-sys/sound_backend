from __future__ import annotations

import math
import threading
from collections import deque
from typing import Any


class PipelineLatencyDiagnostics:
    """In-memory, low-overhead latency diagnostics for the live event pipeline."""

    def __init__(self, max_samples: int = 200) -> None:
        self._lock = threading.Lock()
        self._samples: deque[dict[str, Any]] = deque(maxlen=max(10, int(max_samples)))
        self._broadcast_samples: deque[dict[str, Any]] = deque(maxlen=max(20, int(max_samples)))
        self._queued_at: dict[str, float] = {}
        self._active = 0

    def mark_enqueued(self, event_id: str, monotonic_value: float) -> None:
        with self._lock:
            self._queued_at[str(event_id)] = float(monotonic_value)

    def mark_started(self, event_id: str, monotonic_value: float) -> float | None:
        key = str(event_id)
        now = float(monotonic_value)
        with self._lock:
            queued_at = self._queued_at.pop(key, None)
            self._active += 1
        if queued_at is None:
            return None
        return max(0.0, (now - queued_at) * 1000.0)

    def finish(self, event_id: str, sample: dict[str, Any]) -> None:
        normalized = self._normalize_sample({"event_id": str(event_id), **sample})
        with self._lock:
            self._active = max(0, self._active - 1)
            self._samples.append(normalized)

    def fail(self, event_id: str, sample: dict[str, Any] | None = None) -> None:
        payload = {"event_id": str(event_id), "failed": True, **(sample or {})}
        normalized = self._normalize_sample(payload)
        with self._lock:
            self._queued_at.pop(str(event_id), None)
            self._active = max(0, self._active - 1)
            self._samples.append(normalized)

    def record_broadcast(self, context: str, duration_ms: float, connections: int) -> None:
        with self._lock:
            self._broadcast_samples.append(
                {
                    "context": str(context),
                    "duration_ms": max(0.0, float(duration_ms)),
                    "connections": max(0, int(connections)),
                }
            )

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            samples = list(self._samples)
            broadcasts = list(self._broadcast_samples)
            pending = len(self._queued_at)
            active = self._active

        stage_keys = sorted(
            {
                key
                for sample in samples
                for key, value in sample.items()
                if key.endswith("_ms") and self._number(value) is not None
            }
        )
        stages = {
            key: self._summary(
                [float(sample[key]) for sample in samples if self._number(sample.get(key)) is not None]
            )
            for key in stage_keys
        }
        broadcast_values = [float(row["duration_ms"]) for row in broadcasts]
        by_context: dict[str, list[float]] = {}
        for row in broadcasts:
            by_context.setdefault(str(row["context"]), []).append(float(row["duration_ms"]))

        return {
            "sample_count": len(samples),
            "pending_post_ingest": pending,
            "active_post_ingest": active,
            "latest": samples[-1] if samples else None,
            "stages": stages,
            "broadcast": {
                "all": self._summary(broadcast_values),
                "by_context": {key: self._summary(values) for key, values in sorted(by_context.items())},
                "sample_count": len(broadcasts),
            },
        }

    @staticmethod
    def _number(value: Any) -> float | None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        number = float(value)
        return number if math.isfinite(number) and number >= 0 else None

    @classmethod
    def _normalize_sample(cls, sample: dict[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in sample.items():
            if key.endswith("_ms"):
                number = cls._number(value)
                if number is not None:
                    result[key] = round(number, 3)
            elif key in {"event_id", "group_id", "label", "localization_method"}:
                result[key] = value
            elif key in {"failed", "localization_created", "track_created"}:
                result[key] = bool(value)
        return result

    @classmethod
    def _summary(cls, values: list[float]) -> dict[str, Any]:
        valid = sorted(float(value) for value in values if cls._number(value) is not None)
        if not valid:
            return {"count": 0, "p50_ms": None, "p95_ms": None, "p99_ms": None, "max_ms": None}
        return {
            "count": len(valid),
            "p50_ms": round(cls._percentile(valid, 0.50), 3),
            "p95_ms": round(cls._percentile(valid, 0.95), 3),
            "p99_ms": round(cls._percentile(valid, 0.99), 3),
            "max_ms": round(valid[-1], 3),
        }

    @staticmethod
    def _percentile(sorted_values: list[float], quantile: float) -> float:
        if len(sorted_values) == 1:
            return sorted_values[0]
        position = (len(sorted_values) - 1) * quantile
        lower = int(math.floor(position))
        upper = int(math.ceil(position))
        if lower == upper:
            return sorted_values[lower]
        weight = position - lower
        return sorted_values[lower] * (1.0 - weight) + sorted_values[upper] * weight
