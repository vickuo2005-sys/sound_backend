from __future__ import annotations

import json
import statistics
from dataclasses import dataclass
from typing import Any, Iterable, Optional

from services.tracking.ordering_experiments import (
    PerKeySequenceExecutor,
    SequenceEmission,
)
from services.tracking.reorder_buffer import TrackingReorderBuffer


MISSING_TIMEOUT_MS = 500.0
REORDER_CONTROL_MS = 2000.0


@dataclass(frozen=True)
class Measurement:
    observation_id: str
    stream_key: str
    track_key: str
    sequence: int
    event_time_ms: float
    completion_ms: float


def _case(
    sequences: Iterable[int],
    *,
    spacing_ms: float,
    track_key: str = "track-a",
    stream_key: str = "A01:session-1",
) -> list[Measurement]:
    return [
        Measurement(
            observation_id=f"{stream_key}-{sequence}",
            stream_key=stream_key,
            track_key=track_key,
            sequence=sequence,
            event_time_ms=(sequence - 1) * spacing_ms,
            completion_ms=index * 100.0,
        )
        for index, sequence in enumerate(sequences)
    ]


def benchmark_cases() -> dict[str, list[Measurement]]:
    duplicate = _case([1, 2], spacing_ms=1500.0)
    duplicate.append(
        Measurement(
            observation_id=duplicate[-1].observation_id,
            stream_key=duplicate[-1].stream_key,
            track_key=duplicate[-1].track_key,
            sequence=2,
            event_time_ms=1500.0,
            completion_ms=200.0,
        )
    )
    two_tracks = [
        Measurement("a-2", "A01:s1", "track-a", 2, 1500.0, 0.0),
        Measurement("b-1", "B01:s1", "track-b", 1, 0.0, 50.0),
        Measurement("a-1", "A01:s1", "track-a", 1, 0.0, 100.0),
        Measurement("b-2", "B01:s1", "track-b", 2, 1500.0, 150.0),
    ]
    return {
        "case_1_E2_E3_E1_one_second": _case([2, 3, 1], spacing_ms=1000.0),
        "case_2_exact_hop_E2_E3_E1": _case([2, 3, 1], spacing_ms=1500.0),
        "case_3_mild_jitter": _case([1, 3, 2, 4], spacing_ms=1500.0),
        "case_4_heavy_jitter": _case([4, 3, 2, 1], spacing_ms=1500.0),
        "case_5_missing_sequence": _case([1, 3], spacing_ms=1500.0),
        "case_6_duplicate": duplicate,
        "case_7_two_independent_tracks": two_tracks,
    }


class StrictTracker:
    def __init__(self) -> None:
        self.latest: dict[str, float] = {}
        self.seen_ids: set[str] = set()
        self.recovered = 0
        self.late = 0
        self.duplicate = 0

    def apply(self, measurement: Measurement) -> None:
        if measurement.observation_id in self.seen_ids:
            self.duplicate += 1
            return
        self.seen_ids.add(measurement.observation_id)
        latest = self.latest.get(measurement.track_key)
        if latest is not None and measurement.event_time_ms <= latest:
            self.late += 1
            return
        self.latest[measurement.track_key] = measurement.event_time_ms
        self.recovered += 1


def current_parallel(measurements: list[Measurement]) -> dict[str, Any]:
    tracker = StrictTracker()
    for measurement in measurements:
        tracker.apply(measurement)
    return _result(
        tracker,
        latencies=[0.0] * (tracker.recovered + tracker.late),
        max_pending=0,
        key_count=len({item.track_key for item in measurements}),
        complexity="low, but completion order can corrupt measurement order",
    )


