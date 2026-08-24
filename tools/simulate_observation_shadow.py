"""Deterministic V2.3 control-vs-observation-shadow simulator.

No smoothing, interpolation, production database, Dashboard, or message broker
is involved. Event time remains the tracking measurement time.
"""

from __future__ import annotations

import json
import statistics
import sys
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.observation_shadow import (  # noqa: E402
    ObservationShadowRegistry,
    ShadowObservation,
    ShadowTrackingPipeline,
)
from services.tracking.ordering_experiments import PerKeySequenceExecutor  # noqa: E402
from services.tracking.reorder_buffer import TrackingReorderBuffer  # noqa: E402


HOP_MS = 1500
ALERT_COOLDOWN_MS = 10000


@dataclass(frozen=True)
class SimObservation:
    observation_id: str
    device_id: str
    process_session_id: str
    sequence: int
    event_time_ms: int
    arrival_time_ms: int
    latitude: float
    longitude: float
    label: str = "drone"

    def to_model(self) -> ShadowObservation:
        return ShadowObservation(
            observation_id=self.observation_id,
            device_id=self.device_id,
            observed_at=datetime.fromtimestamp(
                self.event_time_ms / 1000.0,
                tz=timezone.utc,
            ).isoformat(),
            event_time_ms=self.event_time_ms,
            sequence=self.sequence,
            process_session_id=self.process_session_id,
            label=self.label,
            confidence=0.9,
            aircraft_probability=0.05,
            rms_peak=0.5,
            avg_rms=0.3,
            estimated_peak_db=78.0,
            estimated_avg_db=74.0,
            location={
                "source": "simulated_node_position",
                "latitude": self.latitude,
                "longitude": self.longitude,
                "accuracy_m": 5.0,
            },
            model_id="deterministic-simulator",
            model_name="deterministic-simulator",
            ai_inference_time_ms=40,
            window_duration_ms=3000,
            hop_duration_ms=HOP_MS,
            sample_rate_hz=16000,
            trace_id=self.observation_id,
        )


def sustained(
    duration_seconds: int,
    *,
    device_id: str = "A01",
    latitude: float = 25.033,
    longitude: float = 121.565,
) -> list[SimObservation]:
    count = duration_seconds * 1000 // HOP_MS
    return [
        SimObservation(
            observation_id=f"obs-{device_id}-{sequence}",
            device_id=device_id,
            process_session_id=f"process-{device_id}",
            sequence=sequence,
            event_time_ms=(sequence - 1) * HOP_MS,
            arrival_time_ms=(sequence - 1) * HOP_MS,
            latitude=latitude,
            longitude=longitude,
        )
        for sequence in range(1, count + 1)
    ]


def admitted_observation_ids(
    observations: Iterable[SimObservation],
) -> set[str]:
    last_admitted: dict[str, int] = {}
    admitted = set()
    for observation in sorted(observations, key=lambda item: item.event_time_ms):
        previous = last_admitted.get(observation.device_id)
        if previous is None or observation.event_time_ms - previous >= ALERT_COOLDOWN_MS:
            admitted.add(observation.observation_id)
            last_admitted[observation.device_id] = observation.event_time_ms
    return admitted


def summarize_intervals(times: list[float]) -> dict:
    ordered = sorted(times)
    intervals = [later - earlier for earlier, later in zip(ordered, ordered[1:])]
    return {
        "track_point_count": len(ordered),
        "median_point_interval_ms": round(statistics.median(intervals), 2)
        if intervals
        else None,
        "p95_point_interval_ms": percentile(intervals, 0.95),
        "maximum_track_gap_ms": max(intervals) if intervals else None,
    }


def summarize_track_times(tracks: dict[str, list[float]]) -> dict:
    intervals = []
    for times in tracks.values():
        ordered = sorted(times)
        intervals.extend(
            later - earlier for earlier, later in zip(ordered, ordered[1:])
        )
    return {
        "track_point_count": sum(len(times) for times in tracks.values()),
        "median_point_interval_ms": round(statistics.median(intervals), 2)
        if intervals
        else None,
        "p95_point_interval_ms": percentile(intervals, 0.95),
        "maximum_track_gap_ms": max(intervals) if intervals else None,
    }


def percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if quantile == 0.50:
        return round(float(statistics.median(ordered)), 2)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * quantile)))
    return round(float(ordered[index]), 2)


def control_metrics(
    raw_observations: list[SimObservation],
    arrivals: list[SimObservation],
) -> dict:
    admitted_ids = admitted_observation_ids(raw_observations)
    seen_ids = set()
    tracks: dict[str, list[float]] = {}
    duplicate = 0
    late = 0
    for observation in sorted(arrivals, key=lambda item: item.arrival_time_ms):
        if observation.observation_id not in admitted_ids:
            continue
        if observation.observation_id in seen_ids:
            duplicate += 1
            continue
        seen_ids.add(observation.observation_id)
        track_key = sim_region_key(observation)
        points = tracks.setdefault(track_key, [])
        if points and observation.event_time_ms <= points[-1]:
            late += 1
            continue
        points.append(float(observation.event_time_ms))
    return {
        "raw_ai_observation_count": len(raw_observations),
        "observation_uploaded_count": 0,
        "alert_admitted_count": len(admitted_ids),
        "cooldown_rejected_count": len(raw_observations) - len(admitted_ids),
        "tracking_measurement_count": sum(len(points) for points in tracks.values()),
        "late_discard_count": late,
        "duplicate_discard_count": duplicate,
        "outlier_discard_count": 0,
        **summarize_track_times(tracks),
    }


