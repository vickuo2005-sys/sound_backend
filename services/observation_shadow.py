from __future__ import annotations

import math
import statistics
import threading
from collections import OrderedDict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from services.tracking.ordering_experiments import (
    PerKeySequenceExecutor,
    SequenceEmission,
)
from services.tracking.serialized_mailbox import (
    MailboxCapacityError,
    PerKeySerializedMailbox,
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
    device_wall_clock_ms: Optional[int] = Field(default=None, ge=0)
    device_monotonic_ms: Optional[float] = Field(default=None, ge=0.0)
    monotonic_session_id: Optional[str] = Field(default=None, max_length=128)


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

    def __init__(
        self,
        *,
        max_observations: int = 10000,
        ttl_seconds: float = 3600.0,
        max_streams: int = 2048,
    ) -> None:
        self.max_observations = max(1, int(max_observations))
        self.ttl_seconds = max(1.0, float(ttl_seconds))
        self.max_streams = max(1, int(max_streams))
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
            "cleanup_count": 0,
            "expired_count": 0,
            "expired_stream_count": 0,
            "forced_stream_eviction_count": 0,
            "max_entries_seen": 0,
            "max_streams_seen": 0,
            "request_payload_bytes": 0,
            "request_wire_estimate_bytes": 0,
            "minimum_payload_bytes": 0,
            "maximum_payload_bytes": 0,
        }
        self._first_received_ms: Optional[float] = None
        self._last_received_ms: Optional[float] = None

    def ingest(
        self,
        observation: ShadowObservation,
        *,
        received_at: Optional[datetime] = None,
        payload_bytes: int = 0,
        request_wire_estimate_bytes: int = 0,
    ) -> ShadowIngestResult:
        received = received_at or datetime.now(timezone.utc)
        received_iso = received.isoformat()
        received_ms = received.timestamp() * 1000.0
        with self._lock:
            self._cleanup_expired_locked(received_ms)
            self._metrics["observation_received_count"] += 1
            normalized_payload_bytes = max(0, int(payload_bytes))
            normalized_request_bytes = max(
                normalized_payload_bytes,
                int(request_wire_estimate_bytes),
            )
            self._metrics["request_payload_bytes"] += normalized_payload_bytes
            self._metrics["request_wire_estimate_bytes"] += normalized_request_bytes
            if normalized_payload_bytes:
                current_minimum = self._metrics["minimum_payload_bytes"]
                self._metrics["minimum_payload_bytes"] = (
                    normalized_payload_bytes
                    if not current_minimum
                    else min(current_minimum, normalized_payload_bytes)
                )
                self._metrics["maximum_payload_bytes"] = max(
                    self._metrics["maximum_payload_bytes"],
                    normalized_payload_bytes,
                )
            self._first_received_ms = (
                received_ms
                if self._first_received_ms is None
                else self._first_received_ms
            )
            self._last_received_ms = received_ms
            if observation.observation_id in self._records:
                self._metrics["duplicate_observation_count"] += 1
                return ShadowIngestResult(
                    accepted=False,
                    duplicate=True,
                    gap_detected=0,
                    gap_filled=False,
                    out_of_order=False,
                    received_at=received_iso,
                )

            stream_key = f"{observation.device_id}:{observation.process_session_id}"
            self._ensure_stream_capacity_locked(stream_key)
            stream = self._streams.setdefault(
                stream_key,
                {
                    "highest": 0,
                    "seen": set(),
                    "missing": set(),
                    "last_activity_ms": received_ms,
                },
            )
            stream["last_activity_ms"] = received_ms
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
            record["_received_epoch_ms"] = received_ms
            self._records[observation.observation_id] = record
            self._metrics["observation_uploaded_count"] += 1
            while len(self._records) > self.max_observations:
                self._records.popitem(last=False)
                self._metrics["evicted_observation_count"] += 1
            self._metrics["max_entries_seen"] = max(
                self._metrics["max_entries_seen"],
                len(self._records),
            )
            self._metrics["max_streams_seen"] = max(
                self._metrics["max_streams_seen"],
                len(self._streams),
            )

            return ShadowIngestResult(
                accepted=True,
                duplicate=False,
                gap_detected=gap_detected,
                gap_filled=gap_filled,
                out_of_order=out_of_order,
                received_at=received_iso,
            )

    def cleanup_expired(self, *, now: Optional[datetime] = None) -> int:
        cleanup_now = now or datetime.now(timezone.utc)
        with self._lock:
            return self._cleanup_expired_locked(cleanup_now.timestamp() * 1000.0)

    def metrics(self) -> dict[str, Any]:
        with self._lock:
            duration_ms = (
                0.0
                if self._first_received_ms is None or self._last_received_ms is None
                else max(0.0, self._last_received_ms - self._first_received_ms)
            )
            received_count = self._metrics["observation_received_count"]
            return {
                **self._metrics,
                "retained_observation_count": len(self._records),
                "current_entries": len(self._records),
                "stream_count": len(self._streams),
                "dedup_cache_size": len(self._records),
                "open_sequence_gap_count": sum(
                    len(stream["missing"]) for stream in self._streams.values()
                ),
                "average_payload_bytes": round(
                    self._metrics["request_payload_bytes"] / received_count,
                    2,
                )
                if received_count
                else None,
                "observed_requests_per_minute": round(
                    received_count * 60_000.0 / duration_ms,
                    2,
                )
                if duration_ms > 0
                else None,
                "ttl_seconds": self.ttl_seconds,
                "max_entries": self.max_observations,
                "max_streams": self.max_streams,
                "storage": "bounded_in_memory_shadow_only",
            }

    def reset(self) -> None:
        with self._lock:
            self._records.clear()
            self._streams.clear()
            self._first_received_ms = None
            self._last_received_ms = None
            for name in self._metrics:
                self._metrics[name] = 0

    def _cleanup_expired_locked(self, now_ms: float) -> int:
        cutoff_ms = now_ms - self.ttl_seconds * 1000.0
        expired_ids = [
            observation_id
            for observation_id, record in self._records.items()
            if float(record.get("_received_epoch_ms") or 0.0) <= cutoff_ms
        ]
        expired_streams = [
            key
            for key, stream in self._streams.items()
            if float(stream.get("last_activity_ms") or 0.0) <= cutoff_ms
        ]
        if not expired_ids and not expired_streams:
            return 0
        for observation_id in expired_ids:
            self._records.pop(observation_id, None)
        for key in expired_streams:
            self._streams.pop(key, None)
        self._metrics["cleanup_count"] += 1
        self._metrics["expired_count"] += len(expired_ids)
        self._metrics["expired_stream_count"] += len(expired_streams)
        return len(expired_ids)

    def _ensure_stream_capacity_locked(self, stream_key: str) -> None:
        if stream_key in self._streams:
            return
        while len(self._streams) >= self.max_streams:
            oldest_key = min(
                self._streams,
                key=lambda key: float(
                    self._streams[key].get("last_activity_ms") or 0.0
                ),
            )
            self._streams.pop(oldest_key, None)
            self._metrics["forced_stream_eviction_count"] += 1


