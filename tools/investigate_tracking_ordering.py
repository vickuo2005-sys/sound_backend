"""Reproduce tracker ordering loss and compare event-time reorder windows."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.tracking.reorder_buffer import TrackingReorderBuffer


@dataclass
class Observation:
    observation_id: str
    event_time_ms: float


class StrictIncreasingTracker:
    def __init__(self) -> None:
        self.points: list[float] = []
        self.discarded_non_increasing = 0

    def accept(self, observation: Observation) -> None:
        if self.points and observation.event_time_ms <= self.points[-1]:
            self.discarded_non_increasing += 1
            return
        self.points.append(observation.event_time_ms)


SCENARIOS = {
    "in_order": [
        Observation("e1", 1000),
        Observation("e2", 1200),
        Observation("e3", 1400),
    ],
    "mild_out_of_order": [
        Observation("e2", 1200),
        Observation("e1", 1000),
        Observation("e3", 1400),
    ],
    "heavy_out_of_order": [
        Observation("e3", 1400),
        Observation("e2", 1200),
        Observation("e1", 1000),
    ],
    "late_arrival_e2_e3_e1": [
        Observation("e2", 2000),
        Observation("e3", 3000),
        Observation("e1", 1000),
    ],
    "duplicate": [
        Observation("e1", 1000),
        Observation("e1", 1000),
        Observation("e2", 1200),
    ],
    "missing_observation": [
        Observation("e1", 1000),
        Observation("e3", 1400),
    ],
}


def run_without_buffer(observations: list[Observation]) -> dict:
    tracker = StrictIncreasingTracker()
    for observation in observations:
        tracker.accept(observation)
    return {
        "track_point_count": len(tracker.points),
        "tracker_discarded_non_increasing": tracker.discarded_non_increasing,
        "buffer_late_discarded": 0,
        "buffer_duplicate_discarded": 0,
        "emitted_event_times_ms": tracker.points,
    }


def run_with_buffer(observations: list[Observation], window_ms: float) -> dict:
    tracker = StrictIncreasingTracker()
    buffer = TrackingReorderBuffer(window_ms)
    for observation in observations:
        result = buffer.offer(
            "region-a",
            observation_id=observation.observation_id,
            event_time_ms=observation.event_time_ms,
            payload={
                "observation_id": observation.observation_id,
                "event_time_ms": observation.event_time_ms,
            },
        )
        for item in result.ready:
            tracker.accept(
                Observation(item.observation_id, item.event_time_ms)
            )
    for item in buffer.flush_key("region-a"):
        tracker.accept(Observation(item.observation_id, item.event_time_ms))
    metrics = buffer.metrics()
    return {
        "track_point_count": len(tracker.points),
        "tracker_discarded_non_increasing": tracker.discarded_non_increasing,
        "buffer_late_discarded": metrics["late_discarded"],
        "buffer_duplicate_discarded": metrics["duplicate_discarded"],
        "emitted_event_times_ms": tracker.points,
    }


def main() -> None:
    output = {}
    for name, observations in SCENARIOS.items():
        output[name] = {
            "disabled": run_without_buffer(observations),
            "300_ms": run_with_buffer(observations, 300),
            "500_ms": run_with_buffer(observations, 500),
        }
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
