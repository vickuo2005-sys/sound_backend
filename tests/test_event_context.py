from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

import main
from services.event_fusion import get_event_group_for_event, list_event_groups, process_event
from tools.test_event_fusion import make_connection


def test_context_resolves_old_event_by_persisted_id_without_writing():
    connection = make_connection()
    base = datetime(2026, 7, 27, tzinfo=timezone.utc)
    first_group = None
    for index in range(23):
        event = {
            "event_id": f"event-{index}", "device_id": "node_A01", "label": "drone",
            "timestamp": (base + timedelta(minutes=5 * index)).isoformat(),
            "latitude": 25.0, "longitude": 121.0, "rms_peak": 0.8,
        }
        group = process_event(connection, event, is_postgres=False)
        if index == 0:
            first_group = group
    recent = list_event_groups(connection, is_postgres=False, limit=20)
    assert first_group["id"] not in {group["id"] for group in recent}
    changes_before = connection.total_changes
    result = get_event_group_for_event(connection, "event-0", False)
    assert result["id"] == first_group["id"]
    assert result["devices"] == ["node_A01"]
    assert result["first_event_time"] == first_group["first_event_time"]
    assert result["node_evidence"][0]["event_id"] == "event-0"
    assert result["node_evidence"][0]["latitude"] == 25.0
    assert result["node_evidence_truncated"] is False
    # Never guess an association from another event on the same node.
    assert get_event_group_for_event(connection, "event-missing", False) is None
    assert connection.total_changes == changes_before
    connection.close()


@pytest.mark.parametrize("group", [None, {"id": "old-group", "devices": ["A01", "A02"]}])
def test_context_api_preserves_event_coordinates_and_explicit_association(monkeypatch, group):
    event = {"event_id": "event-old", "raw_latitude": 25.0, "raw_longitude": 121.0,
             "fixed_latitude": 26.0, "fixed_longitude": 122.0, "effective_location_source": "fixed"}
    monkeypatch.setattr(main, "get_event_by_event_id", lambda event_id: event)
    queried = []

    def lookup(event_id):
        queried.append(event_id)
        return group

    monkeypatch.setattr(main, "get_event_fusion_context", lookup)
    response = TestClient(main.app).get("/events/event-old/context")
    assert response.status_code == 200
    data = response.json()
    assert queried == ["event-old"]
    assert data["group"] == group
    assert data["association_status"] == ("associated" if group else "not_associated")
    assert data["event"]["raw_latitude"] == 25.0
    assert data["event"]["fixed_latitude"] == 26.0


def test_context_unknown_event_returns_404_without_group_lookup(monkeypatch):
    monkeypatch.setattr(main, "get_event_by_event_id", lambda event_id: None)
    monkeypatch.setattr(main, "get_event_fusion_context", lambda event_id: pytest.fail("unexpected lookup"))
    assert TestClient(main.app).get("/events/unknown/context").status_code == 404


def test_context_database_failure_is_not_reported_as_no_group(monkeypatch):
    monkeypatch.setattr(main, "get_event_by_event_id", lambda event_id: {"event_id": event_id})

    def unavailable(event_id):
        raise RuntimeError("private database diagnostic")

    monkeypatch.setattr(main, "get_event_fusion_context", unavailable)
    response = TestClient(main.app).get("/events/event-old/context")
    assert response.status_code == 503
    assert "private database diagnostic" not in response.text
    assert "group" not in response.json()


def test_node_evidence_uses_first_observation_per_node_and_stored_coordinates():
    connection = make_connection()
    for index, node in enumerate(["node_A01", "node_A02", "node_A01"]):
        process_event(connection, {
            "event_id": f"evidence-{index}", "device_id": node, "label": "drone",
            "timestamp": f"2026-09-01T00:00:0{index}+00:00",
            "latitude": 25.0, "longitude": 121.0, "rms_peak": 0.8,
            "time_sync_quality": "good", "time_sync_offset_ms": index,
            "time_sync_rtt_ms": 10 + index,
        }, is_postgres=False)
    # A later persisted snapshot must not overwrite the first evidence for the node.
    connection.execute("UPDATE event_group_observations SET latitude=26 WHERE event_id='evidence-2'")
    changes_before = connection.total_changes
    result = get_event_group_for_event(connection, "evidence-2", False)
    evidence = result["node_evidence"]
    assert [item["event_id"] for item in evidence] == ["evidence-0", "evidence-1"]
    assert evidence[0]["latitude"] == 25
    assert evidence[0]["time_sync_offset_ms"] == 0
    assert evidence[1]["time_sync_rtt_ms"] == 11
    assert evidence[0]["created_at"]
    assert connection.total_changes == changes_before
    connection.close()