class ObservationClockQualityTracker:
    """Bounded per-device/session clock diagnostics; monotonic clocks never cross keys."""

    def __init__(
        self,
        *,
        max_streams: int = 2048,
        max_samples_per_stream: int = 240,
        stream_ttl_ms: float = 3_600_000.0,
        clock_jump_threshold_ms: float = 1000.0,
    ) -> None:
        self.max_streams = max(1, int(max_streams))
        self.max_samples_per_stream = max(2, int(max_samples_per_stream))
        self.stream_ttl_ms = max(1.0, float(stream_ttl_ms))
        self.clock_jump_threshold_ms = max(1.0, float(clock_jump_threshold_ms))
        self._lock = threading.RLock()
        self._streams: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._clock_jump_count = 0
        self._cleanup_count = 0
        self._expired_stream_count = 0

    def observe(
        self,
        observation: ShadowObservation,
        *,
        received_at_ms: float,
    ) -> None:
        time_sync = observation.time_sync
        if time_sync is None:
            return
        offset_ms = _finite_number(time_sync.offset_ms)
        device_wall_ms = _finite_number(time_sync.device_wall_clock_ms)
        device_monotonic_ms = _finite_number(time_sync.device_monotonic_ms)
        if offset_ms is None and device_wall_ms is not None:
            offset_ms = float(received_at_ms) - device_wall_ms
        if offset_ms is None:
            return
        key = f"{observation.device_id}:{observation.process_session_id}"
        with self._lock:
            self._cleanup_expired_locked(float(received_at_ms), exclude_key=key)
            if key not in self._streams and len(self._streams) >= self.max_streams:
                self._streams.popitem(last=False)
                self._expired_stream_count += 1
                self._cleanup_count += 1
            stream = self._streams.setdefault(
                key,
                {
                    "device_id": observation.device_id,
                    "process_session_id": observation.process_session_id,
                    "samples": deque(maxlen=self.max_samples_per_stream),
                    "last_activity_ms": float(received_at_ms),
                    "clock_jump_count": 0,
                },
            )
            samples: deque[dict[str, float | None]] = stream["samples"]
            if samples and device_wall_ms is not None and device_monotonic_ms is not None:
                previous = samples[-1]
                previous_wall = _finite_number(previous.get("device_wall_ms"))
                previous_monotonic = _finite_number(
                    previous.get("device_monotonic_ms")
                )
                if previous_wall is not None and previous_monotonic is not None:
                    wall_delta = device_wall_ms - previous_wall
                    monotonic_delta = device_monotonic_ms - previous_monotonic
                    if abs(wall_delta - monotonic_delta) >= self.clock_jump_threshold_ms:
                        stream["clock_jump_count"] += 1
                        self._clock_jump_count += 1
            samples.append(
                {
                    "offset_ms": offset_ms,
                    "device_wall_ms": device_wall_ms,
                    "device_monotonic_ms": device_monotonic_ms,
                    "received_at_ms": float(received_at_ms),
                }
            )
            stream["last_activity_ms"] = float(received_at_ms)
            self._streams.move_to_end(key)

    def cleanup_expired(self, *, now_ms: float) -> int:
        with self._lock:
            return self._cleanup_expired_locked(float(now_ms))

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            all_offsets: list[float] = []
            all_drifts: list[float] = []
            streams: dict[str, dict[str, Any]] = {}
            for key, stream in self._streams.items():
                samples = list(stream["samples"])
                offsets = [
                    float(sample["offset_ms"])
                    for sample in samples
                    if _finite_number(sample.get("offset_ms")) is not None
                ]
                all_offsets.extend(offsets)
                drift = _clock_drift_ms_per_min(samples)
                if drift is not None:
                    all_drifts.append(drift)
                streams[key] = {
                    "device_id": stream["device_id"],
                    "process_session_id": stream["process_session_id"],
                    "sample_count": len(samples),
                    "estimated_clock_offset_ms": offsets[-1] if offsets else None,
                    "clock_offset_p95_ms": _percentile(offsets, 0.95),
                    "clock_drift_ms_per_min": drift,
                    "clock_jump_count": stream["clock_jump_count"],
                }
            return {
                "stream_count": len(self._streams),
                "sample_count": len(all_offsets),
                "estimated_clock_offset_ms": all_offsets[-1]
                if all_offsets
                else None,
                "clock_offset_p95_ms": _percentile(all_offsets, 0.95),
                "clock_drift_ms_per_min": _percentile(all_drifts, 0.95),
                "clock_jump_count": self._clock_jump_count,
                "cleanup_count": self._cleanup_count,
                "expired_stream_count": self._expired_stream_count,
                "streams": streams,
                "monotonic_comparison_scope": "same_device_process_session_only",
            }

    def reset(self) -> None:
        with self._lock:
            self._streams.clear()
            self._clock_jump_count = 0
            self._cleanup_count = 0
            self._expired_stream_count = 0

    def _cleanup_expired_locked(
        self,
        now_ms: float,
        *,
        exclude_key: Optional[str] = None,
    ) -> int:
        expired = [
            key
            for key, stream in self._streams.items()
            if key != exclude_key
            and now_ms - float(stream["last_activity_ms"]) >= self.stream_ttl_ms
        ]
        for key in expired:
            self._streams.pop(key, None)
        if expired:
            self._cleanup_count += 1
            self._expired_stream_count += len(expired)
        return len(expired)


