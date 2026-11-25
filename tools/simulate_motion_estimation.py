from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.tracking.motion import (
    MotionQualityConfig,
    estimate_constant_velocity,
    local_xy_to_latlng,
)


REFERENCE_LATITUDE = 25.033
REFERENCE_LONGITUDE = 121.565
START_TIME_MS = 1_800_000_000_000
HOP_SECONDS = 1.5


def points_for_velocity(
    vx_mps: float,
    vy_mps: float,
    *,
    count: int = 5,
    offsets_m: list[tuple[float, float]] | None = None,
) -> list[dict[str, Any]]:
    points = []
    for index in range(count):
        time_s = index * HOP_SECONDS
        offset_x, offset_y = (offsets_m or [(0.0, 0.0)] * count)[index]
        latitude, longitude = local_xy_to_latlng(
            vx_mps * time_s + offset_x,
            vy_mps * time_s + offset_y,
            REFERENCE_LATITUDE,
            REFERENCE_LONGITUDE,
        )
        points.append(
            {
                "measurement_time_ms": START_TIME_MS + time_s * 1000.0,
                "measured_lat": latitude,
                "measured_lng": longitude,
                "uncertainty_radius_m": 8.0,
            }
        )
    return points


def _scenario(
    points: list[dict[str, Any]],
    *,
    expected_speed_mps: float | None,
    expected_heading_deg: float | None,
    config: MotionQualityConfig = MotionQualityConfig(),
) -> dict[str, Any]:
    estimate = estimate_constant_velocity(points, config=config).to_dict()
    speed = estimate["speed_mps"]
    heading = estimate["heading_deg"]
    return {
        "expected": {
            "speed_mps": expected_speed_mps,
            "heading_deg": expected_heading_deg,
        },
        "estimated": estimate,
        "error": {
            "speed_mps": None
            if speed is None or expected_speed_mps is None
            else abs(speed - expected_speed_mps),
            "heading_deg": None
            if heading is None or expected_heading_deg is None
            else min(
                abs(heading - expected_heading_deg),
                360.0 - abs(heading - expected_heading_deg),
            ),
        },
        "quality": estimate["quality"],
    }


def simulate_scenarios() -> dict[str, dict[str, Any]]:
    east = points_for_velocity(10.0, 0.0)
    ordered_three = east[:3]
    out_of_order = [ordered_three[1], ordered_three[2], ordered_three[0]]
    noisy_offsets = [(0, 0), (2, -1), (-2, 2), (1, -2), (0, 1)]
    outlier = points_for_velocity(10.0, 0.0)
    outlier_lat, outlier_lng = local_xy_to_latlng(
        10.0 * 2 * HOP_SECONDS + 500.0,
        0.0,
        REFERENCE_LATITUDE,
        REFERENCE_LONGITUDE,
    )
    outlier[2] = {
        **outlier[2],
        "measured_lat": outlier_lat,
        "measured_lng": outlier_lng,
    }
    missing = [east[index] for index in (0, 1, 3, 4)]
    duplicate = [*east, dict(east[2])]
    southwest_component = 20.0 / math.sqrt(2.0)

    return {
        "A_stationary": _scenario(
            points_for_velocity(0.0, 0.0),
            expected_speed_mps=0.0,
            expected_heading_deg=None,
        ),
        "B_straight_east_10_mps": _scenario(
            east,
            expected_speed_mps=10.0,
            expected_heading_deg=90.0,
        ),
        "C_straight_north_15_mps": _scenario(
            points_for_velocity(0.0, 15.0),
            expected_speed_mps=15.0,
            expected_heading_deg=0.0,
        ),
        "D_southwest_20_mps": _scenario(
            points_for_velocity(-southwest_component, -southwest_component),
            expected_speed_mps=20.0,
            expected_heading_deg=225.0,
        ),
        "E_noisy_positions": _scenario(
            points_for_velocity(10.0, 0.0, offsets_m=noisy_offsets),
            expected_speed_mps=10.0,
            expected_heading_deg=90.0,
        ),
        "F_one_outlier_point": _scenario(
            outlier,
            expected_speed_mps=10.0,
            expected_heading_deg=90.0,
        ),
        "G_missing_observation": _scenario(
            missing,
            expected_speed_mps=10.0,
            expected_heading_deg=90.0,
        ),
        "H_out_of_order_E2_E3_E1": _scenario(
            out_of_order,
            expected_speed_mps=10.0,
            expected_heading_deg=90.0,
        ),
        "I_duplicate_point": _scenario(
            duplicate,
            expected_speed_mps=10.0,
            expected_heading_deg=90.0,
        ),
        "J_single_point": _scenario(
            east[:1],
            expected_speed_mps=None,
            expected_heading_deg=None,
        ),
    }


if __name__ == "__main__":
    print(json.dumps(simulate_scenarios(), indent=2, sort_keys=True))
