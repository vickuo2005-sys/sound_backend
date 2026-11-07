from __future__ import annotations

import heapq
import threading
from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class ReorderItem:
    observation_id: str
    event_time_ms: float
    payload: dict[str, Any]


@dataclass(frozen=True)
class ReorderOfferResult:
    ready: tuple[ReorderItem, ...]
    discarded_reason: Optional[str] = None
    watermark_ms: Optional[float] = None


class TrackingReorderBuffer:
    """Small event-time reorder buffer for the post-ingest tracking path.

    The class intentionally knows nothing about Dashboard alerts or HTTP ingest.
    Callers choose a region/track key and process ``ready`` items in order.
    """

    def __init__(self, window_ms: float) -> None:
        if window_ms < 0:
            raise ValueError("window_ms must be non-negative")
        self.window_ms = float(window_ms)
        self._lock = threading.RLock()
        self._sequence = 0
        self._queues: dict[str, list[tuple[float, int, ReorderItem]]] = {}
        self._latest_seen_ms: dict[str, float] = {}
        self._last_emitted_ms: dict[str, float] = {}
        self._seen_ids: dict[str, set[str]] = {}
        self._metrics = {
            "offered": 0,
            "emitted": 0,
            "late_discarded": 0,
            "duplicate_discarded": 0,
        }

    def offer(
        self,
        key: str,
        *,
        observation_id: str,
        event_time_ms: float,
        payload: dict[str, Any],
    ) -> ReorderOfferResult:
        normalized_key = str(key).strip()
        normalized_id = str(observation_id).strip()
        if not normalized_key:
            raise ValueError("key is required")
        if not normalized_id:
            raise ValueError("observation_id is required")

        timestamp = float(event_time_ms)
        with self._lock:
            self._metrics["offered"] += 1
            seen = self._seen_ids.setdefault(normalized_key, set())
            if normalized_id in seen:
                self._metrics["duplicate_discarded"] += 1
                return ReorderOfferResult(ready=(), discarded_reason="duplicate")
            seen.add(normalized_id)

            last_emitted = self._last_emitted_ms.get(normalized_key)
            if last_emitted is not None and timestamp <= last_emitted:
                self._metrics["late_discarded"] += 1
                return ReorderOfferResult(
                    ready=(),
                    discarded_reason="arrived_behind_emitted_watermark",
                    watermark_ms=last_emitted,
                )

            self._sequence += 1
            item = ReorderItem(
                observation_id=normalized_id,
                event_time_ms=timestamp,
                payload=dict(payload),
            )
            queue = self._queues.setdefault(normalized_key, [])
            heapq.heappush(queue, (timestamp, self._sequence, item))
            latest_seen = max(timestamp, self._latest_seen_ms.get(normalized_key, timestamp))
            self._latest_seen_ms[normalized_key] = latest_seen
            watermark = latest_seen - self.window_ms
            ready = self._pop_through_watermark(normalized_key, watermark)
            return ReorderOfferResult(
                ready=tuple(ready),
                watermark_ms=watermark,
            )

    def flush_key(self, key: str) -> tuple[ReorderItem, ...]:
        """Release the tail in event-time order after the bounded hold expires."""

        normalized_key = str(key).strip()
        with self._lock:
            queue = self._queues.get(normalized_key) or []
            ready: list[ReorderItem] = []
            while queue:
                _, _, item = heapq.heappop(queue)
                last_emitted = self._last_emitted_ms.get(normalized_key)
                if last_emitted is not None and item.event_time_ms <= last_emitted:
                    self._metrics["late_discarded"] += 1
                    continue
                self._last_emitted_ms[normalized_key] = item.event_time_ms
                self._metrics["emitted"] += 1
                ready.append(item)
            self._queues.pop(normalized_key, None)
            return tuple(ready)

    def pending_count(self, key: Optional[str] = None) -> int:
        with self._lock:
            if key is not None:
                return len(self._queues.get(str(key).strip()) or [])
            return sum(len(queue) for queue in self._queues.values())

    def metrics(self) -> dict[str, int | float]:
        with self._lock:
            return {
                **self._metrics,
                "pending": self.pending_count(),
                "window_ms": self.window_ms,
            }

    def reset(self) -> None:
        with self._lock:
            self._sequence = 0
            self._queues.clear()
            self._latest_seen_ms.clear()
            self._last_emitted_ms.clear()
            self._seen_ids.clear()
            for name in self._metrics:
                self._metrics[name] = 0

    def _pop_through_watermark(
        self,
        key: str,
        watermark_ms: float,
    ) -> list[ReorderItem]:
        queue = self._queues.get(key) or []
        ready: list[ReorderItem] = []
        while queue and queue[0][0] <= watermark_ms:
            _, _, item = heapq.heappop(queue)
            last_emitted = self._last_emitted_ms.get(key)
            if last_emitted is not None and item.event_time_ms <= last_emitted:
                self._metrics["late_discarded"] += 1
                continue
            self._last_emitted_ms[key] = item.event_time_ms
            self._metrics["emitted"] += 1
            ready.append(item)
        if not queue:
            self._queues.pop(key, None)
        return ready
