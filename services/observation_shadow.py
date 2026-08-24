from __future__ import annotations

import math
import statistics
import threading
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from services.tracking.ordering_experiments import (
    PerKeySequenceExecutor,
    SequenceEmission,
)


class ShadowObservationLocation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    accuracy_m: Optional[float] = None


class ShadowObservationTimeSync(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Optional[int] = None
    quality: Optional[str] = None
    offset_ms: Optional[float] = None
    rtt_ms: Optional[float] = Field(default=None, ge=0.0)
    age_ms: Optional[int] = Field(default=None, ge=0)


class ShadowObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message_type: Literal["observation.v1"] = "observation.v1"
    schema_version: Literal[1] = 1
    observation_id: str = Field(min_length=1, max_length=200)
    device_id: str = Field(min_length=1, max_length=128)
    observed_at: str = Field(min_length=1, max_length=64)
    event_time_ms: int = Field(ge=0)
    sequence: int = Field(ge=1, le=2_147_483_647)
    process_session_id: str = Field(min_length=1, max_length=128)
    label: str = Field(min_length=1, max_length=64)
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    aircraft_probability: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    rms_peak: float
    avg_rms: float
    estimated_peak_db: float
    estimated_avg_db: float
    location: ShadowObservationLocation
    time_sync: Optional[ShadowObservationTimeSync] = None
    model_id: str = Field(min_length=1, max_length=128)
    model_name: str = Field(min_length=1, max_length=256)
    ai_inference_time_ms: int = Field(ge=0)
    window_duration_ms: int = Field(gt=0)
    hop_duration_ms: int = Field(gt=0)
    sample_rate_hz: int = Field(gt=0)
    audio_ref: None = None
    alert_candidate: bool = True
    trace_id: str = Field(min_length=1, max_length=200)


@dataclass(frozen=True)
class ShadowIngestResult:
    accepted: bool
    duplicate: bool
    gap_detected: int
    gap_filled: bool
    out_of_order: bool
    received_at: str


class ObservationShadowRegistry:
    """Bounded, in-memory shadow registry; never reads or writes production DB."""

    def __init__(self, *, max_observations: int = 10000) -> None:
        self.max_observations = max(1, int(max_observations))
        self._lock = threading.RLock()
        self._records: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._streams: dict[str, dict[str, Any]] = {}
        self._metrics = {
            "observation_received_count": 0,
            "observation_uploaded_count": 0,
            "duplicate_observation_count": 0,
            "sequence_gap_count": 0,
            "sequence_gap_filled_count": 0,
            "sequence_out_of_order_count": 0,
            "sequence_duplicate_count": 0,
            "evicted_observation_count": 0,
            "unretained_sequence_gap_count": 0,
        }

    def ingest(
        self,
        observation: ShadowObservation,
        *,
        received_at: Optional[datetime] = None,
    ) -> ShadowIngestResult:
        received = received_at or datetime.now(timezone.utc)
        received_iso = received.isoformat()
        with self._lock:
            self._metrics["observation_received_count"] += 1
            if observation.observation_id in self._records:
                self._metrics["duplicate_observation_count"] += 1
                self._records.move_to_end(observation.observation_id)
                return ShadowIngestResult(
                    accepted=False,
                    duplicate=True,
                    gap_detected=0,
                    gap_filled=False,
                    out_of_order=False,
                    received_at=received_iso,
                )

            stream_key = f"{observation.device_id}:{observation.process_session_id}"
            stream = self._streams.setdefault(
                stream_key,
                {"highest": 0, "seen": set(), "missing": set()},
            )
            sequence = observation.sequence
            highest = int(stream["highest"])
            seen: set[int] = stream["seen"]
            missing: set[int] = stream["missing"]
            gap_detected = 0
            gap_filled = False
            out_of_order = sequence < highest
            if sequence in seen:
                self._metrics["sequence_duplicate_count"] += 1
            elif sequence > highest:
                if sequence > highest + 1:
                    gap_detected = sequence - highest - 1
                    retained_gap_start = max(
                        highest + 1,
                        sequence - self.max_observations,
                    )
                    new_missing = set(range(retained_gap_start, sequence))
                    missing.update(new_missing)
                    self._metrics["sequence_gap_count"] += gap_detected
                    self._metrics["unretained_sequence_gap_count"] += max(
                        0,
                        gap_detected - len(new_missing),
                    )
                stream["highest"] = sequence
            elif sequence in missing:
                missing.remove(sequence)
                gap_filled = True
                self._metrics["sequence_gap_filled_count"] += 1

            if out_of_order:
                self._metrics["sequence_out_of_order_count"] += 1
            seen.add(sequence)
            if len(seen) > self.max_observations:
                cutoff = int(stream["highest"]) - self.max_observations
                stream["seen"] = {item for item in seen if item > cutoff}
            record = observation.model_dump()
            record["received_at"] = received_iso
            self._records[observation.observation_id] = record
            self._metrics["observation_uploaded_count"] += 1
            while len(self._records) > self.max_observations:
                self._records.popitem(last=False)
                self._metrics["evicted_observation_count"] += 1

            return ShadowIngestResult(
                accepted=True,
                duplicate=False,
                gap_detected=gap_detected,
                gap_filled=gap_filled,
                out_of_order=out_of_order,
                received_at=received_iso,
            )

    def metrics(self) -> dict[str, Any]:
        with self._lock:
            return {
                **self._metrics,
                "retained_observation_count": len(self._records),
                "stream_count": len(self._streams),
                "open_sequence_gap_count": sum(
                    len(stream["missing"]) for stream in self._streams.values()
                ),
                "storage": "bounded_in_memory_shadow_only",
            }

    def reset(self) -> None:
        with self._lock:
            self._records.clear()
            self._streams.clear()
            for name in self._metrics:
                self._metrics[name] = 0


class ShadowTrackingPipeline:
    """Independent observation fusion/tracking shadow with no smoothing or DB IO."""

    def __init__(
        self,
        *,
        max_late_ms: float = 2000.0,
        max_points_per_track: int = 5000,
        schedule_timers: bool = True,
    ) -> None:
        self.max_late_ms = float(max_late_ms)
        self.max_points_per_track = max(1, int(max_points_per_track))
        self.schedule_timers = bool(schedule_timers)
        self.sequence_executor = PerKeySequenceExecutor(max_late_ms=max_late_ms)
        self._lock = threading.RLock()
        self._timers: dict[str, threading.Timer] = {}
        self._fusion_buckets: dict[str, dict[int, dict[str, dict[str, Any]]]] = {}
        self._tracks: dict[str, list[dict[str, Any]]] = {}
        self._metrics = {
            "tracking_measurement_count": 0,
            "late_discard_count": 0,
            "duplicate_discard_count": 0,
            "outlier_discard_count": 0,
            "sequence_gap_skipped_count": 0,
        }

    def accept(self, observation: ShadowObservation, *, arrival_time_ms: float) -> None:
        stream_key = f"{observation.device_id}:{observation.process_session_id}"
        payload = observation.model_dump()
        result = self.sequence_executor.offer(
            stream_key,
            observation_id=observation.observation_id,
            sequence=observation.sequence,
            event_time_ms=observation.event_time_ms,
            arrival_time_ms=arrival_time_ms,
            payload=payload,
        )
        if result.discarded_reason:
            metric = (
                "duplicate_discard_count"
                if "duplicate" in result.discarded_reason
                else "late_discard_count"
            )
            with self._lock:
                self._metrics[metric] += 1
        self._process_emissions(result.ready)
        if self.schedule_timers and self.sequence_executor.pending_count(stream_key):
            self._schedule_flush(stream_key)

    def flush_stream(self, stream_key: str, *, now_ms: float) -> None:
        with self._lock:
            self._timers.pop(stream_key, None)
        result = self.sequence_executor.flush_expired(stream_key, now_ms=now_ms)
        with self._lock:
            self._metrics["sequence_gap_skipped_count"] += result.gaps_skipped
        self._process_emissions(result.ready)
        if self.schedule_timers and self.sequence_executor.pending_count(stream_key):
            self._schedule_flush(stream_key)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            intervals = []
            tracking_latencies = []
            track_summaries = {}
            for key, points in self._tracks.items():
                times = [float(point["measurement_event_time_ms"]) for point in points]
                track_intervals = [
                    later - earlier
                    for earlier, later in zip(times, times[1:])
                    if later >= earlier
                ]
                intervals.extend(track_intervals)
                tracking_latencies.extend(
                    float(point["additional_tracking_latency_ms"])
                    for point in points
                )
                track_summaries[key] = {
                    "track_point_count": len(points),
                    "median_point_interval_ms": _percentile(track_intervals, 0.50),
                    "p95_point_interval_ms": _percentile(track_intervals, 0.95),
                    "maximum_track_gap_ms": max(track_intervals) if track_intervals else None,
                }
            return {
                **self._metrics,
                "track_point_count": sum(len(points) for points in self._tracks.values()),
                "track_count": len(self._tracks),
                "median_point_interval_ms": _percentile(intervals, 0.50),
                "p95_point_interval_ms": _percentile(intervals, 0.95),
                "maximum_track_gap_ms": max(intervals) if intervals else None,
                "additional_tracking_latency_p50_ms": _percentile(
                    tracking_latencies, 0.50
                ),
                "additional_tracking_latency_p95_ms": _percentile(
                    tracking_latencies, 0.95
                ),
                "additional_tracking_latency_max_ms": max(tracking_latencies)
                if tracking_latencies
                else None,
                "ordering": self.sequence_executor.metrics(),
                "tracks": track_summaries,
                "retained_fusion_bucket_count": sum(
                    len(buckets) for buckets in self._fusion_buckets.values()
                ),
                "storage": "bounded_in_memory_shadow_only",
                "smoothing": "disabled",
            }

    def reset(self) -> None:
        with self._lock:
            for timer in self._timers.values():
                timer.cancel()
            self._timers.clear()
            self._fusion_buckets.clear()
            self._tracks.clear()
            for name in self._metrics:
                self._metrics[name] = 0
        self.sequence_executor.reset()

    def _process_emissions(self, emissions: tuple[SequenceEmission, ...]) -> None:
        for emission in emissions:
            self._process_observation(emission)

    def _process_observation(self, emission: SequenceEmission) -> None:
        observation = emission.item.payload
        location = observation.get("location") or {}
        latitude = _coordinate(location.get("latitude"), -90.0, 90.0)
        longitude = _coordinate(location.get("longitude"), -180.0, 180.0)
        if latitude is None or longitude is None:
            with self._lock:
                self._metrics["outlier_discard_count"] += 1
            return

        label = str(observation.get("label") or "unknown").lower()
        region_key = f"{label}:{_region_cell(latitude)}:{_region_cell(longitude)}"
        hop_ms = max(1, int(observation.get("hop_duration_ms") or 1500))
        event_time_ms = float(observation.get("event_time_ms") or 0.0)
        bucket = int(event_time_ms // hop_ms)
        with self._lock:
            region_buckets = self._fusion_buckets.setdefault(region_key, {})
            observations = region_buckets.setdefault(bucket, {})
            observations[str(observation.get("device_id"))] = observation
            weighted = list(observations.values())
            total_weight = sum(_observation_weight(item) for item in weighted)
            center_lat = sum(
                float((item.get("location") or {})["latitude"])
                * _observation_weight(item)
                for item in weighted
            ) / total_weight
            center_lng = sum(
                float((item.get("location") or {})["longitude"])
                * _observation_weight(item)
                for item in weighted
            ) / total_weight
            measurement_time_ms = bucket * hop_ms
            points = self._tracks.setdefault(region_key, [])
            existing = next(
                (
                    point
                    for point in points
                    if point["measurement_event_time_ms"] == measurement_time_ms
                ),
                None,
            )
            if existing is not None:
                existing.update(
                    latitude=center_lat,
                    longitude=center_lng,
                    node_count=len(weighted),
                    revision=int(existing["revision"]) + 1,
                )
                return
            if points and measurement_time_ms <= float(
                points[-1]["measurement_event_time_ms"]
            ):
                self._metrics["late_discard_count"] += 1
                return
            points.append(
                {
                    "measurement_event_time_ms": measurement_time_ms,
                    "latitude": center_lat,
                    "longitude": center_lng,
                    "node_count": len(weighted),
                    "revision": 1,
                    "source_observation_id": observation.get("observation_id"),
                    "additional_tracking_latency_ms": emission.additional_latency_ms,
                }
            )
            if len(points) > self.max_points_per_track:
                del points[: len(points) - self.max_points_per_track]
            self._metrics["tracking_measurement_count"] += 1

            minimum_bucket = bucket - 20
            for old_bucket in list(region_buckets):
                if old_bucket < minimum_bucket:
                    region_buckets.pop(old_bucket, None)

    def _schedule_flush(self, stream_key: str) -> None:
        with self._lock:
            existing = self._timers.get(stream_key)
            if existing is not None and existing.is_alive():
                return
            timer = threading.Timer(
                self.max_late_ms / 1000.0,
                self.flush_stream,
                kwargs={
                    "stream_key": stream_key,
                    "now_ms": datetime.now(timezone.utc).timestamp() * 1000.0
                    + self.max_late_ms,
                },
            )
            timer.daemon = True
            self._timers[stream_key] = timer
            timer.start()


def _coordinate(value: Any, minimum: float, maximum: float) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    numeric = float(value)
    if not math.isfinite(numeric) or numeric < minimum or numeric > maximum:
        return None
    return numeric


def _observation_weight(observation: dict[str, Any]) -> float:
    confidence = observation.get("confidence")
    if isinstance(confidence, (int, float)) and math.isfinite(float(confidence)):
        return max(0.05, float(confidence))
    return 1.0


def _region_cell(value: float) -> float:
    return math.floor(value * 100.0) / 100.0


def _percentile(values: list[float], quantile: float) -> Optional[float]:
    if not values:
        return None
    if quantile == 0.50:
        return round(float(statistics.median(values)), 2)
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * quantile)))
    return round(float(ordered[index]), 2)
