from __future__ import annotations

import main


def measurement(event_time_ms: float) -> dict:
    return {
        "group_id": "executor-order-group",
        "label": "aircraft",
        "estimated_lat": 25.033,
        "estimated_lng": 121.565,
        "confidence": 0.9,
        "uncertainty_radius_m": 30.0,
        "event_time_ms": event_time_ms,
        "source": "executor_order_test",
    }


def test_executor_completion_e2_e3_e1_discards_e1_from_same_track(
    tmp_path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "executor_order.db"
    monkeypatch.setattr(main, "DB_NAME", str(db_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    main.init_sqlite_db()
    counters_before = main.tracking_discard_metrics_snapshot()

    e2_track = main.process_tracking_measurement(measurement(2000), close_stale=False)
    e3_track = main.process_tracking_measurement(measurement(3000), close_stale=False)
    e1_result = main.process_tracking_measurement(measurement(1000), close_stale=False)

    with main.get_sqlite_connection() as connection:
        rows = connection.execute(
            """
            SELECT measurement_time_ms
            FROM target_track_points
            WHERE track_id = ?
            ORDER BY measurement_time_ms
            """,
            (e2_track["id"],),
        ).fetchall()

    counters_after = main.tracking_discard_metrics_snapshot()
    assert e3_track["id"] == e2_track["id"]
    assert e1_result["id"] == e2_track["id"]
    assert [row["measurement_time_ms"] for row in rows] == [2000, 3000]
    assert e1_result["point_count"] == 2
    assert (
        counters_after["late_measurement_discarded"]
        - counters_before["late_measurement_discarded"]
        == 1
    )
