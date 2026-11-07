from datetime import datetime, timezone

import main
import pytest
from services.localization.geo import xy_to_latlng
from services.tracking.tracking_service import update_track_from_measurement


def base_track(*, time_ms: float) -> dict:
    return {
        "id": "track-stable",
        "label": "aircraft",
        "origin_lat": 25.033,
        "origin_lng": 121.565,
        "last_lat": 25.033,
        "last_lng": 121.565,
        "last_event_time_ms": time_ms,
        "velocity_east_mps": 0.0,
        "velocity_north_mps": 0.0,
    }


def test_same_timestamp_is_rejected_without_velocity_explosion() -> None:
    time_ms = 1_787_202_804_434.0
    east_lat, east_lng = xy_to_latlng(300.0, 0.0, 25.033, 121.565)

    state = update_track_from_measurement(
        base_track(time_ms=time_ms),
        {
            "estimated_lat": east_lat,
            "estimated_lng": east_lng,
            "event_time_ms": time_ms,
            "uncertainty_radius_m": 30.0,
        },
        max_speed_mps=80.0,
    )

    assert state["rejected_as_outlier"] is True
    assert state["state_json"]["reason"] == "non_increasing_measurement_time"
    assert state["speed_mps"] == 0.0
    assert state["filtered_lat"] == 25.033
    assert state["filtered_lng"] == 121.565


def test_impossible_motion_is_rejected_by_physical_gate() -> None:
    time_ms = 1_787_202_804_434.0
    east_lat, east_lng = xy_to_latlng(1000.0, 0.0, 25.033, 121.565)

    state = update_track_from_measurement(
        base_track(time_ms=time_ms),
        {
            "estimated_lat": east_lat,
            "estimated_lng": east_lng,
            "event_time_ms": time_ms + 1000.0,
            "uncertainty_radius_m": 0.0,
        },
        max_speed_mps=80.0,
        base_gate_m=100.0,
    )

    assert state["rejected_as_outlier"] is True
    assert state["state_json"]["reason"] == "innovation_gate_exceeded"
    assert state["speed_mps"] <= 80.0


def test_motion_field_mode_rejects_missing_event_time() -> None:
    with pytest.raises(ValueError, match="canonical event_time_ms"):
        update_track_from_measurement(
            None,
            {
                "estimated_lat": 25.033,
                "estimated_lng": 121.565,
                "uncertainty_radius_m": 30.0,
            },
            require_event_time=True,
        )


