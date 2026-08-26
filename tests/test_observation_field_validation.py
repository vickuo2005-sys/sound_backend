from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

import main
from services.observation_shadow import (
    ObservationClockQualityTracker,
    ObservationShadowRegistry,
    ShadowObservation,
    ShadowTrackingPipeline,
)


BASE_TIME = datetime(2026, 8, 25, tzinfo=timezone.utc)


def observation(
    device_id: str,
    process_session_id: str,
    sequence: int,
    event_time_ms: int,
    *,
    latitude: float = 25.033,
    longitude: float = 121.565,
    offset_ms: float = 10.0,
    wall_clock_ms: int = 1_787_616_000_000,
    monotonic_ms: float = 1000.0,
) -> ShadowObservation:
    observation_id = f"obs-{device_id}-{process_session_id}-{sequence}"
    return ShadowObservation.model_validate(
        {
            "message_type": "observation.v1",
            "schema_version": 1,
            "observation_id": observation_id,
            "device_id": device_id,
            "observed_at": BASE_TIME.isoformat(),
            "event_time_ms": event_time_ms,
            "sequence": sequence,
            "process_session_id": process_session_id,
            "label": "drone",
            "confidence": 0.9,
            "aircraft_probability": 0.1,
            "rms_peak": 0.5,
            "avg_rms": 0.3,
            "estimated_peak_db": 78.0,
            "estimated_avg_db": 74.0,
            "location": {
                "source": "cached_device_gps",
                "latitude": latitude,
                "longitude": longitude,
                "accuracy_m": 8.0,
            },
            "time_sync": {
                "version": 1,
                "quality": "good",
                "offset_ms": offset_ms,
                "rtt_ms": 20.0,
                "age_ms": 1000,
                "device_wall_clock_ms": wall_clock_ms,
                "device_monotonic_ms": monotonic_ms,
                "monotonic_session_id": process_session_id,
            },
            "model_id": "v1",
            "model_name": "V1",
            "ai_inference_time_ms": 40,
            "window_duration_ms": 3000,
            "hop_duration_ms": 1500,
            "sample_rate_hz": 16000,
            "audio_ref": None,
            "alert_candidate": True,
            "trace_id": observation_id,
        }
    )


def test_registry_ttl_cleanup_and_max_entries_are_bounded() -> None:
    registry = ObservationShadowRegistry(
        max_observations=2,
        ttl_seconds=1,
        max_streams=2,
    )
    registry.ingest(observation("A01", "s1", 1, 0), received_at=BASE_TIME)
    registry.ingest(
        observation("A02", "s1", 1, 0),
        received_at=BASE_TIME + timedelta(milliseconds=100),
    )

    assert registry.metrics()["current_entries"] == 2
    assert registry.cleanup_expired(now=BASE_TIME + timedelta(seconds=2)) == 2
    metrics = registry.metrics()
    assert metrics["current_entries"] == 0
    assert metrics["expired_count"] == 2
    assert metrics["max_entries_seen"] == 2


def test_app_restart_same_device_sequence_one_is_not_duplicate() -> None:
    registry = ObservationShadowRegistry()

    first = registry.ingest(observation("A01", "process-x", 1, 0))
    restarted = registry.ingest(observation("A01", "process-y", 1, 1500))

    assert first.accepted is True
    assert restarted.accepted is True
    assert registry.metrics()["duplicate_observation_count"] == 0
    assert registry.metrics()["stream_count"] == 2


def test_cross_device_reverse_arrival_produces_one_consistent_fusion_revision() -> None:
    pipeline = ShadowTrackingPipeline(schedule_timers=False, mailbox_workers=2)
    try:
        arrivals = [
            observation("A03", "s3", 1, 1200),
            observation("A01", "s1", 1, 1000),
            observation("A02", "s2", 1, 1100),
        ]
        for arrival_index, item in enumerate(arrivals):
            pipeline.accept(item, arrival_time_ms=arrival_index * 100.0)

        snapshot = pipeline.snapshot()
        assert snapshot["track_point_count"] == 1
        assert snapshot["fusion_applied_count"] == 3
        assert snapshot["fusion_revision_count"] == 2
        assert snapshot["fusion_late_attach_count"] == 2
        assert snapshot["fusion_late_drop_count"] == 0
    finally:
        pipeline.mailbox.close()