class ShadowTrackingPipeline:
    """Independent observation fusion/tracking shadow with no smoothing or DB IO."""

    def __init__(
        self,
        *,
        max_late_ms: float = 2000.0,
        max_points_per_track: int = 5000,
        max_pending_per_key: int = 1024,
        max_sequence_keys: int = 2048,
        max_tracks: int = 2048,
        state_ttl_ms: float = 3_600_000.0,
        fusion_late_attach_ms: float = 2000.0,
        mailbox_workers: int = 4,
        schedule_timers: bool = True,
    ) -> None:
        self.max_late_ms = float(max_late_ms)
        self.max_points_per_track = max(1, int(max_points_per_track))
        self.max_tracks = max(1, int(max_tracks))
        self.state_ttl_ms = max(1.0, float(state_ttl_ms))
        self.fusion_late_attach_ms = max(0.0, float(fusion_late_attach_ms))
        self.schedule_timers = bool(schedule_timers)
        self.sequence_executor = PerKeySequenceExecutor(
            max_late_ms=max_late_ms,
            max_pending_per_key=max_pending_per_key,
            max_keys=max_sequence_keys,
            key_ttl_ms=self.state_ttl_ms,
        )
        self.mailbox = PerKeySerializedMailbox(
            max_workers=mailbox_workers,
            max_pending_per_key=max_pending_per_key,
            max_keys=max_tracks,
            key_ttl_ms=self.state_ttl_ms,
        )
        self._lock = threading.RLock()
        self._timers: dict[str, threading.Timer] = {}
        self._fusion_buckets: dict[str, dict[int, dict[str, dict[str, Any]]]] = {}
        self._tracks: dict[str, list[dict[str, Any]]] = {}
        self._track_last_activity_ms: dict[str, float] = {}
        self._metrics = {
            "tracking_measurement_count": 0,
            "late_discard_count": 0,
            "duplicate_discard_count": 0,
            "outlier_discard_count": 0,
            "sequence_gap_skipped_count": 0,
            "sequence_gate_pass_count": 0,
            "fusion_applied_count": 0,
            "fusion_revision_count": 0,
            "fusion_late_attach_count": 0,
            "fusion_late_drop_count": 0,
            "mailbox_drop_count": 0,
            "track_cleanup_count": 0,
            "expired_track_count": 0,
            "max_tracks_seen": 0,
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

    def snapshot(self, *, wait_for_idle: bool = True) -> dict[str, Any]:
        if wait_for_idle:
            self.mailbox.wait_for_idle(timeout_seconds=2.0)
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
                "additional_tracking_latency_p99_ms": _percentile(
                    tracking_latencies, 0.99
                ),
                "additional_tracking_latency_max_ms": max(tracking_latencies)
                if tracking_latencies
                else None,
                "ordering": self.sequence_executor.metrics(),
                "mailbox": self.mailbox.metrics(),
                "tracks": track_summaries,
                "retained_fusion_bucket_count": sum(
                    len(buckets) for buckets in self._fusion_buckets.values()
                ),
                "current_track_entries": len(self._tracks),
                "max_tracks": self.max_tracks,
                "state_ttl_ms": self.state_ttl_ms,
                "storage": "bounded_in_memory_shadow_only",
                "smoothing": "disabled",
            }

    def reset(self) -> None:
        with self._lock:
            for timer in self._timers.values():
                timer.cancel()
            self._timers.clear()
        self.mailbox.reset()
        with self._lock:
            self._fusion_buckets.clear()
            self._tracks.clear()
            self._track_last_activity_ms.clear()
            for name in self._metrics:
                self._metrics[name] = 0
        self.sequence_executor.reset()

    def _process_emissions(self, emissions: tuple[SequenceEmission, ...]) -> None:
        for emission in emissions:
            region_key = _region_key_for_observation(emission.item.payload)
            with self._lock:
                self._metrics["sequence_gate_pass_count"] += 1
            future = self.mailbox.submit(
                region_key,
                self._process_observation,
                emission,
            )
            if future.done() and isinstance(future.exception(), MailboxCapacityError):
                with self._lock:
                    self._metrics["mailbox_drop_count"] += 1

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
            self._cleanup_tracks_locked(emission.emitted_at_ms, exclude_key=region_key)
            self._ensure_track_capacity_locked(region_key)
            self._track_last_activity_ms[region_key] = emission.emitted_at_ms
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
                latest_time_ms = float(points[-1]["measurement_event_time_ms"])
                if latest_time_ms - measurement_time_ms > self.fusion_late_attach_ms:
                    self._metrics["late_discard_count"] += 1
                    self._metrics["fusion_late_drop_count"] += 1
                    return
                existing.update(
                    latitude=center_lat,
                    longitude=center_lng,
                    node_count=len(weighted),
                    revision=int(existing["revision"]) + 1,
                )
                self._metrics["fusion_applied_count"] += 1
                self._metrics["fusion_revision_count"] += 1
                self._metrics["fusion_late_attach_count"] += 1
                self._metrics["tracking_measurement_count"] += 1
                return
            if points and measurement_time_ms <= float(
                points[-1]["measurement_event_time_ms"]
            ):
                self._metrics["late_discard_count"] += 1
                self._metrics["fusion_late_drop_count"] += 1
                return
            point = {
                "measurement_event_time_ms": measurement_time_ms,
                "latitude": center_lat,
                "longitude": center_lng,
                "node_count": len(weighted),
                "revision": 1,
                "source_observation_id": observation.get("observation_id"),
                "additional_tracking_latency_ms": emission.additional_latency_ms,
            }
            points.append(point)
            points.sort(key=lambda item: float(item["measurement_event_time_ms"]))
            if len(points) > self.max_points_per_track:
                del points[: len(points) - self.max_points_per_track]
            self._metrics["fusion_applied_count"] += 1
            self._metrics["tracking_measurement_count"] += 1
            self._metrics["max_tracks_seen"] = max(
                self._metrics["max_tracks_seen"],
                len(self._tracks),
            )

            minimum_bucket = bucket - 20
            for old_bucket in list(region_buckets):
                if old_bucket < minimum_bucket:
                    region_buckets.pop(old_bucket, None)

    def _cleanup_tracks_locked(
        self,
        now_ms: float,
        *,
        exclude_key: Optional[str] = None,
    ) -> int:
        expired = [
            key
            for key, last_activity in self._track_last_activity_ms.items()
            if key != exclude_key and now_ms - last_activity >= self.state_ttl_ms
        ]
        for key in expired:
            self._tracks.pop(key, None)
            self._fusion_buckets.pop(key, None)
            self._track_last_activity_ms.pop(key, None)
        if expired:
            self._metrics["track_cleanup_count"] += 1
            self._metrics["expired_track_count"] += len(expired)
        return len(expired)

    def _ensure_track_capacity_locked(self, region_key: str) -> None:
        if region_key in self._tracks:
            return
        while len(self._tracks) >= self.max_tracks:
            oldest_key = min(
                self._track_last_activity_ms,
                key=self._track_last_activity_ms.__getitem__,
            )
            self._tracks.pop(oldest_key, None)
            self._fusion_buckets.pop(oldest_key, None)
            self._track_last_activity_ms.pop(oldest_key, None)
            self._metrics["track_cleanup_count"] += 1
            self._metrics["expired_track_count"] += 1

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


