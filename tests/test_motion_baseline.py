from __future__ import annotations

import math

import pytest

from services.tracking.motion import (
    MotionQualityConfig,
    estimate_constant_velocity,
)
from tools.simulate_motion_estimation import points_for_velocity


@pytest.mark.parametrize(
    ("vx", "vy", "speed", "heading"),
    [
        (10.0, 0.0, 10.0, 90.0),
        (0.0, 15.0, 15.0, 0.0),
        (0.0, -15.0, 15.0, 180.0),
        (-10.0, 0.0, 10.0, 270.0),
        (-20 / math.sqrt(2), -20 / math.sqrt(2), 20.0, 225.0),
    ],
)
def test_cardinal_and_southwest_motion(vx, vy, speed, heading) -> None:
    estimate = estimate_constant_velocity(points_for_velocity(vx, vy))

    assert estimate.speed_mps == pytest.approx(speed, abs=0.02)
    assert estimate.heading_deg == pytest.approx(heading, abs=0.1)
    assert estimate.quality == "high"


def test_stationary_speed_is_zero() -> None:
    estimate = estimate_constant_velocity(points_for_velocity(0.0, 0.0))

    assert estimate.speed_mps == pytest.approx(0.0, abs=0.001)
    assert estimate.heading_deg is None


def test_out_of_order_arrival_matches_event_time_order() -> None:
    ordered = points_for_velocity(10.0, 0.0)[:3]
    out_of_order = [ordered[1], ordered[2], ordered[0]]

    expected = estimate_constant_velocity(ordered)
    actual = estimate_constant_velocity(out_of_order)

    assert actual.speed_mps == pytest.approx(expected.speed_mps, abs=1e-12)
    assert actual.heading_deg == pytest.approx(expected.heading_deg, abs=1e-12)
    assert actual.ordered_event_time_ms == expected.ordered_event_time_ms


def test_missing_observation_reduces_quality() -> None:
    complete = points_for_velocity(10.0, 0.0)
    missing = [complete[index] for index in (0, 1, 3, 4)]

    complete_estimate = estimate_constant_velocity(complete)
    missing_estimate = estimate_constant_velocity(missing)

    assert complete_estimate.quality == "high"
    assert missing_estimate.quality == "medium"
    assert missing_estimate.maximum_gap_s == 3.0


def test_duplicate_time_is_ignored_and_reported() -> None:
    points = points_for_velocity(10.0, 0.0)
    duplicate = [*points, dict(points[2])]

    estimate = estimate_constant_velocity(duplicate)

    assert estimate.sample_count == 5
    assert estimate.duplicate_count == 1
    assert estimate.speed_mps == pytest.approx(10.0, abs=0.02)


def test_single_point_is_insufficient() -> None:
    estimate = estimate_constant_velocity(points_for_velocity(10.0, 0.0)[:1])

    assert estimate.quality == "insufficient"
    assert estimate.valid is False
    assert estimate.speed_mps is None


def test_unrealistic_jump_is_low_quality_and_guard_can_invalidate() -> None:
    points = points_for_velocity(10.0, 0.0)
    points[2] = {
        **points[2],
        "measured_lng": points[2]["measured_lng"] + 0.01,
    }

    diagnostic = estimate_constant_velocity(points)
    guarded = estimate_constant_velocity(
        points,
        config=MotionQualityConfig(outlier_speed_guard_enabled=True),
    )

    assert diagnostic.outlier_detected is True
    assert diagnostic.quality == "low"
    assert diagnostic.valid is True
    assert guarded.outlier_detected is True
    assert guarded.valid is False
