from fastapi.testclient import TestClient

import main
from services.dashboard_payloads import (
    CANONICAL_CLASS_LABELS,
    serialize_event_for_dashboard,
    serialize_node_for_dashboard,
    serialize_track_for_dashboard,
)
from services.dashboard_v2_4 import render_dashboard_v2_4


def classification_payload(*, label: str = "Drone", target: bool = True) -> dict:
    return {
        "schema_version": "classification.v1",
        "model_id": "sounddetector-five-class",
        "model_version": "1",
        "model_label": label,
        "confidence": 0.6087,
        "class_scores": {
            "Car": 0.0,
            "Drone": 0.6087,
            "Airplane": 0.0002,
            "Rainfall": 0.0246,
            "Electric_saw": 0.3665,
        },
        "operational_class": "drone" if target else "non_aircraft",
        "is_target": target,
        "aircraft_probability": 0.6089 if target else 0.0,
        "drone_subtype": None,
    }


def test_dashboard_flag_off_returns_legacy(monkeypatch) -> None:
    monkeypatch.setattr(main, "DASHBOARD_V2_ENABLED", False)

    html = main.dashboard().body.decode("utf-8")

    assert "聲音偵測戰情室 V4.0" in html
    assert "Operational Intelligence" not in html


def test_dashboard_flag_on_returns_v2_4(monkeypatch) -> None:
    monkeypatch.setattr(main, "DASHBOARD_V2_ENABLED", True)

    html = main.dashboard().body.decode("utf-8")

    assert "Operational Intelligence" in html
    assert "STAGING" in html
    assert "DASHBOARD V2.4" not in html  # Product UI, not an internal version banner.
    assert "Prediction / ETA：僅模擬，未完成實地驗證" in html


def test_legacy_route_is_always_available(monkeypatch) -> None:
    monkeypatch.setattr(main, "DASHBOARD_V2_ENABLED", True)
    client = TestClient(main.app)

    response = client.get("/dashboard/legacy")

    assert response.status_code == 200
    assert "聲音偵測戰情室 V4.0" in response.text


def test_legacy_event_serializes_safely() -> None:
    event = serialize_event_for_dashboard(
        {"event_id": "legacy-1", "label": "aircraft", "audio_path": None}
    )

    presentation = event["dashboard_presentation"]
    assert event["event_id"] == "legacy-1"
    assert presentation["classification_available"] is False
    assert presentation["is_target"] is None
    assert presentation["audio_available"] is False


def test_classification_v1_serializer_preserves_transport_contract() -> None:
    classification = classification_payload()
    event = serialize_event_for_dashboard(
        {
            "event_id": "classified-1",
            "label": "drone",
            "classification": classification,
        }
    )

    assert event["classification"] == classification
    assert event["dashboard_presentation"]["model_label"] == "Drone"
    assert event["dashboard_presentation"]["operational_class"] == "drone"


def test_all_five_scores_use_canonical_transport_order() -> None:
    event = serialize_event_for_dashboard(
        {"classification": classification_payload()}
    )

    scores = event["dashboard_presentation"]["class_scores"]
    assert tuple(scores) == CANONICAL_CLASS_LABELS
    assert scores["Drone"] == 0.6087
    assert scores["Electric_saw"] == 0.3665


def test_drone_target_presentation_uses_server_normalized_policy() -> None:
    event = serialize_event_for_dashboard(
        {"classification": classification_payload(label="Drone", target=True)}
    )

    assert event["dashboard_presentation"]["is_target"] is True
    assert event["dashboard_presentation"]["name_zh"] == "無人機聲音"


def test_non_target_presentation_does_not_recalculate_policy() -> None:
    classification = classification_payload(label="Car", target=False)
    classification["confidence"] = 0.91
    classification["class_scores"]["Car"] = 0.91
    event = serialize_event_for_dashboard({"classification": classification})

    assert event["dashboard_presentation"]["is_target"] is False
    assert event["dashboard_presentation"]["operational_class"] == "non_aircraft"
    assert event["dashboard_presentation"]["name_zh"] == "車輛聲音"


def test_missing_classification_and_audio_are_null_safe() -> None:
    event = serialize_event_for_dashboard(
        {"event_id": "null-safe", "classification": None, "audio_path": ""}
    )

    assert event["dashboard_presentation"]["model_score"] is None
    assert event["dashboard_presentation"]["class_scores"] == {}
    assert event["dashboard_presentation"]["audio_available"] is False


def test_node_offline_payload_is_additive_and_queue_is_not_fabricated() -> None:
    node = serialize_node_for_dashboard(
        {"device_id": "node_A02", "status": "offline", "is_listening": False}
    )

    assert node["status"] == "offline"
    assert node["is_listening"] is False
    assert node["dashboard_presentation"]["queue_source"] == "node_reported"
    assert node["dashboard_presentation"]["queue_count"] is None


def test_track_missing_and_experimental_motion_are_null_safe() -> None:
    track = serialize_track_for_dashboard(
        {"id": "track-empty", "points": []},
        experimental_motion_enabled=True,
    )

    presentation = track["dashboard_presentation"]
    assert presentation["experimental"] is True
    assert presentation["field_validated"] is False
    assert presentation["speed_mps"] is None
    assert presentation["heading_deg"] is None
    assert presentation["motion_quality"] is None


def test_motion_panel_never_exposes_prediction_or_eta(monkeypatch) -> None:
    monkeypatch.setattr(main, "DASHBOARD_V2_EXPERIMENTAL_MOTION_ENABLED", True)

    html = main.dashboard_v2_4().body.decode("utf-8")

    assert "EXPERIMENTAL" in html
    assert "未完成多節點實地驗證" in html
    assert "未提供 ETA、future path 或 threat prediction" in html
    assert "Kalman" not in html


def test_existing_websocket_event_types_are_reused() -> None:
    html = main.dashboard_v2_4().body.decode("utf-8")

    for message_type in (
        "event_trigger",
        "location_update",
        "node_heartbeat",
        "event_group",
        "track_update",
        "event_audio_update",
    ):
        assert message_type in html
    assert "/ws/dashboard" in html
    assert "data.event?.classification || data.classification" in html


def test_dashboard_ignores_unknown_websocket_fields() -> None:
    html = main.dashboard_v2_4().body.decode("utf-8")

    assert "Unknown fields and message types are intentionally ignored" in html
    assert "JSON.parse(message.data)" in html


def test_dashboard_without_maps_key_uses_real_coordinate_fallback() -> None:
    html = render_dashboard_v2_4(
        maps_api_key="", experimental_motion_enabled=False
    )

    assert "const mapsConfigured = false" in html
    assert "RELATIVE COORDINATES" in html
    assert "以真實經緯度顯示相對位置" in html
    assert "maps.googleapis.com" not in html


def test_dashboard_with_maps_key_loads_google_maps_callback() -> None:
    html = render_dashboard_v2_4(
        maps_api_key="test key", experimental_motion_enabled=False
    )

    assert "const mapsConfigured = true" in html
    assert "key=test%20key" in html
    assert "callback=initOperationalMap" in html


def test_events_api_adds_presentation_without_removing_legacy_fields(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        main,
        "list_recent_events",
        lambda limit: [
            {
                "event_id": "api-event",
                "device_id": "node_A01",
                "label": "drone",
                "classification": classification_payload(),
            }
        ],
    )

    event = main.list_events(limit=20)["events"][0]

    assert event["event_id"] == "api-event"
    assert event["device_id"] == "node_A01"
    assert event["label"] == "drone"
    assert event["classification"]["model_label"] == "Drone"
    assert event["dashboard_presentation"]["is_target"] is True
