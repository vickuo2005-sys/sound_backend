from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

import main
from services.observation_shadow import ObservationShadowRegistry, ShadowObservation


def observation_payload(
    *,
    observation_id: str = "obs-A01-process-1-1",
    sequence: int = 1,
    event_time_ms: int | None = None,
) -> dict:
    effective_event_time_ms = event_time_ms or int(
        datetime.now(timezone.utc).timestamp() * 1000
    )
    return {
        "message_type": "observation.v1",
        "schema_version": 1,
        "observation_id": observation_id,
        "device_id": "A01",
        "observed_at": datetime.fromtimestamp(
            effective_event_time_ms / 1000.0,
            tz=timezone.utc,
        ).isoformat(),
        "event_time_ms": effective_event_time_ms,
        "sequence": sequence,
        "process_session_id": "process-1",
        "label": "drone",
        "confidence": 0.91,
        "aircraft_probability": 0.02,
        "rms_peak": 0.5,
        "avg_rms": 0.3,
        "estimated_peak_db": 78.0,
        "estimated_avg_db": 74.0,
        "location": {
            "source": "cached_device_gps",
            "latitude": 25.033,
            "longitude": 121.565,
            "accuracy_m": 8.0,
        },
        "model_id": "v1_1_0_flower_drone_audio",
        "model_name": "V1.1.0",
        "ai_inference_time_ms": 42,
        "window_duration_ms": 3000,
        "hop_duration_ms": 1500,
        "sample_rate_hz": 16000,
        "alert_candidate": True,
        "trace_id": observation_id,
    }


def prepare_shadow(monkeypatch, *, tracking: bool = False) -> TestClient:
    monkeypatch.setenv("UPLOAD_TOKEN", "shadow-token")
    monkeypatch.setattr(main, "OBSERVATION_SHADOW_ENABLED", True)
    monkeypatch.setattr(main, "OBSERVATION_TRACKING_ENABLED", tracking)
    main.observation_shadow_registry.reset()
    main.observation_shadow_tracking.reset()
    return TestClient(main.app)


def test_feature_flag_off_restores_v22_behavior(monkeypatch) -> None:
    monkeypatch.setenv("UPLOAD_TOKEN", "shadow-token")
    monkeypatch.setattr(main, "OBSERVATION_SHADOW_ENABLED", False)
    main.observation_shadow_registry.reset()

    response = TestClient(main.app).post(
        "/observations/shadow",
        headers={"x-upload-token": "shadow-token"},
        json=observation_payload(),
    )

    assert response.status_code == 404
    assert main.observation_shadow_registry.metrics()["observation_received_count"] == 0


def test_shadow_ingest_is_idempotent_and_does_not_alert_or_write_event_db(
    monkeypatch,
) -> None:
    client = prepare_shadow(monkeypatch)
    monkeypatch.setattr(
        main,
        "schedule_dashboard_broadcast",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("shadow path must not broadcast")
        ),
    )
    monkeypatch.setattr(
        main,
        "save_event_with_inserted",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("shadow path must not write events")
        ),
    )

    first = client.post(
        "/observations/shadow",
        headers={"x-upload-token": "shadow-token"},
        json=observation_payload(),
    )
    duplicate = client.post(
        "/observations/shadow",
        headers={"x-upload-token": "shadow-token"},
        json=observation_payload(),
    )

    assert first.status_code == 202
    assert first.json()["dashboard_alert_created"] is False
    assert first.json()["tracking_scheduled"] is False
    assert duplicate.status_code == 202
    assert duplicate.json()["duplicate"] is True
    metrics = main.observation_shadow_registry.metrics()
    assert metrics["observation_received_count"] == 2
    assert metrics["observation_uploaded_count"] == 1
    assert metrics["duplicate_observation_count"] == 1


def test_sequence_gap_and_out_of_order_fill_are_measured(monkeypatch) -> None:
    client = prepare_shadow(monkeypatch)
    headers = {"x-upload-token": "shadow-token"}

    for observation_id, sequence in [("obs-1", 1), ("obs-3", 3), ("obs-2", 2)]:
        response = client.post(
            "/observations/shadow",
            headers=headers,
            json=observation_payload(
                observation_id=observation_id,
                sequence=sequence,
                event_time_ms=sequence * 1500,
            ),
        )
        assert response.status_code == 202

    metrics = main.observation_shadow_registry.metrics()
    assert metrics["sequence_gap_count"] == 1
    assert metrics["sequence_gap_filled_count"] == 1
    assert metrics["sequence_out_of_order_count"] == 1
    assert metrics["open_sequence_gap_count"] == 0


