import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

import main
from services.telemetry_v1 import LatestTelemetry, TelemetryV1

AUTH = {"x-upload-token": "telemetry-unit-test"}
DEVICE = "node_telemetry_unit"


def packet(sequence=1, **fields):
    return {
        "version": 1,
        "device_id": DEVICE,
        "sequence": sequence,
        "gps_time_ms": None,
        "latitude": None,
        "longitude": None,
        "detected": False,
        "event_id": None,
        "event_time_ms": None,
        "label": None,
        "confidence": None,
        "battery": None,
        **fields,
    }


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("UPLOAD_TOKEN", AUTH["x-upload-token"])
    monkeypatch.setattr(main, "DB_NAME", str(tmp_path / "telemetry.db"))
    monkeypatch.setattr(main, "latest_telemetry", LatestTelemetry())
    monkeypatch.setattr(main, "schedule_event_post_ingest", lambda *args: None)
    monkeypatch.setattr(main, "schedule_device_event_status_update", lambda *args: None)
    main.init_sqlite_db()
    return TestClient(main.app)


@pytest.mark.parametrize("fields", [
    {"version": True},
    {"sequence": 0},
    {"battery": 101},
    {"latitude": 25},
    {"gps_time_ms": 1794650400000},
    {"detected": True},
    {"event_id": "wrong"},
    {"extra": 1},
])
def test_contract_rejects_invalid_fields(fields):
    with pytest.raises(ValidationError):
        TelemetryV1.model_validate({**packet(), **fields})


def test_http_and_websocket_share_exact_contract_and_latest_status(client):
    assert client.post("/telemetry/v1", json=packet()).status_code == 401
    first = packet(battery=85)
    assert client.post("/telemetry/v1", json=first, headers=AUTH).json()["sequence"] == 1
    newer = packet(3, gps_time_ms=1794650400000, latitude=25.0478, longitude=121.5170, battery=84)
    with client.websocket_connect("/ws/telemetry/v1", headers=AUTH) as socket:
        socket.send_json({**packet(), "version": 2})
        assert socket.receive_json() == {"status": "rejected", "code": 422}
        socket.send_json(newer)
        assert socket.receive_json()["sequence"] == 3
    assert client.post("/telemetry/v1", json=packet(2), headers=AUTH).status_code == 200
    assert client.get(f"/telemetry/v1/latest/{DEVICE}", headers=AUTH).json() == newer
    devices = client.get("/device-status").json()["devices"]
    assert next(device for device in devices if device["device_id"] == DEVICE)["telemetry_sequence"] == 3


def test_replayed_event_never_replaces_full_metadata(client):
    event = packet(2, detected=True, event_id="telemetry-unit-event",
                   event_time_ms=1794650399500, label="drone", confidence=0.93)
    with client.websocket_connect("/ws/telemetry/v1", headers=AUTH) as socket:
        socket.send_json(event)
        assert socket.receive_json()["event_id"] == event["event_id"]
    assert client.post("/events", headers=AUTH, json={
        "event_id": event["event_id"],
        "device_id": DEVICE,
        "timestamp": "2026-11-14T12:00:00+00:00",
        "label": "drone",
        "audio_path": "telemetry-test.mp3",
        "duration_s": 3,
    }).status_code == 200
    assert client.post("/telemetry/v1", json=event, headers=AUTH).status_code == 200
    with main.get_sqlite_connection() as connection:
        rows = connection.execute(
            "SELECT audio_path, duration_s FROM events WHERE event_id = ?",
            (event["event_id"],),
        ).fetchall()
    assert [(row["audio_path"], row["duration_s"]) for row in rows] == [("telemetry-test.mp3", 3)]


def test_recent_telemetry_protects_a_node_from_removal(client, monkeypatch):
    monkeypatch.setenv("DASHBOARD_ADMIN_TOKEN", "telemetry-admin-unit-test")
    assert client.post("/telemetry/v1", json=packet(), headers=AUTH).status_code == 200

    response = client.delete(
        f"/device-status/{DEVICE}",
        headers={"x-upload-token": "telemetry-admin-unit-test"},
    )

    assert response.status_code == 409
    assert client.get(f"/telemetry/v1/latest/{DEVICE}", headers=AUTH).status_code == 200