def _region_key_for_observation(observation: dict[str, Any]) -> str:
    location = observation.get("location") or {}
    latitude = _coordinate(location.get("latitude"), -90.0, 90.0)
    longitude = _coordinate(location.get("longitude"), -180.0, 180.0)
    label = str(observation.get("label") or "unknown").lower()
    if latitude is None or longitude is None:
        return f"invalid:{label}:{observation.get('device_id') or 'unknown'}"
    return f"{label}:{_region_cell(latitude)}:{_region_cell(longitude)}"


def _finite_number(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    numeric = float(value)
    return numeric if math.isfinite(numeric) else None


def _clock_drift_ms_per_min(
    samples: list[dict[str, float | None]],
) -> Optional[float]:
    if len(samples) < 2:
        return None
    first = samples[0]
    last = samples[-1]
    first_offset = _finite_number(first.get("offset_ms"))
    last_offset = _finite_number(last.get("offset_ms"))
    first_monotonic = _finite_number(first.get("device_monotonic_ms"))
    last_monotonic = _finite_number(last.get("device_monotonic_ms"))
    if (
        first_offset is None
        or last_offset is None
        or first_monotonic is None
        or last_monotonic is None
    ):
        return None
    elapsed_minutes = (last_monotonic - first_monotonic) / 60_000.0
    if elapsed_minutes <= 0:
        return None
    return round((last_offset - first_offset) / elapsed_minutes, 3)


def _percentile(values: list[float], quantile: float) -> Optional[float]:
    if not values:
        return None
    if quantile == 0.50:
        return round(float(statistics.median(values)), 2)
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * quantile)))
    return round(float(ordered[index]), 2)