def test_shadow_schema_rejects_audio_metadata(monkeypatch) -> None:
    client = prepare_shadow(monkeypatch)
    payload = observation_payload()
    payload["audio_path"] = "gs://must-not-upload/audio.mp3"

    response = client.post(
        "/observations/shadow",
        headers={"x-upload-token": "shadow-token"},
        json=payload,
    )

    assert response.status_code == 422
    assert main.observation_shadow_registry.metrics()["observation_received_count"] == 0


def test_shadow_tracking_is_scheduled_on_independent_executor(monkeypatch) -> None:
    client = prepare_shadow(monkeypatch, tracking=True)
    submitted = []

    class ImmediateExecutor:
        def submit(self, function, *args, **kwargs):
            submitted.append((function, args, kwargs))
            return function(*args, **kwargs)

    monkeypatch.setattr(main, "observation_shadow_executor", ImmediateExecutor())
    response = client.post(
        "/observations/shadow",
        headers={"x-upload-token": "shadow-token"},
        json=observation_payload(),
    )

    assert response.status_code == 202
    assert response.json()["tracking_scheduled"] is True
    assert len(submitted) == 1
    snapshot = main.observation_shadow_tracking.snapshot()
    assert snapshot["tracking_measurement_count"] == 1
    assert snapshot["track_point_count"] == 1


def test_shadow_tracking_measures_late_event_time_and_coordinate_outlier(
    monkeypatch,
) -> None:
    client = prepare_shadow(monkeypatch, tracking=True)

    class ImmediateExecutor:
        def submit(self, function, *args, **kwargs):
            return function(*args, **kwargs)

    monkeypatch.setattr(main, "observation_shadow_executor", ImmediateExecutor())
    headers = {"x-upload-token": "shadow-token"}
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    first = observation_payload(
        observation_id="obs-1",
        sequence=1,
        event_time_ms=now_ms,
    )
    late = observation_payload(
        observation_id="obs-2",
        sequence=2,
        event_time_ms=now_ms - 1500,
    )
    outlier = observation_payload(
        observation_id="obs-3",
        sequence=3,
        event_time_ms=now_ms + 1500,
    )
    outlier["location"] = {
        "source": "unavailable",
        "latitude": None,
        "longitude": None,
        "accuracy_m": None,
    }

    for payload in (first, late, outlier):
        assert (
            client.post(
                "/observations/shadow",
                headers=headers,
                json=payload,
            ).status_code
            == 202
        )

    snapshot = main.observation_shadow_tracking.snapshot()
    assert snapshot["track_point_count"] == 1
    assert snapshot["late_discard_count"] == 1
    assert snapshot["outlier_discard_count"] == 1


def test_same_observation_id_retried_five_times_tracks_once(monkeypatch) -> None:
    client = prepare_shadow(monkeypatch, tracking=True)

    class ImmediateExecutor:
        def submit(self, function, *args, **kwargs):
            return function(*args, **kwargs)

    monkeypatch.setattr(main, "observation_shadow_executor", ImmediateExecutor())
    payload = observation_payload()
    responses = [
        client.post(
            "/observations/shadow",
            headers={"x-upload-token": "shadow-token"},
            json=payload,
        )
        for _ in range(5)
    ]

    assert all(response.status_code == 202 for response in responses)
    assert [response.json()["duplicate"] for response in responses] == [
        False,
        True,
        True,
        True,
        True,
    ]
    metrics = main.observation_shadow_registry.metrics()
    tracking = main.observation_shadow_tracking.snapshot()
    assert metrics["observation_received_count"] == 5
    assert metrics["observation_uploaded_count"] == 1
    assert metrics["duplicate_observation_count"] == 4
    assert tracking["tracking_measurement_count"] == 1
    assert tracking["track_point_count"] == 1


def test_late_recoverable_observation_keeps_event_time_and_tracks(monkeypatch) -> None:
    client = prepare_shadow(monkeypatch, tracking=True)
    monkeypatch.setattr(main, "OBSERVATION_LIVE_MAX_AGE_MS", 5_000.0)
    monkeypatch.setattr(main, "OBSERVATION_LIVE_TRACKING_MAX_AGE_MS", 120_000.0)
    monkeypatch.setattr(main, "OBSERVATION_HISTORICAL_MAX_AGE_MS", 21_600_000.0)

    class ImmediateExecutor:
        def submit(self, function, *args, **kwargs):
            return function(*args, **kwargs)

    monkeypatch.setattr(main, "observation_shadow_executor", ImmediateExecutor())
    event_time_ms = int(datetime.now(timezone.utc).timestamp() * 1000) - 30_000
    response = client.post(
        "/observations/shadow",
        headers={"x-upload-token": "shadow-token"},
        json=observation_payload(event_time_ms=event_time_ms),
    )

    assert response.status_code == 202
    body = response.json()
    assert body["event_time_ms"] == event_time_ms
    assert body["age_classification"] == "late-but-recoverable"
    assert body["tracking_eligible"] is True
    assert body["tracking_scheduled"] is True
    assert main.observation_shadow_tracking.snapshot()["track_point_count"] == 1


