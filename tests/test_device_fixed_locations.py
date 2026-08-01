from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

import main
from services.device_location_service import (
    DeviceLocationValidationError,
    resolve_effective_location,
    validate_device_location,
)
from services.event_fusion import process_event
from tools.test_event_fusion import make_connection


def event_record(
    event_id: str,
    device_id: str,
    label: str,
    timestamp: datetime,
    latitude=None,
    longitude=None,
) -> dict:
    return {
        "id": None,
        "event_id": event_id,
        "device_id": device_id,
        "label": label,
        "timestamp": timestamp.isoformat(),
        "created_at": timestamp.isoformat(),
        "latitude": latitude,
        "longitude": longitude,
        "rms_peak": 0.8,
    }


def insert_fixed_location(
    connection,
    device_id: str,
    latitude: float,
    longitude: float,
    source: str = "manual_map",
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    connection.execute(
        """
        INSERT INTO device_locations (
            device_id, latitude, longitude, location_source,
            accuracy_m, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, NULL, ?, ?)
        ON CONFLICT(device_id) DO UPDATE SET
            latitude = excluded.latitude,
            longitude = excluded.longitude,
            location_source = excluded.location_source,
            updated_at = excluded.updated_at
        """,
        (device_id, latitude, longitude, source, now, now),
    )
    connection.commit()


def test_validate_fixed_location_accepts_valid_manual_and_zero_coordinates() -> None:
    values = validate_device_location(
        device_id="node_A00",
        latitude=0,
        longitude=0,
        location_source="manual_map",
        accuracy_m=0,
    )

    assert values["latitude"] == 0.0
    assert values["longitude"] == 0.0
    assert values["accuracy_m"] == 0.0


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("latitude", 91),
        ("latitude", -91),
        ("latitude", float("nan")),
        ("longitude", 181),
        ("longitude", -181),
        ("longitude", float("inf")),
    ],
)
def test_validate_fixed_location_rejects_invalid_coordinates(field, value) -> None:
    kwargs = {
        "device_id": "node_A01",
        "latitude": 25.0,
        "longitude": 121.0,
        "location_source": "manual_map",
    }
    kwargs[field] = value

    with pytest.raises(DeviceLocationValidationError):
        validate_device_location(**kwargs)


def test_resolver_uses_fixed_location_before_event_gps() -> None:
    effective = resolve_effective_location(
        device_id="node_A01",
        event_latitude=25.04,
        event_longitude=121.53,
        fixed_locations={
            "node_A01": {
                "device_id": "node_A01",
                "latitude": 25.041234,
                "longitude": 121.531567,
            }
        },
    )

    assert effective["latitude"] == 25.041234
    assert effective["longitude"] == 121.531567
    assert effective["effective_location_source"] == "fixed"


def test_resolver_falls_back_to_event_gps_and_excludes_missing() -> None:
    fallback = resolve_effective_location(
        device_id="node_A01",
        event_latitude=25.04,
        event_longitude=121.53,
        fixed_locations={},
    )
    missing = resolve_effective_location(
        device_id="node_A02",
        event_latitude=None,
        event_longitude=None,
        fixed_locations={},
    )

    assert fallback["effective_location_source"] == "event_gps"
    assert fallback["latitude"] == 25.04
    assert missing is None


def test_event_fusion_fixed_location_overrides_without_mutating_raw_observation() -> None:
    connection = make_connection()
    base = datetime(2026, 7, 28, 8, 0, tzinfo=timezone.utc)
    insert_fixed_location(connection, "node_A01", 25.2, 121.2)

    group = process_event(
        connection,
        event_record("evt_a01", "node_A01", "aircraft", base, 25.0, 121.0),
        is_postgres=False,
        window_seconds=3,
    )
    raw_observation = connection.execute(
        """
        SELECT latitude, longitude
        FROM event_group_observations
        WHERE event_id = ?
        """,
        ("evt_a01",),
    ).fetchone()

    assert group["region_type"] == "single_node"
    assert group["region_center_lat"] == 25.2
    assert group["region_center_lng"] == 121.2
    assert raw_observation["latitude"] == 25.0
    assert raw_observation["longitude"] == 121.0


def test_fixed_locations_allow_gps_less_node_and_segments() -> None:
    connection = make_connection()
    base = datetime(2026, 7, 28, 8, 0, tzinfo=timezone.utc)
    insert_fixed_location(connection, "node_A01", 25.0, 121.0)
    insert_fixed_location(connection, "node_A02", 25.2, 121.4)

    group = process_event(
        connection,
        event_record("evt_a01", "node_A01", "aircraft", base),
        is_postgres=False,
        window_seconds=3,
    )
    group = process_event(
        connection,
        event_record("evt_a02", "node_A02", "aircraft", base + timedelta(seconds=1)),
        is_postgres=False,
        window_seconds=3,
    )

    assert group["region_type"] == "segment"
    assert group["reporting_node_count"] == 2
    assert group["region_center_lat"] == 25.1
    assert group["region_center_lng"] == 121.2


