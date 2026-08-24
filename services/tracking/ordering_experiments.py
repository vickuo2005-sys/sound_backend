from __future__ import annotations

import threading
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class SequencedItem:
    observation_id: str
    sequence: int
    event_time_ms: float
    arrival_time_ms: float
    payload: dict[str, Any]


@dataclass(frozen=True)
class SequenceEmission:
    item: SequencedItem
    emitted_at_ms: float

    @property
    def additional_latency_ms(self) -> float:
        return max(0.0, self.emitted_at_ms - self.item.arrival_time_ms)


@dataclass(frozen=True)
class SequenceOfferResult:
    ready: tuple[SequenceEmission, ...]
    discarded_reason: Optional[str] = None
    gaps_skipped: int = 0


class PerKeySequenceExecutor:
    """Sequence-aware gate with isolated state for every independent key.

    It serializes only observations sharing a key. Missing sequences are held
    for ``max_late_ms`` and then skipped by ``flush_expired``; event time remains
    part of each item and is never replaced by the sequence number.
    """

    def __init__(
        self,
        *,
        max_late_ms: float = 2000.0,
        initial_sequence: int = 1,
        max_seen_ids_per_key: int = 10000,
    ) -> None:
        if max_late_ms < 0:
            raise ValueError("max_late_ms must be non-negative")
        if initial_sequence < 0:
            raise ValueError("initial_sequence must be non-negative")
        self.max_late_ms = float(max_late_ms)
        self.initial_sequence = int(initial_sequence)
        self.max_seen_ids_per_key = max(1, int(max_seen_ids_per_key))
        self._lock = threading.RLock()
        self._next_sequence: dict[str, int] = {}
        self._pending: dict[str, dict[int, SequencedItem]] = {}
        self._seen_ids: dict[str, OrderedDict[str, None]] = {}
        self._metrics = {
            "offered": 0,
            "emitted": 0,
            "duplicate_discarded": 0,
            "late_discarded": 0,
            "gaps_skipped": 0,
            "max_pending": 0,
        }

    def offer(
        self,
        key: str,
        *,
        observation_id: str,
        sequence: int,
        event_time_ms: float,
        arrival_time_ms: float,
        payload: dict[str, Any],
    ) -> SequenceOfferResult:
        normalized_key = self._normalize_key(key)
        normalized_id = str(observation_id).strip()
        if not normalized_id:
            raise ValueError("observation_id is required")
        numeric_sequence = int(sequence)
        with self._lock:
            self._metrics["offered"] += 1
            seen_ids = self._seen_ids.setdefault(normalized_key, OrderedDict())
            if normalized_id in seen_ids:
                seen_ids.move_to_end(normalized_id)
                self._metrics["duplicate_discarded"] += 1
                return SequenceOfferResult(ready=(), discarded_reason="duplicate_id")
            seen_ids[normalized_id] = None
            while len(seen_ids) > self.max_seen_ids_per_key:
                seen_ids.popitem(last=False)

            next_sequence = self._next_sequence.setdefault(
                normalized_key,
                self.initial_sequence,
            )
            pending = self._pending.setdefault(normalized_key, {})
            if numeric_sequence < next_sequence:
                self._metrics["late_discarded"] += 1
                return SequenceOfferResult(
                    ready=(),
                    discarded_reason="sequence_behind_emitted",
                )
            if numeric_sequence in pending:
                self._metrics["duplicate_discarded"] += 1
                return SequenceOfferResult(
                    ready=(),
                    discarded_reason="duplicate_sequence",
                )

            pending[numeric_sequence] = SequencedItem(
                observation_id=normalized_id,
                sequence=numeric_sequence,
                event_time_ms=float(event_time_ms),
                arrival_time_ms=float(arrival_time_ms),
                payload=dict(payload),
            )
            self._metrics["max_pending"] = max(
                self._metrics["max_pending"],
                self.pending_count(),
            )
            ready = self._emit_contiguous(normalized_key, float(arrival_time_ms))
            return SequenceOfferResult(ready=tuple(ready))

    def flush_expired(self, key: str, *, now_ms: float) -> SequenceOfferResult:
        normalized_key = self._normalize_key(key)
        with self._lock:
            pending = self._pending.get(normalized_key) or {}
            if not pending:
                return SequenceOfferResult(ready=())
            oldest_arrival = min(item.arrival_time_ms for item in pending.values())
            if float(now_ms) - oldest_arrival < self.max_late_ms:
                return SequenceOfferResult(ready=())

            next_sequence = self._next_sequence.setdefault(
                normalized_key,
                self.initial_sequence,
            )
            minimum_pending = min(pending)
            gaps_skipped = max(0, minimum_pending - next_sequence)
            if gaps_skipped:
                self._metrics["gaps_skipped"] += gaps_skipped
                self._next_sequence[normalized_key] = minimum_pending
            ready = self._emit_contiguous(normalized_key, float(now_ms))
            return SequenceOfferResult(
                ready=tuple(ready),
                gaps_skipped=gaps_skipped,
            )

    def pending_count(self, key: Optional[str] = None) -> int:
        with self._lock:
            if key is not None:
                return len(self._pending.get(self._normalize_key(key)) or {})
            return sum(len(items) for items in self._pending.values())

    def metrics(self) -> dict[str, int | float]:
        with self._lock:
            return {
                **self._metrics,
                "pending": self.pending_count(),
                "max_late_ms": self.max_late_ms,
            }

    def reset(self) -> None:
        with self._lock:
            self._next_sequence.clear()
            self._pending.clear()
            self._seen_ids.clear()
            for name in self._metrics:
                self._metrics[name] = 0

    def _emit_contiguous(self, key: str, emitted_at_ms: float) -> list[SequenceEmission]:
        pending = self._pending.get(key) or {}
        next_sequence = self._next_sequence.setdefault(key, self.initial_sequence)
        ready: list[SequenceEmission] = []
        while next_sequence in pending:
            item = pending.pop(next_sequence)
            ready.append(SequenceEmission(item=item, emitted_at_ms=emitted_at_ms))
            next_sequence += 1
            self._metrics["emitted"] += 1
        self._next_sequence[key] = next_sequence
        if not pending:
            self._pending.pop(key, None)
        return ready

    @staticmethod
    def _normalize_key(key: str) -> str:
        normalized = str(key).strip()
        if not normalized:
            raise ValueError("key is required")
        return normalized
