import os
import sys

os.environ["DATABASE_URL"] = ""

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from main import (  # noqa: E402
    SOUND_SPEED_MPS,
    estimate_position_tdoa,
    haversine_m,
    local_xy_to_latlng,
)


def main() -> None:
    origin_lat = 25.033000
    origin_lng = 121.565000
    node_xy = [
        (-100.0, -100.0),
        (100.0, -100.0),
        (100.0, 100.0),
        (-100.0, 100.0),
    ]
    target_x = 35.0
    target_y = 45.0
    target_lat, target_lng = local_xy_to_latlng(
        target_x,
        target_y,
        origin_lat,
        origin_lng,
    )

    base_time_ms = 1_780_000_000_000.0
    noise_ms = [0.0, 2.0, -3.0, 1.0]
    observations = []
    for index, (x, y) in enumerate(node_xy, start=1):
        lat, lng = local_xy_to_latlng(x, y, origin_lat, origin_lng)
        distance_m = ((target_x - x) ** 2 + (target_y - y) ** 2) ** 0.5
        arrival_ms = base_time_ms + (distance_m / SOUND_SPEED_MPS * 1000.0)
        observations.append(
            {
                "event_id": f"sim_event_{index}",
                "device_id": f"node_A0{index}",
                "latitude": lat,
                "longitude": lng,
                "rms_peak": 1000.0,
                "aircraft_probability": 0.95,
                "event_timestamp": None,
                "weight": 1.0,
                "label": "aircraft",
                "corrected_arrival_time_ms": arrival_ms + noise_ms[index - 1],
                "time_sync_rtt_ms": 20.0,
            }
        )

    result = estimate_position_tdoa(observations)
    print(f"true position:      {target_lat:.8f}, {target_lng:.8f}")
    print(f"solver success:     {result.get('success')}")
    if not result.get("success"):
        print(f"fallback reason:    {result.get('reason')}")
        return

    estimated_lat = float(result["estimated_lat"])
    estimated_lng = float(result["estimated_lng"])
    error_m = haversine_m(target_lat, target_lng, estimated_lat, estimated_lng)
    print(f"estimated position: {estimated_lat:.8f}, {estimated_lng:.8f}")
    print(f"error meters:       {error_m:.2f}")
    print(f"residual rmse:      {float(result['residual_rmse_m']):.2f} m")
    print(f"time sync quality:  {result.get('time_sync_quality')}")
    print(f"uncertainty radius: {float(result['uncertainty_radius_m']):.2f} m")


if __name__ == "__main__":
    main()
