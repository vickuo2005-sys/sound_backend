from __future__ import annotations

import math

import pytest

from services.tracking.motion import (
    estimate_constant_velocity,
    latlng_to_local_xy,
    local_xy_to_latlng,
)
from services.tracking.motion_validation import (
    circular_heading_error_deg,
    classify_site_motion,
    uncertainty_coverage,
)
from tools.analyze_motion_field import analyze_run, truth_state_at
from tools.capture_motion_field_run import (
    normalized_points,
    reject_secret_keys,
    validate_base_url,
)
from tools.simulate_motion_estimation import (
    HOP_SECONDS,
    REFERENCE_LATITUDE,
    REFERENCE_LONGITUDE,
    START_TIME_MS,
    points_for_velocity,
)


def field_points_for_x(values: list[float]) -> list[dict]:
    points = []
    for index, x_m in enumerate(values):
        latitude, longitude = local_xy_to_latlng(
            x_m,
            0.0,
            REFERENCE_LATITUDE,
            REFERENCE_LONGITUDE,
        )
        points.append(
            {
                "measurement_time_ms": START_TIME_MS + index * HOP_SECONDS * 1000,
                "filtered_lat": latitude,
                "filtered_lng": longitude,
                "uncertainty_radius_m": 8.0,
            }
        )
    return points


def test_local_tangent_units_and_axis_convention() -> None:
    for expected_x, expected_y in ((0.0, 1.0), (1.0, 0.0), (1.0, 1.0)):
        latitude, longitude = local_xy_to_latlng(
            expected_x,
            expected_y,
            REFERENCE_LATITUDE,
            REFERENCE_LONGITUDE,
        )
        actual_x, actual_y = latlng_to_local_xy(
            latitude,
            longitude,
            REFERENCE_LATITUDE,
            REFERENCE_LONGITUDE,
        )
        assert actual_x == pytest.approx(expected_x, abs=1e-6)
        assert actual_y == pytest.approx(expected_y, abs=1e-6)


def test_heading_circular_error_wraps_at_north() -> None:
    assert circular_heading_error_deg(359.0, 1.0) == pytest.approx(2.0)
    assert circular_heading_error_deg(90.0, 270.0) == pytest.approx(180.0)


def test_capture_is_fail_closed_to_isolated_staging() -> None:
    assert (
        validate_base_url("https://sound-backend-staging.onrender.com/")
        == "https://sound-backend-staging.onrender.com"
    )
    for forbidden in (
        "https://sound-backend.onrender.com",
        "http://sound-backend-staging.onrender.com",
        "https://sound-backend-staging.onrender.com?token=secret",
    ):
        with pytest.raises(ValueError):
            validate_base_url(forbidden)

    with pytest.raises(ValueError, match="secret-like key"):
        reject_secret_keys({"nested": {"upload_token": "must-not-be-exported"}})


def test_ground_truth_motion_includes_route_endpoints() -> None:
    east_lat, east_lng = local_xy_to_latlng(
        1.0,
        0.0,
        REFERENCE_LATITUDE,
        REFERENCE_LONGITUDE,
    )
    waypoints = [
        {
            "time_ms": 1000.0,
            "lat": REFERENCE_LATITUDE,
            "lng": REFERENCE_LONGITUDE,
        },
        {"time_ms": 2000.0, "lat": east_lat, "lng": east_lng},
    ]

    at_start = truth_state_at(1000.0, waypoints)
    at_end = truth_state_at(2000.0, waypoints)

    assert at_start is not None and at_start["speed_mps"] == pytest.approx(
        1.0, abs=1e-5
    )
    assert at_end is not None and at_end["speed_mps"] == pytest.approx(
        1.0, abs=1e-5
    )


def test_event_time_reorder_matches_normal_for_motion_result() -> None:
    ordered = points_for_velocity(8.0, 4.0)[:3]
    arrival_e2_e3_e1 = [ordered[1], ordered[2], ordered[0]]

    expected = estimate_constant_velocity(ordered)
    reordered = estimate_constant_velocity(arrival_e2_e3_e1)

    assert reordered.ordered_event_time_ms == expected.ordered_event_time_ms
    assert reordered.vx_mps == pytest.approx(expected.vx_mps, abs=1e-12)
    assert reordered.vy_mps == pytest.approx(expected.vy_mps, abs=1e-12)


def test_stop_move_stop_series_preserves_raw_phase_changes() -> None:
    x_values = [0.0, 0.0, 0.0, 3.0, 6.0, 9.0, 9.0, 9.0]
    points = []
    for index, x_m in enumerate(x_values):
        latitude, longitude = local_xy_to_latlng(
            x_m,
            0.0,
            REFERENCE_LATITUDE,
            REFERENCE_LONGITUDE,
        )
        points.append(
            {
                "measurement_time_ms": START_TIME_MS + index * 1500,
                "measured_lat": latitude,
                "measured_lng": longitude,
                "uncertainty_radius_m": 8.0,
            }
        )

    start = estimate_constant_velocity(points[:3])
    moving = estimate_constant_velocity(points[2:6])
    end = estimate_constant_velocity(points[-3:])

    assert start.speed_mps == pytest.approx(0.0, abs=1e-6)
    assert moving.speed_mps is not None and moving.speed_mps > 1.0
    assert moving.heading_deg == pytest.approx(90.0, abs=0.1)
    assert end.speed_mps == pytest.approx(0.0, abs=1e-6)


