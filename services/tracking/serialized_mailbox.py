from __future__ import annotations

import statistics
import threading
from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from time import monotonic
from typing import Any, Callable, Optional


class MailboxCapacityError(RuntimeError):
    pass


@dataclass
class _MailboxWork:
    enqueued_at_ms: float
    callback: Callable[..., Any]
    args: tuple[Any, ...]
    kwargs: dict[str, Any]
    future: Future[Any]


class PerKeySerializedMailbox:
    """Serialize work within a key while allowing different keys to run in parallel."""

    def __init__(
        self,
        *,
        max_workers: int = 4,
        max_pending_per_key: int = 1024,
        max_keys: int = 2048,
        key_ttl_ms: float = 3_600_000.0,
        max_metric_samples: int = 10_000,
        clock_ms: Optional[Callable[[], float]] = None,
    ) -> None:
        self.max_workers = max(1, int(max_workers))
        self.max_pending_per_key = max(1, int(max_pending_per_key))
        self.max_keys = max(1, int(max_keys))
        self.key_ttl_ms = max(1.0, float(key_ttl_ms))
        self.max_metric_samples = max(1, int(max_metric_samples))
        self._clock_ms = clock_ms or (lambda: monotonic() * 1000.0)
        self._executor = ThreadPoolExecutor(
            max_workers=self.max_workers,
            thread_name_prefix="track-mailbox",
        )
        self._lock = threading.RLock()
        self._idle = threading.Condition(self._lock)
        self._queues: dict[str, deque[_MailboxWork]] = {}
        self._running: set[str] = set()
        self._processing: set[str] = set()
        self._last_activity_ms: dict[str, float] = {}
        self._wait_samples_ms: deque[float] = deque(maxlen=self.max_metric_samples)
        self._processing_samples_ms: deque[float] = deque(
            maxlen=self.max_metric_samples
        )
        self._closed = False
        self._metrics = {
            "submitted_count": 0,
            "completed_count": 0,
            "failed_count": 0,
            "timeout_drop_count": 0,
            "capacity_drop_count": 0,
            "current_pending": 0,
            "max_pending": 0,
            "max_mailbox_depth": 0,
            "cleanup_count": 0,
            "expired_key_count": 0,
            "max_keys_seen": 0,
        }

    def submit(
        self,
        key: str,
        callback: Callable[..., Any],
        /,
        *args: Any,
        **kwargs: Any,
    ) -> Future[Any]:
        normalized_key = self._normalize_key(key)
        future: Future[Any] = Future()
        with self._lock:
            if self._closed:
                future.set_exception(RuntimeError("mailbox is closed"))
                return future
            now_ms = self._clock_ms()
            self._cleanup_expired_locked(now_ms)
            if not self._ensure_key_capacity_locked(normalized_key):
                self._metrics["capacity_drop_count"] += 1
                future.set_exception(MailboxCapacityError("mailbox key capacity reached"))
                return future
            queue = self._queues.setdefault(normalized_key, deque())
            depth = len(queue) + (1 if normalized_key in self._processing else 0)
            if depth >= self.max_pending_per_key:
                self._metrics["capacity_drop_count"] += 1
                future.set_exception(MailboxCapacityError("mailbox depth reached"))
                return future
            queue.append(
                _MailboxWork(
                    enqueued_at_ms=now_ms,
                    callback=callback,
                    args=args,
                    kwargs=dict(kwargs),
                    future=future,
                )
            )
            self._last_activity_ms[normalized_key] = now_ms
            self._metrics["submitted_count"] += 1
            self._metrics["current_pending"] += 1
            self._metrics["max_pending"] = max(
                self._metrics["max_pending"],
                self._metrics["current_pending"],
            )
            self._metrics["max_mailbox_depth"] = max(
                self._metrics["max_mailbox_depth"],
                depth + 1,
            )
            self._metrics["max_keys_seen"] = max(
                self._metrics["max_keys_seen"],
                len(self._last_activity_ms),
            )
            if normalized_key not in self._running:
                self._running.add(normalized_key)
                self._executor.submit(self._drain, normalized_key)
        return future

    def wait_for_idle(self, timeout_seconds: float = 5.0) -> bool:
        deadline_ms = monotonic() * 1000.0 + max(0.0, timeout_seconds) * 1000.0
        with self._idle:
            while self._metrics["current_pending"]:
                remaining_seconds = (deadline_ms - monotonic() * 1000.0) / 1000.0
                if remaining_seconds <= 0:
                    return False
                self._idle.wait(timeout=remaining_seconds)
            return True

    def cleanup_expired(self, *, now_ms: Optional[float] = None) -> int:
        with self._lock:
            return self._cleanup_expired_locked(
                self._clock_ms() if now_ms is None else float(now_ms)
            )

    def metrics(self) -> dict[str, Any]:
        with self._lock:
            waits = list(self._wait_samples_ms)
            processing = list(self._processing_samples_ms)
            return {
                **self._metrics,
                "mailbox_depth": sum(len(queue) for queue in self._queues.values()),
                "current_keys": len(self._last_activity_ms),
                "running_keys": len(self._running),
                "processing_keys": len(self._processing),
                "mailbox_wait_p50_ms": _percentile(waits, 0.50),
                "mailbox_wait_p95_ms": _percentile(waits, 0.95),
                "mailbox_wait_p99_ms": _percentile(waits, 0.99),
                "mailbox_wait_max_ms": max(waits) if waits else None,
                "processing_p50_ms": _percentile(processing, 0.50),
                "processing_p95_ms": _percentile(processing, 0.95),
                "processing_p99_ms": _percentile(processing, 0.99),
                "processing_max_ms": max(processing) if processing else None,
                "max_pending_per_key": self.max_pending_per_key,
                "max_keys": self.max_keys,
                "key_ttl_ms": self.key_ttl_ms,
            }

    def reset(self) -> None:
        if not self.wait_for_idle():
            raise RuntimeError("cannot reset a busy mailbox")
        with self._lock:
            self._queues.clear()
            self._running.clear()
            self._processing.clear()
            self._last_activity_ms.clear()
            self._wait_samples_ms.clear()
            self._processing_samples_ms.clear()
            for name in self._metrics:
                self._metrics[name] = 0

    def close(self) -> None:
        with self._lock:
            self._closed = True
        self.wait_for_idle()
        self._executor.shutdown(wait=True, cancel_futures=False)

    def _drain(self, key: str) -> None:
        while True:
            with self._lock:
                queue = self._queues.get(key)
                if not queue:
                    self._queues.pop(key, None)
                    self._running.discard(key)
                    self._last_activity_ms[key] = self._clock_ms()
                    self._idle.notify_all()
                    return
                work = queue.popleft()
                self._processing.add(key)
                started_at_ms = self._clock_ms()
                self._wait_samples_ms.append(
                    max(0.0, started_at_ms - work.enqueued_at_ms)
                )
            try:
                result = work.callback(*work.args, **work.kwargs)
            except BaseException as exc:
                work.future.set_exception(exc)
                failed = True
            else:
                work.future.set_result(result)
                failed = False
            completed_at_ms = self._clock_ms()
            with self._lock:
                self._processing.discard(key)
                self._processing_samples_ms.append(
                    max(0.0, completed_at_ms - started_at_ms)
                )
                self._last_activity_ms[key] = completed_at_ms
                self._metrics["current_pending"] -= 1
                if failed:
                    self._metrics["failed_count"] += 1
                else:
                    self._metrics["completed_count"] += 1
                self._idle.notify_all()

    def _cleanup_expired_locked(self, now_ms: float) -> int:
        expired = [
            key
            for key, last_activity in self._last_activity_ms.items()
            if key not in self._running
            and not self._queues.get(key)
            and now_ms - last_activity >= self.key_ttl_ms
        ]
        if not expired:
            return 0
        for key in expired:
            self._queues.pop(key, None)
            self._last_activity_ms.pop(key, None)
        self._metrics["cleanup_count"] += 1
        self._metrics["expired_key_count"] += len(expired)
        return len(expired)

    def _ensure_key_capacity_locked(self, key: str) -> bool:
        if key in self._last_activity_ms:
            return True
        idle_keys = [
            existing
            for existing in self._last_activity_ms
            if existing not in self._running and not self._queues.get(existing)
        ]
        while len(self._last_activity_ms) >= self.max_keys and idle_keys:
            oldest = min(idle_keys, key=self._last_activity_ms.__getitem__)
            self._last_activity_ms.pop(oldest, None)
            self._queues.pop(oldest, None)
            idle_keys.remove(oldest)
            self._metrics["cleanup_count"] += 1
            self._metrics["expired_key_count"] += 1
        return len(self._last_activity_ms) < self.max_keys

    @staticmethod
    def _normalize_key(key: str) -> str:
        normalized = str(key).strip()
        if not normalized:
            raise ValueError("key is required")
        return normalized


def _percentile(values: list[float], quantile: float) -> Optional[float]:
    if not values:
        return None
    if quantile == 0.50:
        return round(float(statistics.median(values)), 3)
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * quantile)))
    return round(float(ordered[index]), 3)