def sequence_and_mailbox(measurements: list[Measurement]) -> dict[str, Any]:
    gate = PerKeySequenceExecutor(max_late_ms=MISSING_TIMEOUT_MS)
    emissions: list[SequenceEmission] = []
    max_pending = 0
    for measurement in measurements:
        result = gate.offer(
            measurement.stream_key,
            observation_id=measurement.observation_id,
            sequence=measurement.sequence,
            event_time_ms=measurement.event_time_ms,
            arrival_time_ms=measurement.completion_ms,
            payload={"measurement": measurement},
        )
        emissions.extend(result.ready)
        max_pending = max(max_pending, gate.pending_count())
    final_now = max((item.completion_ms for item in measurements), default=0.0)
    final_now += MISSING_TIMEOUT_MS
    for stream_key in sorted({item.stream_key for item in measurements}):
        emissions.extend(gate.flush_expired(stream_key, now_ms=final_now).ready)

    tracker = StrictTracker()
    for emission in emissions:
        tracker.apply(emission.item.payload["measurement"])
    metrics = gate.metrics()
    tracker.duplicate += int(metrics["duplicate_discarded"])
    tracker.late += int(metrics["late_discarded"])
    return _result(
        tracker,
        latencies=[item.additional_latency_ms for item in emissions],
        max_pending=max_pending,
        key_count=len({item.track_key for item in measurements}),
        complexity=(
            "medium: per-session expected sequence, bounded missing timer, "
            "per-track serialized mailbox"
        ),
    )


def event_time_2000_control(measurements: list[Measurement]) -> dict[str, Any]:
    buffer = TrackingReorderBuffer(REORDER_CONTROL_MS)
    ready: list[tuple[Measurement, float]] = []
    max_pending = 0
    for measurement in measurements:
        result = buffer.offer(
            measurement.track_key,
            observation_id=measurement.observation_id,
            event_time_ms=measurement.event_time_ms,
            payload={"measurement": measurement},
        )
        ready.extend(
            (item.payload["measurement"], measurement.completion_ms)
            for item in result.ready
        )
        max_pending = max(max_pending, buffer.pending_count())
    final_release_ms = max(
        (item.completion_ms for item in measurements),
        default=0.0,
    ) + REORDER_CONTROL_MS
    for track_key in sorted({item.track_key for item in measurements}):
        ready.extend(
            (item.payload["measurement"], final_release_ms)
            for item in buffer.flush_key(track_key)
        )

    ready.sort(key=lambda item: (item[1], item[0].event_time_ms))
    tracker = StrictTracker()
    latencies = []
    for measurement, released_at_ms in ready:
        tracker.apply(measurement)
        latencies.append(max(0.0, released_at_ms - measurement.completion_ms))
    buffer_metrics = buffer.metrics()
    tracker.duplicate += int(buffer_metrics["duplicate_discarded"])
    tracker.late += int(buffer_metrics["late_discarded"])
    return _result(
        tracker,
        latencies=latencies,
        max_pending=max_pending,
        key_count=len({item.track_key for item in measurements}),
        complexity="medium-low: per-track heap, watermark, and 2000 ms tail timer",
    )


def _result(
    tracker: StrictTracker,
    *,
    latencies: list[float],
    max_pending: int,
    key_count: int,
    complexity: str,
) -> dict[str, Any]:
    return {
        "recovered_measurements": tracker.recovered,
        "late_discard": tracker.late,
        "duplicate_discard": tracker.duplicate,
        "added_latency_p50_ms": _percentile(latencies, 0.50),
        "added_latency_p95_ms": _percentile(latencies, 0.95),
        "added_latency_p99_ms": _percentile(latencies, 0.99),
        "added_latency_max_ms": max(latencies) if latencies else 0.0,
        "max_pending": max_pending,
        "estimated_state_bytes": max_pending * 512 + key_count * 256,
        "memory_basis": "deterministic state estimate; field RSS required",
        "complexity": complexity,
    }


def run_benchmark() -> dict[str, Any]:
    return {
        case_name: {
            "A_current_parallel": current_parallel(measurements),
            "B_sequence_gate_serialized_mailbox": sequence_and_mailbox(measurements),
            "C_event_time_reorder_2000_ms": event_time_2000_control(measurements),
        }
        for case_name, measurements in benchmark_cases().items()
    }


def _percentile(values: list[float], quantile: float) -> Optional[float]:
    if not values:
        return None
    if quantile == 0.50:
        return round(float(statistics.median(values)), 3)
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * quantile)))
    return round(float(ordered[index]), 3)


def main() -> None:
    print(
        json.dumps(
            {
                "evidence_kind": "local_deterministic_not_field",
                "smoothing": False,
                "missing_sequence_timeout_ms": MISSING_TIMEOUT_MS,
                "reorder_control_ms": REORDER_CONTROL_MS,
                "cases": run_benchmark(),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