def sim_region_key(observation: SimObservation) -> str:
    return (
        f"{observation.label}:"
        f"{int(observation.latitude * 100) / 100.0}:"
        f"{int(observation.longitude * 100) / 100.0}"
    )


def shadow_metrics(
    raw_observations: list[SimObservation],
    arrivals: list[SimObservation],
) -> dict:
    registry = ObservationShadowRegistry(max_observations=10000)
    tracking = ShadowTrackingPipeline(
        max_late_ms=2000,
        schedule_timers=False,
    )
    base_time = datetime(2026, 8, 25, tzinfo=timezone.utc)
    stream_keys = set()
    for observation in sorted(arrivals, key=lambda item: item.arrival_time_ms):
        model = observation.to_model()
        result = registry.ingest(
            model,
            received_at=base_time + timedelta(milliseconds=observation.arrival_time_ms),
        )
        if result.accepted:
            tracking.accept(model, arrival_time_ms=observation.arrival_time_ms)
            stream_keys.add(f"{observation.device_id}:{observation.process_session_id}")
    final_time = max((item.arrival_time_ms for item in arrivals), default=0) + 2001
    for stream_key in sorted(stream_keys):
        tracking.flush_stream(stream_key, now_ms=final_time)

    ingest = registry.metrics()
    track = tracking.snapshot()
    admitted_count = len(admitted_observation_ids(raw_observations))
    result = {
        "raw_ai_observation_count": len(raw_observations),
        "observation_uploaded_count": ingest["observation_uploaded_count"],
        "alert_admitted_count": admitted_count,
        "cooldown_rejected_count": len(raw_observations) - admitted_count,
        "tracking_measurement_count": track["tracking_measurement_count"],
        "late_discard_count": track["late_discard_count"],
        "duplicate_discard_count": ingest["duplicate_observation_count"]
        + track["duplicate_discard_count"],
        "outlier_discard_count": track["outlier_discard_count"],
        "track_point_count": track["track_point_count"],
        "median_point_interval_ms": track["median_point_interval_ms"],
        "p95_point_interval_ms": track["p95_point_interval_ms"],
        "maximum_track_gap_ms": track["maximum_track_gap_ms"],
        "sequence_gap_count": ingest["sequence_gap_count"],
        "sequence_out_of_order_count": ingest["sequence_out_of_order_count"],
        "track_count": track["track_count"],
    }
    tracking.reset()
    return result


def comparison(
    raw_observations: list[SimObservation],
    arrivals: list[SimObservation],
) -> dict:
    control = control_metrics(raw_observations, arrivals)
    shadow = shadow_metrics(raw_observations, arrivals)
    control_points = control["track_point_count"]
    shadow_points = shadow["track_point_count"]
    control_gap = control["maximum_track_gap_ms"]
    shadow_gap = shadow["maximum_track_gap_ms"]
    return {
        "control": control,
        "shadow": shadow,
        "improvement": {
            "point_density_multiplier": round(shadow_points / control_points, 2)
            if control_points
            else None,
            "maximum_gap_reduction_ms": control_gap - shadow_gap
            if control_gap is not None and shadow_gap is not None
            else None,
            "maximum_gap_reduction_percent": round(
                (control_gap - shadow_gap) / control_gap * 100.0,
                2,
            )
            if control_gap and shadow_gap is not None
            else None,
        },
    }


