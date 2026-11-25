from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

import main
from services.classification import (
    CANONICAL_LABELS,
    ClassificationMetadata,
    normalize_classification,
)


def classification_payload(**overrides) -> dict:
    payload = {
        "schema_version": "classification.v1",
        "model_id": "v1_1_0_flower_drone_audio",
        "model_version": "1.1.0",
        "model_label": "Drone",
        "confidence": 0.92,
        "class_scores": {
            "Airplane": 0.03,
            "Car": 0.02,
            "Drone": 0.92,
            "Electric_saw": 0.01,
            "Rainfall": 0.02,
        },
        # Deliberately inconsistent App policy fields exercise the trust boundary.
        "operational_class": "aircraft",
        "aircraft_probability": 0.03,
        "is_target": False,
        "drone_subtype": None,
    }
    payload.update(overrides)
    return payload


def event_payload(event_id: str, *, classification: dict | None = None) -> dict:
    payload = {
        "event_id": event_id,
        "device_id": "node_A01",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "label": "drone",
    }
    if classification is not None:
        payload["classification"] = classification
    return payload


def observation_payload(
    observation_id: str,
    *,
    classification: dict | None = None,
) -> dict:
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    payload = {
        "message_type": "observation.v1",
        "schema_version": 1,
        "observation_id": observation_id,
        "device_id": "A01",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "event_time_ms": now_ms,
        "sequence": 1,
        "process_session_id": "process-bi1",
        "label": "drone",
        "confidence": 0.92,
        "aircraft_probability": 0.95,
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
    if classification is not None:
        payload["classification"] = classification
    return payload


def fake_initial_submission(event: main.SoundEvent) -> dict:
    created_at = main.current_time_iso()
    return {
        "db_id": 101,
        "device_row": {
            "device_id": event.device_id,
            "last_event_at": created_at,
            "is_listening": True,
        },
        "is_existing_event": False,
        "saved_event": main.fast_saved_event_payload(event, 101, created_at),
        "created_at": created_at,
        "db_duration_ms": 1.0,
        "fixed_location_duration_ms": 0.0,
        "fixed_location_cache_stale": False,
    }


def prepare_event_client(monkeypatch) -> TestClient:
    monkeypatch.setenv("UPLOAD_TOKEN", "classification-token")
    monkeypatch.setattr(main, "process_event_initial_submission", fake_initial_submission)
    monkeypatch.setattr(main, "schedule_device_event_status_update", lambda event: None)
    monkeypatch.setattr(main, "schedule_event_post_ingest", lambda *args: None)
    return TestClient(main.app)


def test_old_and_new_events_are_both_accepted(monkeypatch) -> None:
    client = prepare_event_client(monkeypatch)

    old_response = client.post(
        "/events",
        headers={"x-upload-token": "classification-token"},
        json=event_payload("legacy-event"),
    )
    new_response = client.post(
        "/events",
        headers={"x-upload-token": "classification-token"},
        json=event_payload("classified-event", classification=classification_payload()),
    )

    assert old_response.status_code == 200
    assert new_response.status_code == 200


def test_server_rebuilds_operational_decision_from_scores() -> None:
    parsed = ClassificationMetadata.model_validate(classification_payload())
    normalized = normalize_classification(parsed)

    assert normalized is not None
    assert normalized.model_label == "Drone"
    assert normalized.operational_class == "drone"
    assert normalized.aircraft_probability == pytest.approx(0.95)
    assert normalized.is_target is True
    assert normalized.drone_subtype is None
    assert tuple(normalized.class_scores) == CANONICAL_LABELS


def test_invalid_model_label_and_score_keys_are_rejected(monkeypatch) -> None:
    client = prepare_event_client(monkeypatch)
    invalid_label = classification_payload(model_label="Car")
    invalid_scores = classification_payload()
    invalid_scores["class_scores"] = {
        **invalid_scores["class_scores"],
        "rain": invalid_scores["class_scores"]["Rainfall"],
    }
    invalid_scores["class_scores"].pop("Rainfall")

    label_response = client.post(
        "/events",
        headers={"x-upload-token": "classification-token"},
        json=event_payload("invalid-label", classification=invalid_label),
    )
    scores_response = client.post(
        "/events",
        headers={"x-upload-token": "classification-token"},
        json=event_payload("invalid-scores", classification=invalid_scores),
    )

    assert label_response.status_code == 422
    assert scores_response.status_code == 422


@pytest.mark.parametrize("invalid_score", ["NaN", "Infinity", "-Infinity"])
def test_non_finite_class_score_is_rejected_without_server_error(
    monkeypatch, invalid_score: str
) -> None:
    client = prepare_event_client(monkeypatch)
    payload = event_payload(
        f"invalid-{invalid_score}", classification=classification_payload()
    )
    encoded = json.dumps(payload, separators=(",", ":")).replace(
        '"Drone":0.92', f'"Drone":{invalid_score}'
    )

    response = client.post(
        "/events",
        headers={
            "x-upload-token": "classification-token",
            "content-type": "application/json",
        },
        content=encoded,
    )

    assert response.status_code == 422


def test_old_and_new_observations_are_accepted_and_identity_is_unchanged(
    monkeypatch,
) -> None:
    monkeypatch.setenv("UPLOAD_TOKEN", "classification-token")
    monkeypatch.setattr(main, "OBSERVATION_SHADOW_ENABLED", True)
    monkeypatch.setattr(main, "OBSERVATION_TRACKING_ENABLED", False)
    main.observation_shadow_registry.reset()
    client = TestClient(main.app)

    old = client.post(
        "/observations/shadow",
        headers={"x-upload-token": "classification-token"},
        json=observation_payload("legacy-observation"),
    )
    new_payload = observation_payload(
        "classified-observation",
        classification=classification_payload(),
    )
    new = client.post(
        "/observations/shadow",
        headers={"x-upload-token": "classification-token"},
        json=new_payload,
    )

    assert old.status_code == 202
    assert new.status_code == 202
    assert new.json()["observation_id"] == new_payload["observation_id"]
    assert new.json()["event_time_ms"] == new_payload["event_time_ms"]
    record = main.observation_shadow_registry.record("classified-observation")
    assert record is not None
    assert record["classification"]["operational_class"] == "drone"
    assert record["classification"]["class_scores"] == classification_payload()[
        "class_scores"
    ]


def test_duplicate_offline_replay_retains_one_classification_record(monkeypatch) -> None:
    monkeypatch.setenv("UPLOAD_TOKEN", "classification-token")
    monkeypatch.setattr(main, "OBSERVATION_SHADOW_ENABLED", True)
    monkeypatch.setattr(main, "OBSERVATION_TRACKING_ENABLED", False)
    main.observation_shadow_registry.reset()
    client = TestClient(main.app)
    payload = observation_payload("offline-replay", classification=classification_payload())

    responses = [
        client.post(
            "/observations/shadow",
            headers={"x-upload-token": "classification-token"},
            json=payload,
        )
        for _ in range(2)
    ]

    assert [response.json()["duplicate"] for response in responses] == [False, True]
    metrics = main.observation_shadow_registry.metrics()
    assert metrics["retained_observation_count"] == 1
    assert metrics["observation_uploaded_count"] == 1
    assert main.observation_shadow_registry.record("offline-replay")["classification"]


def test_websocket_extension_is_flagged_and_legacy_fields_remain(monkeypatch) -> None:
    client = prepare_event_client(monkeypatch)
    broadcasts: list[dict] = []
    monkeypatch.setattr(
        main,
        "schedule_dashboard_broadcast",
        lambda message, context="dashboard": broadcasts.append(message),
    )
    monkeypatch.setattr(main, "CLASSIFICATION_V1_ENABLED", True)
    monkeypatch.setattr(main, "CLASSIFICATION_V1_WEBSOCKET_ENABLED", False)

    response = client.post(
        "/events",
        headers={"x-upload-token": "classification-token"},
        json=event_payload("legacy-ws", classification=classification_payload()),
    )

    assert response.status_code == 200
    trigger = broadcasts[0]
    assert trigger["type"] == "event_trigger"
    assert trigger["label"] == "drone"
    assert "classification" not in trigger

    broadcasts.clear()
    monkeypatch.setattr(main, "CLASSIFICATION_V1_WEBSOCKET_ENABLED", True)
    response = client.post(
        "/events",
        headers={"x-upload-token": "classification-token"},
        json=event_payload("classified-ws", classification=classification_payload()),
    )

    assert response.status_code == 200
    assert broadcasts[0]["label"] == "drone"
    assert broadcasts[0]["classification"]["model_label"] == "Drone"
    assert broadcasts[0]["classification"]["operational_class"] == "drone"


def test_sqlite_event_persistence_preserves_all_five_scores(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(main, "DB_NAME", str(tmp_path / "classification.db"))
    monkeypatch.setattr(main, "CLASSIFICATION_V1_PERSISTENCE_ENABLED", True)
    main.init_sqlite_db()
    event = main.SoundEvent.model_validate(
        event_payload("sqlite-event", classification=classification_payload())
    )
    event.classification = normalize_classification(event.classification)

    _db_id, inserted = main.save_event_with_inserted(event, main.current_time_iso())
    with main.get_sqlite_connection() as connection:
        row = dict(
            connection.execute(
                "SELECT * FROM events WHERE event_id = ?", ("sqlite-event",)
            ).fetchone()
        )

    assert inserted is True
    assert row["model_label"] == "Drone"
    assert row["operational_class"] == "drone"
    assert json.loads(row["class_scores_json"]) == classification_payload()[
        "class_scores"
    ]

    legacy_refresh = main.SoundEvent.model_validate(event_payload("sqlite-event"))
    _db_id, inserted = main.save_event_with_inserted(
        legacy_refresh, main.current_time_iso()
    )
    with main.get_sqlite_connection() as connection:
        refreshed = dict(
            connection.execute(
                "SELECT * FROM events WHERE event_id = ?", ("sqlite-event",)
            ).fetchone()
        )

    assert inserted is False
    assert refreshed["model_label"] == "Drone"
    assert json.loads(refreshed["class_scores_json"])["Drone"] == 0.92


def test_postgres_repository_sql_includes_structured_classification(monkeypatch) -> None:
    captured: dict = {}

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def execute(self, query, params):
            captured["query"] = query
            captured["params"] = params

        def fetchone(self):
            return {"id": 9, "inserted": True}

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def cursor(self):
            return Cursor()

        def close(self):
            return None

    monkeypatch.setattr(main, "CLASSIFICATION_V1_PERSISTENCE_ENABLED", True)
    monkeypatch.setattr(main, "get_postgres_connection", lambda: Connection())
    event = main.SoundEvent.model_validate(
        event_payload("postgres-event", classification=classification_payload())
    )
    event.classification = normalize_classification(event.classification)

    db_id, inserted = main.upsert_event_postgres_with_inserted(
        event, main.current_time_iso()
    )
    columns = main.event_write_columns()
    params = dict(zip(columns, captured["params"]))

    assert db_id == 9
    assert inserted is True
    assert "model_label" in captured["query"]
    assert params["model_label"] == "Drone"
    assert json.loads(params["class_scores_json"])["Drone"] == 0.92
