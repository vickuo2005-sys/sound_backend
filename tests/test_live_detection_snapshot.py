from fastapi.testclient import TestClient

import main


def test_device_snapshot_preserves_live_inference_state(monkeypatch):
    node = {
        "device_id": "node_A01", "websocket_connected": True,
        "availability_status": "ONLINE", "connection_id": "session-1",
        "recording": True, "last_heartbeat_at": "2026-10-07T02:00:00Z",
        "detection_state": {"active": False, "sequence": 11, "received_at_ms": 1791338400000},
        "detection_active": False, "detection_sequence": 11,
        "detection_state_received_at_ms": 1791338400000,
    }
    monkeypatch.setattr(main.node_manager, "live_states", lambda: [node])
    monkeypatch.setattr(main, "list_device_status_rows", lambda: [{"device_id": "node_A01"}])
    monkeypatch.setattr(main, "enrich_device_status_rows", lambda rows: rows)
    monkeypatch.setattr(main, "dashboard_device_location_payloads", lambda rows: rows)
    response = TestClient(main.app).get("/device-status")
    assert response.status_code == 200
    device = response.json()["devices"][0]
    assert device["detection_state"] == node["detection_state"]
    assert device["detection_active"] is False
    assert device["detection_sequence"] == 11
    assert device["connection_id"] == "session-1"
    assert device["websocket_connected"] is True