def test_cross_device_very_late_attach_is_explicitly_dropped() -> None:
    pipeline = ShadowTrackingPipeline(
        schedule_timers=False,
        fusion_late_attach_ms=2000,
    )
    try:
        for arrival_index, item in enumerate(
            [
                observation("A01", "s1", 1, 1000),
                observation("A01", "s1", 2, 4500),
                observation("A02", "s2", 1, 1100),
            ]
        ):
            pipeline.accept(item, arrival_time_ms=arrival_index * 100.0)

        snapshot = pipeline.snapshot()
        assert snapshot["fusion_late_drop_count"] == 1
        assert snapshot["late_discard_count"] == 1
        assert snapshot["fusion_applied_count"] == 2
    finally:
        pipeline.mailbox.close()


def test_clock_quality_uses_only_same_process_monotonic_deltas() -> None:
    tracker = ObservationClockQualityTracker(clock_jump_threshold_ms=1000)
    tracker.observe(
        observation("A01", "s1", 1, 0, offset_ms=10, monotonic_ms=0),
        received_at_ms=1_000_000,
    )
    tracker.observe(
        observation(
            "A01",
            "s1",
            2,
            1500,
            offset_ms=12,
            wall_clock_ms=1_787_616_060_000,
            monotonic_ms=60_000,
        ),
        received_at_ms=1_060_000,
    )
    tracker.observe(
        observation(
            "A01",
            "s1",
            3,
            3000,
            offset_ms=13,
            wall_clock_ms=1_787_616_125_000,
            monotonic_ms=120_000,
        ),
        received_at_ms=1_120_000,
    )
    tracker.observe(
        observation("A02", "other", 1, 0, offset_ms=-20, monotonic_ms=5),
        received_at_ms=1_000_100,
    )

    snapshot = tracker.snapshot()
    assert snapshot["stream_count"] == 2
    assert snapshot["clock_jump_count"] == 1
    assert snapshot["streams"]["A01:s1"]["clock_drift_ms_per_min"] == 1.5
    assert snapshot["monotonic_comparison_scope"] == (
        "same_device_process_session_only"
    )


def test_backend_restart_reset_clears_all_best_effort_shadow_state() -> None:
    registry = ObservationShadowRegistry()
    clock = ObservationClockQualityTracker()
    pipeline = ShadowTrackingPipeline(schedule_timers=False)
    item = observation("A01", "s1", 1, 0)
    try:
        registry.ingest(item)
        clock.observe(item, received_at_ms=1_000_000)
        pipeline.accept(item, arrival_time_ms=0)
        assert pipeline.snapshot()["track_point_count"] == 1

        registry.reset()
        clock.reset()
        pipeline.reset()

        assert registry.metrics()["current_entries"] == 0
        assert clock.snapshot()["sample_count"] == 0
        assert pipeline.snapshot()["track_point_count"] == 0
    finally:
        pipeline.mailbox.close()


def test_http_field_metrics_include_body_bytes_and_reconciliation(monkeypatch) -> None:
    monkeypatch.setenv("UPLOAD_TOKEN", "shadow-token")
    monkeypatch.setattr(main, "OBSERVATION_SHADOW_ENABLED", True)
    monkeypatch.setattr(main, "OBSERVATION_TRACKING_ENABLED", True)
    main.observation_shadow_registry.reset()
    main.observation_shadow_tracking.reset()
    main.observation_clock_quality.reset()

    class ImmediateExecutor:
        def submit(self, function, *args, **kwargs):
            return function(*args, **kwargs)

    monkeypatch.setattr(main, "observation_shadow_executor", ImmediateExecutor())
    client = TestClient(main.app)
    now = datetime.now(timezone.utc)
    payload = observation(
        "A01",
        "s1",
        1,
        int(now.timestamp() * 1000),
    ).model_dump()
    payload["observed_at"] = now.isoformat()
    response = client.post(
        "/observations/shadow",
        headers={"x-upload-token": "shadow-token"},
        json=payload,
    )

    assert response.status_code == 202
    assert response.json()["payload_bytes"] > 0
    metrics = client.get(
        "/observations/shadow/metrics",
        headers={"x-upload-token": "shadow-token"},
    ).json()
    assert metrics["ingest"]["request_payload_bytes"] > 0
    assert metrics["reconciliation"]["backend_received_count"] == 1
    assert metrics["reconciliation"]["sequence_gate_count"] == 1
    assert metrics["reconciliation"]["backend_to_tracking_delivery_percent"] == 100