def test_uncertainty_coverage_is_diagnostic_not_confidence_claim() -> None:
    result = uncertainty_coverage([5.0, 20.0, 80.0], [10.0, 20.0, 30.0])

    assert result["count"] == 3
    assert result["covered_count"] == 2
    assert result["coverage_rate"] == pytest.approx(2 / 3)
    assert result["underestimated_count"] == 1


def test_approaching_departing_stationary_and_uncertain_shadow() -> None:
    site_lat, site_lng = local_xy_to_latlng(
        100.0,
        0.0,
        REFERENCE_LATITUDE,
        REFERENCE_LONGITUDE,
    )
    approaching = classify_site_motion(
        field_points_for_x([20, 35, 50, 65, 80]),
        site_latitude=site_lat,
        site_longitude=site_lng,
        minimum_reliable_speed_mps=1.0,
    )
    departing = classify_site_motion(
        field_points_for_x([80, 65, 50, 35, 20]),
        site_latitude=site_lat,
        site_longitude=site_lng,
        minimum_reliable_speed_mps=1.0,
    )
    stationary = classify_site_motion(
        field_points_for_x([40, 40, 40, 40, 40]),
        site_latitude=site_lat,
        site_longitude=site_lng,
        minimum_reliable_speed_mps=1.0,
    )
    uncertain = classify_site_motion(
        field_points_for_x([20, 35, 50, 65, 80]),
        site_latitude=site_lat,
        site_longitude=site_lng,
        minimum_reliable_speed_mps=None,
    )

    assert approaching["classification"] == "APPROACHING"
    assert departing["classification"] == "DEPARTING"
    assert stationary["classification"] == "STATIONARY"
    assert uncertain["classification"] == "UNCERTAIN"


def test_capture_normalization_retains_raw_and_arrival_order() -> None:
    points = [
        {
            "id": "p2",
            "measurement_time_ms": 2000.0,
            "measured_lat": 25.0,
            "measured_lng": 121.0,
            "filtered_lat": 25.1,
            "filtered_lng": 121.1,
            "created_at": "2026-01-01T00:00:00Z",
            "diagnostics_json": {
                "localization_method": "timestamp_tdoa",
                "reporting_node_count": 3,
            },
        },
        {
            "id": "p1",
            "measurement_time_ms": 1000.0,
            "measured_lat": 24.9,
            "measured_lng": 120.9,
            "filtered_lat": 25.0,
            "filtered_lng": 121.0,
            "created_at": "2026-01-01T00:00:01Z",
            "diagnostics_json": {"tracking_discard_reason": "late_measurement_discarded"},
            "rejected_as_outlier": True,
        },
    ]

    normalized = normalized_points(
        points,
        run_id="run-1",
        track_id="track-1",
        start_time_ms=0.0,
        end_time_ms=3000.0,
    )

    assert [point["point_id"] for point in normalized] == ["p1", "p2"]
    assert normalized[0]["measured_lat"] == 24.9
    assert normalized[0]["filtered_lat"] == 25.0
    assert normalized[0]["arrival_out_of_order"] is True
    assert normalized[1]["source_node_count"] == 3


def test_analyzer_reports_raw_and_current_without_hiding_points() -> None:
    points = []
    for index in range(5):
        latitude, longitude = local_xy_to_latlng(
            float(index % 2),
            0.0,
            REFERENCE_LATITUDE,
            REFERENCE_LONGITUDE,
        )
        points.append(
            {
                "point_id": f"p{index}",
                "event_time_ms": START_TIME_MS + index * 1500.0,
                "measured_lat": latitude,
                "measured_lng": longitude,
                "filtered_lat": REFERENCE_LATITUDE,
                "filtered_lng": REFERENCE_LONGITUDE,
                "speed_mps": 0.0,
                "heading_deg": None,
                "uncertainty_radius_m": 8.0,
                "innovation_m": abs(float(index % 2)),
                "rejected_as_outlier": False,
                "arrival_out_of_order": False,
            }
        )
    run = {
        "schema_version": "bi2.motion_field_run.v1",
        "run_id": "static-01",
        "scenario": "S0_static",
        "start_time": "2026-01-01T00:00:00Z",
        "end_time": "2026-01-01T00:00:06Z",
        "node_ids": ["A01", "A02"],
        "ground_truth": {
            "route_start": {
                "lat": REFERENCE_LATITUDE,
                "lng": REFERENCE_LONGITUDE,
            },
            "route_end": {
                "lat": REFERENCE_LATITUDE,
                "lng": REFERENCE_LONGITUDE,
            },
            "start_time": START_TIME_MS,
            "end_time": START_TIME_MS + 6000.0,
            "analysis": {"minimum_reliable_motion_speed_mps": 1.0},
        },
        "track_raw_data": points,
    }

    metrics = analyze_run(run)

    assert metrics["point_count"] == 5
    assert metrics["position"]["raw_measured"]["count"] == 5
    assert metrics["position"]["current_filtered"]["rmse"] == pytest.approx(0.0)
    assert metrics["static"]["raw_position_jitter_rms_m"] is not None
    assert metrics["static"]["current_tracker_false_speed_mps"]["max"] == 0.0
    assert metrics["uncertainty_coverage_diagnostic"]["count"] == 5
    assert metrics["speed"]["current_tracker"]["estimate_standard_deviation"] == 0.0
    assert (
        metrics["speed"]["current_tracker"]["relative_absolute_error_percent"][
            "count"
        ]
        == 0
    )