def test_historical_only_replay_is_retained_but_does_not_touch_live_track(
    monkeypatch,
) -> None:
    client = prepare_shadow(monkeypatch, tracking=True)
    monkeypatch.setattr(main, "OBSERVATION_LIVE_MAX_AGE_MS", 5_000.0)
    monkeypatch.setattr(main, "OBSERVATION_LIVE_TRACKING_MAX_AGE_MS", 120_000.0)
    monkeypatch.setattr(main, "OBSERVATION_HISTORICAL_MAX_AGE_MS", 21_600_000.0)

    class ImmediateExecutor:
        def submit(self, function, *args, **kwargs):
            return function(*args, **kwargs)

    monkeypatch.setattr(main, "observation_shadow_executor", ImmediateExecutor())
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    live = observation_payload(
        observation_id="obs-live-1",
        sequence=1,
        event_time_ms=now_ms,
    )
    old = observation_payload(
        observation_id="obs-old-2",
        sequence=2,
        event_time_ms=now_ms - 180_000,
    )

    live_response = client.post(
        "/observations/shadow",
        headers={"x-upload-token": "shadow-token"},
        json=live,
    )
    old_response = client.post(
        "/observations/shadow",
        headers={"x-upload-token": "shadow-token"},
        json=old,
    )

    assert live_response.json()["tracking_scheduled"] is True
    assert old_response.json()["age_classification"] == "historical-only"
    assert old_response.json()["tracking_scheduled"] is False
    metrics = main.observation_shadow_registry.metrics()
    tracking = main.observation_shadow_tracking.snapshot()
    assert metrics["observation_uploaded_count"] == 2
    assert metrics["replay_historical_only_count"] == 1
    assert metrics["tracking_historical_suppressed_count"] == 1
    assert tracking["track_point_count"] == 1


def test_expired_replay_is_counted_and_never_scheduled_for_tracking(
    monkeypatch,
) -> None:
    client = prepare_shadow(monkeypatch, tracking=True)
    monkeypatch.setattr(main, "OBSERVATION_LIVE_MAX_AGE_MS", 5_000.0)
    monkeypatch.setattr(main, "OBSERVATION_LIVE_TRACKING_MAX_AGE_MS", 120_000.0)
    monkeypatch.setattr(main, "OBSERVATION_HISTORICAL_MAX_AGE_MS", 600_000.0)
    event_time_ms = int(datetime.now(timezone.utc).timestamp() * 1000) - 900_000

    response = client.post(
        "/observations/shadow",
        headers={"x-upload-token": "shadow-token"},
        json=observation_payload(event_time_ms=event_time_ms),
    )

    assert response.status_code == 202
    assert response.json()["age_classification"] == "expired"
    assert response.json()["tracking_eligible"] is False
    assert response.json()["tracking_scheduled"] is False
    metrics = main.observation_shadow_registry.metrics()
    assert metrics["replay_expired_count"] == 1
    assert metrics["tracking_expired_suppressed_count"] == 1
    assert main.observation_shadow_tracking.snapshot()["track_point_count"] == 0


def test_idempotency_tombstone_outlives_short_record_retention() -> None:
    registry = ObservationShadowRegistry(
        max_observations=10,
        ttl_seconds=1,
        max_streams=2,
        dedup_ttl_seconds=60,
        max_dedup_ids=20,
    )
    accepted_at = datetime(2026, 8, 25, tzinfo=timezone.utc)
    observation = ShadowObservation.model_validate(observation_payload())

    first = registry.ingest(observation, received_at=accepted_at)
    registry.cleanup_expired(now=accepted_at + timedelta(seconds=2))
    duplicate = registry.ingest(
        observation,
        received_at=accepted_at + timedelta(seconds=2),
    )

    assert first.accepted is True
    assert duplicate.duplicate is True
    metrics = registry.metrics()
    assert metrics["current_entries"] == 0
    assert metrics["idempotency_tombstone_count"] == 1
    assert metrics["duplicate_observation_count"] == 1


def test_shadow_metrics_exposes_control_and_shadow_without_dashboard_side_effect(
    monkeypatch,
) -> None:
    client = prepare_shadow(monkeypatch)
    response = client.get(
        "/observations/shadow/metrics",
        headers={"x-upload-token": "shadow-token"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["feature_flags"]["observation_shadow_enabled"] is True
    assert "ingest" in body
    assert "shadow_tracking" in body
    assert "control_tracking" in body