def test_three_fixed_nodes_and_mixed_sources_produce_polygon() -> None:
    connection = make_connection()
    base = datetime(2026, 7, 28, 8, 0, tzinfo=timezone.utc)
    insert_fixed_location(connection, "node_A01", 25.0, 121.0)
    insert_fixed_location(connection, "node_A03", 25.2, 121.0)

    group = process_event(
        connection,
        event_record("evt_a01", "node_A01", "aircraft", base, None, None),
        is_postgres=False,
        window_seconds=3,
    )
    group = process_event(
        connection,
        event_record("evt_a02", "node_A02", "aircraft", base + timedelta(seconds=1), 25.0, 121.2),
        is_postgres=False,
        window_seconds=3,
    )
    group = process_event(
        connection,
        event_record("evt_a03", "node_A03", "aircraft", base + timedelta(seconds=2), None, None),
        is_postgres=False,
        window_seconds=3,
    )

    assert group["region_type"] == "polygon"
    assert group["reporting_device_ids"] == ["node_A01", "node_A02", "node_A03"]


def test_clearing_fixed_location_returns_to_event_gps_fallback() -> None:
    connection = make_connection()
    base = datetime(2026, 7, 28, 8, 0, tzinfo=timezone.utc)
    insert_fixed_location(connection, "node_A01", 25.2, 121.2)
    first = process_event(
        connection,
        event_record("evt_a01", "node_A01", "aircraft", base, 25.0, 121.0),
        is_postgres=False,
        window_seconds=3,
    )
    connection.execute("DELETE FROM device_locations WHERE device_id = ?", ("node_A01",))
    connection.commit()
    second = process_event(
        connection,
        event_record("evt_a01_again", "node_A01", "aircraft", base + timedelta(seconds=1), 25.0, 121.0),
        is_postgres=False,
        window_seconds=3,
    )

    assert first["region_center_lat"] == 25.2
    assert second["region_center_lat"] == 25.0
    assert second["region_center_lng"] == 121.0


def test_device_location_api_crud_allows_internal_dashboard_without_token(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "fixed_locations.db"
    monkeypatch.setattr(main, "DB_NAME", str(db_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("UPLOAD_TOKEN", "secret-token")
    main.init_sqlite_db()
    client = TestClient(main.app)

    created = client.put(
        "/device-locations/node_A01",
        json={
            "latitude": 25.041234,
            "longitude": 121.531567,
            "location_source": "manual_map",
            "accuracy_m": None,
        },
    )
    assert created.status_code == 200
    assert created.json()["device_location"]["latitude"] == 25.041234

    listed = client.get("/device-locations")
    assert listed.status_code == 200
    assert listed.json()["count"] == 1

    detail = client.get("/device-locations/node_A01")
    assert detail.status_code == 200
    assert detail.json()["has_fixed_location"] is True

    status_rows = client.get("/device-status")
    assert status_rows.status_code == 200
    status_device = status_rows.json()["devices"][0]
    assert status_device["device_id"] == "node_A01"
    assert status_device["latitude"] is None
    assert status_device["longitude"] is None
    assert status_device["effective_latitude"] == 25.041234
    assert status_device["effective_longitude"] == 121.531567
    assert status_device["effective_location_source"] == "fixed"

    live_gps = client.post(
        "/location-update",
        json={
            "device_id": "node_A01",
            "latitude": 25.9,
            "longitude": 121.9,
        },
    )
    assert live_gps.status_code == 200
    updated_status = client.get("/device-status").json()["devices"][0]
    assert updated_status["latitude"] == 25.9
    assert updated_status["longitude"] == 121.9
    assert updated_status["effective_latitude"] == 25.041234
    assert updated_status["effective_longitude"] == 121.531567
    assert updated_status["effective_location_source"] == "fixed"

    invalid = client.put(
        "/device-locations/node_A01",
        headers={"x-upload-token": "secret-token"},
        json={
            "latitude": 95,
            "longitude": 121.531567,
            "location_source": "manual_map",
        },
    )
    assert invalid.status_code == 400

    deleted = client.delete(
        "/device-locations/node_A01",
        headers={"x-upload-token": "secret-token"},
    )
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True
    assert client.get("/device-locations/node_A01").json()["device_location"] is None
    fallback_status = client.get("/device-status").json()["devices"][0]
    assert fallback_status["effective_latitude"] == 25.9
    assert fallback_status["effective_longitude"] == 121.9
    assert fallback_status["effective_location_source"] == "event_gps"
