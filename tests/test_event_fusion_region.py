from datetime import datetime, timedelta, timezone

from services.event_fusion import process_event
from tools.test_event_fusion import make_connection


def event_record(
    event_id: str,
    device_id: str,
    label: str,
    timestamp: datetime,
    latitude: float = 25.0,
    longitude: float = 121.0,
    created_at: datetime | None = None,
) -> dict:
    return {
        "id": None,
        "event_id": event_id,
        "device_id": device_id,
        "label": label,
        "timestamp": timestamp.isoformat(),
        "created_at": (created_at or timestamp).isoformat(),
        "latitude": latitude,
        "longitude": longitude,
        "rms_peak": 0.8,
        "note": "probability_aircraft=0.9, confidence=0.9",
    }


def test_fusion_group_updates_region_fields_and_dedupes_devices() -> None:
    connection = make_connection()
    base = datetime(2026, 7, 27, 8, 0, tzinfo=timezone.utc)

    group = process_event(
        connection,
        event_record("evt_a01", "node_A01", "aircraft", base, 25.0, 121.0),
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
        event_record("evt_a03", "node_A03", "aircraft", base + timedelta(seconds=2), 25.2, 121.0),
        is_postgres=False,
        window_seconds=3,
    )
    duplicate_device_group = process_event(
        connection,
        event_record("evt_a01_again", "node_A01", "aircraft", base + timedelta(seconds=2.5), 25.05, 121.02),
        is_postgres=False,
        window_seconds=3,
    )

    assert duplicate_device_group["id"] == group["id"]
    assert duplicate_device_group["node_count"] == 3
    assert duplicate_device_group["reporting_node_count"] == 3
    assert duplicate_device_group["reporting_device_ids"] == ["node_A01", "node_A02", "node_A03"]
    assert duplicate_device_group["region_type"] == "polygon"
    assert duplicate_device_group["region_geojson"]["type"] == "Polygon"
    assert duplicate_device_group["localization_method"] == "multi_node_region"
    assert duplicate_device_group["estimated_lat"] == duplicate_device_group["region_center_lat"]
    assert duplicate_device_group["estimated_lng"] == duplicate_device_group["region_center_lng"]


def test_events_outside_episode_hold_are_not_grouped() -> None:
    connection = make_connection()
    base = datetime(2026, 7, 27, 8, 0, tzinfo=timezone.utc)

    first = process_event(
        connection,
        event_record("evt_early", "node_A01", "aircraft", base),
        is_postgres=False,
        window_seconds=3,
    )
    later = process_event(
        connection,
        event_record("evt_late", "node_A02", "aircraft", base + timedelta(seconds=70)),
        is_postgres=False,
        window_seconds=3,
    )

    assert later["id"] != first["id"]


def test_late_arriving_observation_can_attach_to_recent_episode() -> None:
    connection = make_connection()
    base = datetime(2026, 7, 27, 8, 0, tzinfo=timezone.utc)

    first = process_event(
        connection,
        event_record("evt_a01", "node_A01", "aircraft", base),
        is_postgres=False,
        window_seconds=3,
    )
    process_event(
        connection,
        event_record("evt_a02", "node_A02", "aircraft", base + timedelta(seconds=1)),
        is_postgres=False,
        window_seconds=3,
    )
    later_episode = process_event(
        connection,
        event_record("evt_a04", "node_A04", "aircraft", base + timedelta(seconds=45)),
        is_postgres=False,
        window_seconds=3,
    )
    late_arrival = process_event(
        connection,
        event_record("evt_a03", "node_A03", "aircraft", base + timedelta(seconds=2)),
        is_postgres=False,
        window_seconds=3,
    )

    assert later_episode["id"] != first["id"]
    assert late_arrival["id"] == first["id"]
    assert late_arrival["node_count"] == 3


def test_nearby_fragment_groups_are_merged_into_one_episode() -> None:
    connection = make_connection()
    base = datetime(2026, 7, 27, 8, 0, tzinfo=timezone.utc)

    first = process_event(
        connection,
        event_record("evt_merge_a01", "node_A01", "aircraft", base, 25.0, 121.0),
        is_postgres=False,
        window_seconds=3,
    )
    later = process_event(
        connection,
        event_record("evt_merge_a04", "node_A04", "aircraft", base + timedelta(seconds=40), 25.1, 121.1),
        is_postgres=False,
        window_seconds=3,
    )

    assert later["id"] != first["id"]

    merged = process_event(
        connection,
        event_record("evt_merge_a03", "node_A03", "aircraft", base + timedelta(seconds=20), 25.2, 121.0),
        is_postgres=False,
        window_seconds=3,
    )

    assert merged["node_count"] == 3
    assert set(merged["reporting_device_ids"]) == {"node_A01", "node_A03", "node_A04"}
    assert merged["region_type"] == "polygon"


def test_events_from_different_labels_are_not_grouped() -> None:
    connection = make_connection()
    base = datetime(2026, 7, 27, 8, 0, tzinfo=timezone.utc)

    aircraft = process_event(
        connection,
        event_record("evt_aircraft", "node_A01", "aircraft", base),
        is_postgres=False,
        window_seconds=3,
    )
    other = process_event(
        connection,
        event_record("evt_other", "node_A02", "non_aircraft", base + timedelta(seconds=1)),
        is_postgres=False,
        window_seconds=3,
    )

    assert other["id"] != aircraft["id"]


def test_fusion_groups_by_device_observed_time_for_live_episode() -> None:
    connection = make_connection()
    backend_time = datetime(2026, 7, 27, 8, 0, tzinfo=timezone.utc)
    device_time = datetime(2026, 7, 27, 7, 59, tzinfo=timezone.utc)

    first = process_event(
        connection,
        event_record(
            "evt_live_a01",
            "node_A01",
            "aircraft",
            device_time,
            25.0,
            121.0,
            created_at=backend_time,
        ),
        is_postgres=False,
        window_seconds=3,
    )
    different_sound_time = process_event(
        connection,
        event_record(
            "evt_live_a02",
            "node_A02",
            "aircraft",
            device_time + timedelta(seconds=45),
            25.0,
            121.2,
            created_at=backend_time + timedelta(seconds=1),
        ),
        is_postgres=False,
        window_seconds=3,
    )

    same_sound_episode = process_event(
        connection,
        event_record(
            "evt_live_a03",
            "node_A03",
            "aircraft",
            device_time + timedelta(seconds=1),
            25.0,
            121.3,
            created_at=backend_time + timedelta(seconds=45),
        ),
        is_postgres=False,
        window_seconds=3,
    )

    assert different_sound_time["id"] != first["id"]
    assert same_sound_episode["id"] == first["id"]
    assert same_sound_episode["node_count"] == 2
    assert same_sound_episode["region_type"] == "segment"