def scenario_matrix() -> dict[str, dict]:
    sustained_30 = sustained(30)
    sustained_60 = sustained(60)

    motion = []
    device_sequences = {"A01": 0, "A02": 0, "A03": 0}
    for index in range(20):
        device_id = ("A01", "A02", "A03")[min(2, index // 7)]
        device_sequences[device_id] += 1
        motion.append(
            SimObservation(
                observation_id=f"motion-{device_id}-{device_sequences[device_id]}",
                device_id=device_id,
                process_session_id=f"process-{device_id}",
                sequence=device_sequences[device_id],
                event_time_ms=index * HOP_MS,
                arrival_time_ms=index * HOP_MS,
                latitude=25.033 + index * 0.00005,
                longitude=121.565 + index * 0.00005,
            )
        )

    mild = sustained(30)
    mild_arrivals = [
        replace(item, arrival_time_ms=item.event_time_ms + (300 if item.sequence % 2 else -200))
        for item in mild
    ]
    heavy = sustained(30)
    heavy_arrivals = []
    for start in range(0, len(heavy), 3):
        chunk = heavy[start : start + 3]
        for offset, item in enumerate(reversed(chunk)):
            heavy_arrivals.append(
                replace(item, arrival_time_ms=start * HOP_MS + offset * 100)
            )

    duplicate = sustained(30)
    duplicate_arrivals = [*duplicate, replace(duplicate[5], arrival_time_ms=duplicate[5].arrival_time_ms + 50)]
    delayed = sustained(30)
    delayed_arrivals = [
        replace(delayed[1], arrival_time_ms=0),
        replace(delayed[2], arrival_time_ms=100),
        replace(delayed[0], arrival_time_ms=200),
        *delayed[3:],
    ]
    missing = sustained(30)
    missing_arrivals = [item for item in missing if item.sequence != 5]

    region_a = sustained(30, device_id="A01", latitude=25.033, longitude=121.565)
    region_b = sustained(30, device_id="B01", latitude=24.150, longitude=120.680)
    two_regions = sorted([*region_a, *region_b], key=lambda item: (item.arrival_time_ms, item.device_id))

    return {
        "sustained_drone_30s": comparison(sustained_30, sustained_30),
        "sustained_drone_60s": comparison(sustained_60, sustained_60),
        "A01_A02_A03_sequential_motion": comparison(motion, motion),
        "mild_network_jitter": comparison(mild, mild_arrivals),
        "heavy_network_jitter": comparison(heavy, heavy_arrivals),
        "duplicate_upload": comparison(duplicate, duplicate_arrivals),
        "delayed_observation": comparison(delayed, delayed_arrivals),
        "missing_observation": comparison(missing, missing_arrivals),
        "two_simultaneous_independent_regions": comparison(two_regions, two_regions),
    }


def ordering_experiment() -> dict:
    cases = {
        "one_second_spacing_E2_E3_E1": [("e2", 2, 2000), ("e3", 3, 3000), ("e1", 1, 1000)],
        "one_hop_spacing_E2_E3_E1": [("e2", 2, 1500), ("e3", 3, 3000), ("e1", 1, 0)],
    }
    output = {}
    for case_name, items in cases.items():
        options = {}
        sequence_executor = PerKeySequenceExecutor(max_late_ms=2000)
        sequence_emissions = []
        max_pending = 0
        for arrival_index, (observation_id, sequence, event_time_ms) in enumerate(items):
            result = sequence_executor.offer(
                "region-a",
                observation_id=observation_id,
                sequence=sequence,
                event_time_ms=event_time_ms,
                arrival_time_ms=arrival_index * 100,
                payload={},
            )
            sequence_emissions.extend(result.ready)
            max_pending = max(max_pending, sequence_executor.pending_count())
        options["sequence_aware_serialized"] = {
            "correct_recovered_points": len(sequence_emissions),
            "late_discard": sequence_executor.metrics()["late_discarded"],
            "additional_tracking_latency_p50_ms": percentile(
                [item.additional_latency_ms for item in sequence_emissions], 0.50
            ),
            "additional_tracking_latency_max_ms": max(
                (item.additional_latency_ms for item in sequence_emissions),
                default=0,
            ),
            "max_pending_items": max_pending,
            "complexity": "medium: per-key expected sequence + bounded gap timer",
        }

        for window_ms in (1500, 2000):
            buffer = TrackingReorderBuffer(window_ms)
            emissions: list[tuple[float, float]] = []
            max_pending = 0
            for arrival_index, (observation_id, _, event_time_ms) in enumerate(items):
                arrival_ms = arrival_index * 100.0
                result = buffer.offer(
                    "region-a",
                    observation_id=observation_id,
                    event_time_ms=event_time_ms,
                    payload={"arrival_time_ms": arrival_ms},
                )
                emissions.extend(
                    (item.event_time_ms, arrival_ms - float(item.payload["arrival_time_ms"]))
                    for item in result.ready
                )
                max_pending = max(max_pending, buffer.pending_count())
            flush_at_ms = float(window_ms)
            emissions.extend(
                (
                    item.event_time_ms,
                    max(0.0, flush_at_ms - float(item.payload["arrival_time_ms"])),
                )
                for item in buffer.flush_key("region-a")
            )
            latencies = [latency for _, latency in emissions]
            options[f"event_time_priority_{window_ms}_ms"] = {
                "correct_recovered_points": len(emissions),
                "late_discard": buffer.metrics()["late_discarded"],
                "additional_tracking_latency_p50_ms": percentile(latencies, 0.50),
                "additional_tracking_latency_max_ms": max(latencies, default=0),
                "max_pending_items": max_pending,
                "complexity": "medium-low: per-key heap + watermark + tail timer",
            }
        output[case_name] = options
    return output


def main() -> None:
    print(
        json.dumps(
            {
                "configuration": {
                    "hop_ms": HOP_MS,
                    "alert_cooldown_ms": ALERT_COOLDOWN_MS,
                    "smoothing": False,
                    "storage": "in_memory_only",
                },
                "scenarios": scenario_matrix(),
                "ordering_experiment": ordering_experiment(),
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
