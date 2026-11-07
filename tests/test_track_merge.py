import json

import main


def _insert_track(connection, track_id: str, first_ms: float, last_ms: float, point_count: int) -> None:
    connection.execute(
        """
        INSERT INTO target_tracks (
            id, label, status, origin_lat, origin_lng, created_at, updated_at,
            first_event_time_ms, last_event_time_ms, point_count, last_lat,
            last_lng, last_speed_mps, last_confidence, velocity_east_mps,
            velocity_north_mps, closed_at
        ) VALUES (?, 'aircraft', 'CLOSED', 25.0, 121.0, ?, ?, ?, ?, ?, 25.0,
                  121.0, 0, 0.8, 0, 0, ?)
        """,
        (
            track_id,
            "2026-08-20T06:00:00+00:00",
            "2026-08-20T06:01:00+00:00",
            first_ms,
            last_ms,
            point_count,
            "2026-08-20T06:01:00+00:00",
        ),
    )


def _insert_point(connection, point_id: str, track_id: str, time_ms: float, latitude: float) -> None:
    connection.execute(
        """
        INSERT INTO target_track_points (
            id, track_id, measurement_time_ms, measured_lat, measured_lng,
            filtered_lat, filtered_lng, speed_mps, heading_deg, confidence, velocity_east_mps,
            velocity_north_mps, diagnostics_json, created_at
        ) VALUES (?, ?, ?, ?, 121.0, ?, 121.0, 0, NULL, 0.8, 0, 0, ?, ?)
        """,
        (
            point_id,
            track_id,
            time_ms,
            latitude,
            latitude,
            json.dumps({"source": "test"}),
            "2026-08-20T06:01:00+00:00",
        ),
    )


def test_merge_closed_tracks_preserves_source_audit(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(main, "DB_NAME", str(tmp_path / "track_merge.db"))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    main.init_sqlite_db()

    target_id = "80ee98e1-dc4c-4a85-8b6d-9bc3157edceb"
    source_id = "3dfbeb21-3e42-4eb8-a76c-812a2f9c4bca"
    with main.get_sqlite_connection() as connection:
        _insert_track(connection, target_id, 1000, 2000, 1)
        _insert_track(connection, source_id, 2000, 3000, 2)
        _insert_point(connection, "point-target", target_id, 2000, 25.1)
        _insert_point(connection, "point-source-1", source_id, 2000, 25.2)
        _insert_point(connection, "point-source-2", source_id, 3000, 25.3)
        connection.commit()

    preview = main.merge_closed_target_tracks(target_id, source_id, dry_run=True)
    assert preview["source_point_count"] == 2
    assert preview["time_gap_ms"] == 0

    result = main.merge_closed_target_tracks(target_id, source_id)

    assert result["moved_point_count"] == 2
    assert result["track"]["point_count"] == 3
    assert result["track"]["last_event_time_ms"] == 3000
    assert result["track"]["last_lat"] == 25.3
    assert result["merged_source"]["status"] == "MERGED"
    assert result["merged_source"]["point_count"] == 0

    merged_points = main.list_track_points(target_id, limit=10)
    source_points = main.list_track_points(source_id, limit=10)
    moved = [point for point in merged_points if point["id"].startswith("point-source")]
    assert len(merged_points) == 3
    assert source_points == []
    assert all(
        point["diagnostics_json"]["merged_from_track_id"] == source_id
        for point in moved
    )


def test_linear_smoothing_preserves_measurements_and_audit(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(main, "DB_NAME", str(tmp_path / "track_smoothing.db"))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    main.init_sqlite_db()

    track_id = "80ee98e1-dc4c-4a85-8b6d-9bc3157edceb"
    with main.get_sqlite_connection() as connection:
        _insert_track(connection, track_id, 1_000_000, 1_020_000, 3)
        _insert_point(connection, "smooth-1", track_id, 1_000_000, 25.0000)
        _insert_point(connection, "smooth-2", track_id, 1_010_000, 25.0100)
        _insert_point(connection, "smooth-3", track_id, 1_020_000, 25.0002)
        connection.commit()

    preview = main.smooth_closed_target_track_linear(track_id, dry_run=True)
    assert preview["point_count"] == 3
    assert preview["speed_mps"] < main.TRACK_MAX_SPEED_MPS

    result = main.smooth_closed_target_track_linear(track_id)
    points = main.list_track_points(track_id, limit=10)

    assert result["point_count"] == 3
    assert points[1]["measured_lat"] == 25.0100
    assert round(points[1]["filtered_lat"], 7) == 25.0001
    assert points[1]["diagnostics_json"]["track_adjustment"] == "linear_time_interpolation"
    assert points[1]["diagnostics_json"]["demo_smoothing_original"]["filtered_lat"] == 25.0100
    assert all(point["speed_mps"] == result["speed_mps"] for point in points)
