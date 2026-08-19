from datetime import datetime, timezone

import main


def insert_track(connection, track_id: str, *, label: str, status: str, point_count: int) -> None:
    now = datetime.now(timezone.utc).isoformat()
    connection.execute(
        """
        INSERT INTO target_tracks (
            id, label, status, point_count, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (track_id, label, status, point_count, now, now),
    )
    connection.execute(
        """
        INSERT INTO target_track_points (
            id, track_id, measurement_time_ms, created_at
        )
        VALUES (?, ?, ?, ?)
        """,
        (f"point-{track_id}", track_id, 1.0, now),
    )
    connection.commit()


def test_delete_closed_single_point_target_tracks_is_exact(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "track_cleanup.db"
    monkeypatch.setattr(main, "DB_NAME", str(db_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    main.init_sqlite_db()

    with main.get_sqlite_connection() as connection:
        insert_track(
            connection,
            "closed-single-aircraft",
            label="aircraft",
            status="CLOSED",
            point_count=1,
        )
        insert_track(
            connection,
            "closed-multi-aircraft",
            label="aircraft",
            status="CLOSED",
            point_count=2,
        )
        insert_track(
            connection,
            "active-single-aircraft",
            label="aircraft",
            status="ACTIVE",
            point_count=1,
        )
        insert_track(
            connection,
            "closed-single-other",
            label="other",
            status="CLOSED",
            point_count=1,
        )

    result = main.delete_closed_single_point_target_tracks()

    assert result["deleted_count"] == 1
    assert result["deleted_track_ids"] == ["closed-single-aircraft"]
    with main.get_sqlite_connection() as connection:
        remaining_tracks = {
            row["id"]
            for row in connection.execute("SELECT id FROM target_tracks").fetchall()
        }
        remaining_points = {
            row["track_id"]
            for row in connection.execute("SELECT track_id FROM target_track_points").fetchall()
        }

    assert "closed-single-aircraft" not in remaining_tracks
    assert "closed-single-aircraft" not in remaining_points
    assert remaining_tracks == {
        "closed-multi-aircraft",
        "active-single-aircraft",
        "closed-single-other",
    }