def test_process_tracking_deduplicates_equal_measurement_time(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "tracking_dedup.db"
    monkeypatch.setattr(main, "DB_NAME", str(db_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    main.init_sqlite_db()
    event_time_ms = datetime.now(timezone.utc).timestamp() * 1000.0

    first = main.process_tracking_measurement(
        {
            "label": "aircraft",
            "estimated_lat": 25.033,
            "estimated_lng": 121.565,
            "confidence": 0.9,
            "uncertainty_radius_m": 30.0,
            "event_time_ms": event_time_ms,
        },
        close_stale=False,
    )
    second_lat, second_lng = xy_to_latlng(10.0, 0.0, 25.033, 121.565)
    second = main.process_tracking_measurement(
        {
            "label": "aircraft",
            "estimated_lat": second_lat,
            "estimated_lng": second_lng,
            "confidence": 0.9,
            "uncertainty_radius_m": 30.0,
            "event_time_ms": event_time_ms,
        },
        close_stale=False,
    )

    with main.get_sqlite_connection() as connection:
        point_count = connection.execute(
            "SELECT COUNT(*) AS count FROM target_track_points WHERE track_id = ?",
            (first["id"],),
        ).fetchone()["count"]

    assert second["id"] == first["id"]
    assert second["point_count"] == 1
    assert point_count == 1


def test_motion_field_telemetry_persists_rejected_raw_point_without_track_update(
    tmp_path, monkeypatch
) -> None:
    db_path = tmp_path / "tracking_raw_rejection.db"
    monkeypatch.setattr(main, "DB_NAME", str(db_path))
    monkeypatch.setattr(main, "MOTION_FIELD_TELEMETRY_ENABLED", True)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    main.init_sqlite_db()
    event_time_ms = datetime.now(timezone.utc).timestamp() * 1000.0
    first = main.process_tracking_measurement(
        {
            "group_id": "motion-field-raw-rejection",
            "label": "aircraft",
            "estimated_lat": 25.033,
            "estimated_lng": 121.565,
            "confidence": 0.9,
            "uncertainty_radius_m": 0.0,
            "event_time_ms": event_time_ms,
            "source": "field-test",
        },
        close_stale=False,
    )
    jump_lat, jump_lng = xy_to_latlng(1000.0, 0.0, 25.033, 121.565)
    second = main.process_tracking_measurement(
        {
            "group_id": "motion-field-raw-rejection",
            "label": "aircraft",
            "estimated_lat": jump_lat,
            "estimated_lng": jump_lng,
            "confidence": 0.9,
            "uncertainty_radius_m": 0.0,
            "event_time_ms": event_time_ms + 1000.0,
            "source": "field-test",
        },
        close_stale=False,
    )

    with main.get_sqlite_connection() as connection:
        rows = connection.execute(
            """
            SELECT measured_lat, measured_lng, rejected_as_outlier, state_json
            FROM target_track_points
            WHERE track_id = ?
            ORDER BY created_at
            """,
            (first["id"],),
        ).fetchall()

    assert second["point_count"] == 1
    assert len(rows) == 2
    assert rows[1]["rejected_as_outlier"] == 1
    assert rows[1]["measured_lat"] == pytest.approx(jump_lat)
    assert rows[1]["measured_lng"] == pytest.approx(jump_lng)
    assert "innovation_gate_exceeded" in rows[1]["state_json"]


def test_delete_implausible_tracks_preserves_healthy_history(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "tracking_cleanup.db"
    monkeypatch.setattr(main, "DB_NAME", str(db_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    main.init_sqlite_db()
    now = datetime.now(timezone.utc).isoformat()

    with main.get_sqlite_connection() as connection:
        for track_id, speed, lat, lng in [
            ("healthy", 25.0, 25.033, 121.565),
            ("bad-speed", 81.0, 25.033, 121.565),
            ("bad-coordinate", 20.0, -777599.0, 250614.0),
            ("bad-point", 20.0, 25.033, 121.565),
        ]:
            connection.execute(
                """
                INSERT INTO target_tracks (
                    id, label, status, point_count, last_lat, last_lng,
                    last_speed_mps, created_at, updated_at
                )
                VALUES (?, 'aircraft', 'CLOSED', 1, ?, ?, ?, ?, ?)
                """,
                (track_id, lat, lng, speed, now, now),
            )
        connection.execute(
            """
            INSERT INTO target_track_points (
                id, track_id, measurement_time_ms, filtered_lat, filtered_lng,
                predicted_lat, predicted_lng, speed_mps, created_at
            )
            VALUES ('bad-point-1', 'bad-point', 1, 25.033, 121.565,
                    25.033, 121.565, 500, ?)
            """,
            (now,),
        )
        connection.commit()

    result = main.delete_implausible_target_tracks(max_speed_mps=80.0)

    with main.get_sqlite_connection() as connection:
        remaining = {
            str(row["id"])
            for row in connection.execute("SELECT id FROM target_tracks").fetchall()
        }

    assert result["deleted_count"] == 3
    assert set(result["deleted_track_ids"]) == {
        "bad-speed",
        "bad-coordinate",
        "bad-point",
    }
    assert remaining == {"healthy"}


def test_dashboard_rejects_invalid_track_points_and_zero_time_playback() -> None:
    html = main.dashboard_v4_clean().body.decode("utf-8")

    assert "!Boolean(point.rejected_as_outlier)" in html
    assert "isValidCoordinatePair(point.filtered_lat, point.filtered_lng)" in html
    assert "Number.isFinite(segmentTimeMs) && segmentTimeMs > 0" in html
    assert "speed >= 0 && speed <= 80" in html
