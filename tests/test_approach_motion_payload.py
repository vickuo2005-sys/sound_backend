from services.dashboard_payloads import serialize_track_for_dashboard


def test_approach_motion_uses_source_points_and_preserves_input():
    points = [{"measurement_time_ms": 1000 + i * 1500,
               "measured_lat": 25.0, "measured_lng": 121.0 + i * 0.0001,
               "uncertainty_radius_m": 1,
               "diagnostics_json": {"source": "localization_result"}} for i in range(6)]
    track = {"id": "test", "recent_points": points}
    result = serialize_track_for_dashboard(track, experimental_motion_enabled=True)
    motion = result["approach_motion"]
    assert motion["valid"] is True
    assert motion["quality"] == "high"
    assert motion["vx_mps"] > 0
    assert abs(motion["vy_mps"]) < 0.001
    assert motion["measurement_time_ms"] == 8500
    assert motion["field_validated"] is False
    assert "approach_motion" not in track
    assert "approach_motion" not in serialize_track_for_dashboard(track, experimental_motion_enabled=False)


def test_approach_motion_rejects_regions_and_rejected_measurements():
    points = [{"measurement_time_ms": i * 1000, "measured_lat": 25,
               "measured_lng": 121 + i * 0.001,
               "diagnostics_json": {"source": "event_group_region"}} for i in range(6)]
    points.append({"measurement_time_ms": 8000, "measured_lat": 25, "measured_lng": 121,
                   "rejected_as_outlier": True, "diagnostics_json": {"source": "localization_result"}})
    result = serialize_track_for_dashboard({"recent_points": points}, experimental_motion_enabled=True)
    assert result["approach_motion"]["valid"] is False
    assert result["approach_motion"]["quality"] == "insufficient"
