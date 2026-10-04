from fastapi.testclient import TestClient

import main
from services.staging_write_freeze import (
    RouteClass,
    classify_route,
    freeze_is_active,
)


def _freeze(monkeypatch, active: bool = True):
    monkeypatch.setattr(main, "APP_ENV", "staging")
    monkeypatch.setattr(main, "STAGING_WRITE_FREEZE_CONFIGURED", active)
    monkeypatch.setattr(main, "STAGING_WRITE_FREEZE_ACTIVE", active)
    return TestClient(main.app)


def test_freeze_requires_exact_staging_environment():
    assert not freeze_is_active("production", True)
    assert not freeze_is_active("development", True)
    assert not freeze_is_active("", True)
    assert freeze_is_active("staging", True)
    assert not freeze_is_active("staging", False)


def test_route_inventory_covers_side_effecting_get_and_mutations():
    assert classify_route("GET", "/events") == RouteClass.READ_ONLY
    assert classify_route("GET", "/tracks") == RouteClass.READ_ONLY
    assert classify_route("GET", "/device-command/node-1") == RouteClass.WRITE_BLOCKED_DURING_FREEZE
    assert classify_route("POST", "/events") == RouteClass.WRITE_BLOCKED_DURING_FREEZE
    assert classify_route("POST", "/upload-audio") == RouteClass.WRITE_BLOCKED_DURING_FREEZE
    assert classify_route("PUT", "/device-locations/node-1") == RouteClass.WRITE_BLOCKED_DURING_FREEZE
    assert classify_route("POST", "/diagnostics/db-latency") == RouteClass.EXEMPT_INTERNAL_IF_REQUIRED


def test_reads_remain_available_and_writes_are_blocked(monkeypatch):
    client = _freeze(monkeypatch)
    monkeypatch.setattr(main, "list_recent_events", lambda limit=50: [])
    monkeypatch.setattr(main, "list_event_fusion_groups", lambda **kwargs: [])
    monkeypatch.setattr(main, "get_tracks_cache", lambda key: {"status": "success", "tracks": []})
    monkeypatch.setattr(main, "list_device_status_rows", lambda: [])
    monkeypatch.setattr(main, "list_device_fixed_locations", lambda: [])

    assert client.get("/health").status_code == 200
    runtime = client.get("/runtime-status")
    assert runtime.status_code == 200
    assert runtime.json()["staging_write_freeze"]["active"] is True
    assert client.get("/events").status_code == 200
    assert client.get("/event-groups").status_code == 200
    assert client.get("/tracks").status_code == 200
    assert client.get("/device-status").status_code == 200
    assert client.get("/device-locations").status_code == 200

    for method, path in (
        ("post", "/events"),
        ("post", "/upload-audio"),
        ("post", "/location-update"),
        ("put", "/device-locations/node-1"),
        ("post", "/device-command"),
        ("post", "/device-command-ack"),
        ("delete", "/events/event-1"),
        ("post", "/tracks/track-1/close"),
    ):
        response = getattr(client, method)(path)
        assert response.status_code == 503, (method, path, response.text)
        assert response.json() == {"detail": "staging_write_freeze_active"}


def test_unfreeze_restores_event_write_path(monkeypatch):
    client = _freeze(monkeypatch, active=False)
    monkeypatch.setattr(main, "verify_upload_token", lambda token: None)
    monkeypatch.setattr(
        main,
        "process_event_initial_submission",
        lambda event: {
            "db_id": 99,
            "device_row": None,
            "is_existing_event": True,
            "saved_event": {},
        },
    )
    response = client.post(
        "/events",
        json={"event_id": "freeze-test", "device_id": "node-1", "timestamp": "2026-01-01T00:00:00Z"},
    )
    assert response.status_code == 200
    assert response.json()["event_id"] == "freeze-test"


def test_production_flag_cannot_activate_freeze(monkeypatch):
    monkeypatch.setattr(main, "APP_ENV", "production")
    monkeypatch.setattr(main, "STAGING_WRITE_FREEZE_CONFIGURED", True)
    monkeypatch.setattr(main, "STAGING_WRITE_FREEZE_ACTIVE", False)
    response = TestClient(main.app).post("/events")
    assert response.status_code != 503


def test_background_schedulers_do_not_accept_new_writes_when_frozen(monkeypatch):
    _freeze(monkeypatch)
    monkeypatch.setattr(
        main.asyncio,
        "get_running_loop",
        lambda: (_ for _ in ()).throw(AssertionError("scheduler should not be reached")),
    )
    event = main.SoundEvent(
        event_id="freeze-background",
        device_id="node-1",
        timestamp="2026-01-01T00:00:00Z",
    )
    main.schedule_device_event_status_update(event)
    main.schedule_event_post_ingest("freeze-background", "alert", False)
