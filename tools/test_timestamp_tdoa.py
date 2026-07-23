import os
import sys

os.environ["DATABASE_URL"] = ""

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from services.localization.geo import haversine_m, xy_to_latlng  # noqa: E402
from services.localization.timestamp_tdoa import (  # noqa: E402
    SOUND_SPEED_MPS,
    estimate_timestamp_tdoa,
)


def synthetic_observations() -> tuple[list[dict], tuple[float, float]]:
    origin_lat = 25.033
    origin_lng = 121.565
    node_xy = [(-120.0, -110.0), (130.0, -90.0), (120.0, 130.0), (-130.0, 100.0)]
    target_x = 40.0
    target_y = 30.0
    target_lat, target_lng = xy_to_latlng(target_x, target_y, origin_lat, origin_lng)
    base_time_ms = 1_780_000_000_000.0
    observations = []
    for index, (x, y) in enumerate(node_xy, start=1):
        lat, lng = xy_to_latlng(x, y, origin_lat, origin_lng)
        distance_m = ((target_x - x) ** 2 + (target_y - y) ** 2) ** 0.5
        observations.append(
            {
                "event_id": f"evt_tdoa_{index}",
                "device_id": f"node_A0{index}",
                "label": "aircraft",
                "latitude": lat,
                "longitude": lng,
                "corrected_arrival_time_ms": base_time_ms
                + (distance_m / SOUND_SPEED_MPS * 1000.0),
                "time_sync_rtt_ms": 20.0,
                "time_sync_quality": "good",
                "time_sync_age_ms": 1000,
                "aircraft_probability": 0.95,
            }
        )
    return observations, (target_lat, target_lng)


def main() -> None:
    observations, truth = synthetic_observations()
    result = estimate_timestamp_tdoa(observations)
    assert result["status"] == "SUCCESS", result
    error_m = haversine_m(
        truth[0],
        truth[1],
        float(result["estimated_lat"]),
        float(result["estimated_lng"]),
    )
    assert error_m < 5.0, error_m
    assert result["method"] == "timestamp_tdoa"
    assert result["reference_device_id"]

    stale = [{**item, "time_sync_quality": "stale"} for item in observations]
    fallback = estimate_timestamp_tdoa(stale)
    assert fallback["status"] == "FALLBACK"
    assert fallback["method"] == "weighted_centroid_fallback"
    print("Timestamp TDOA tests passed")


if __name__ == "__main__":
    main()
