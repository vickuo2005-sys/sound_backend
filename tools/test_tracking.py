import os
import sys

os.environ["DATABASE_URL"] = ""

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from services.localization.geo import haversine_m, xy_to_latlng  # noqa: E402
from services.tracking.tracking_service import (  # noqa: E402
    can_associate_track,
    update_track_from_measurement,
)


def main() -> None:
    origin_lat = 25.033
    origin_lng = 121.565
    first_lat, first_lng = xy_to_latlng(0.0, 0.0, origin_lat, origin_lng)
    second_lat, second_lng = xy_to_latlng(10.0, 0.0, origin_lat, origin_lng)

    first_measurement = {
        "label": "aircraft",
        "estimated_lat": first_lat,
        "estimated_lng": first_lng,
        "confidence": 0.8,
        "uncertainty_radius_m": 30,
        "event_time_ms": 1000.0,
    }
    state = update_track_from_measurement(None, first_measurement)
    assert state["filtered_lat"] == first_lat
    assert state["speed_mps"] == 0

    track = {
        "id": "track_1",
        "label": "aircraft",
        "origin_lat": state["origin_lat"],
        "origin_lng": state["origin_lng"],
        "last_lat": state["filtered_lat"],
        "last_lng": state["filtered_lng"],
        "last_event_time_ms": 1000.0,
        "velocity_east_mps": 0.0,
        "velocity_north_mps": 0.0,
    }
    second_measurement = {
        "label": "aircraft",
        "estimated_lat": second_lat,
        "estimated_lng": second_lng,
        "confidence": 0.8,
        "uncertainty_radius_m": 30,
        "event_time_ms": 2000.0,
    }
    ok, details = can_associate_track(track, second_measurement)
    assert ok, details

    next_state = update_track_from_measurement(track, second_measurement)
    distance_m = haversine_m(
        second_lat,
        second_lng,
        next_state["filtered_lat"],
        next_state["filtered_lng"],
    )
    assert distance_m < 5.0, distance_m
    assert next_state["speed_mps"] > 0
    print("Tracking tests passed")


if __name__ == "__main__":
    main()
