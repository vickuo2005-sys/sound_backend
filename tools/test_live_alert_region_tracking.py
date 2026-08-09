import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


os.environ["DATABASE_URL"] = ""

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from main import build_active_alert_region_measurement  # noqa: E402


def event(
    device_id: str,
    *,
    seconds_ago: float,
    latitude: float,
    longitude: float,
    label: str = "aircraft",
    observed_seconds_ago: float | None = None,
) -> dict:
    now = datetime(2026, 8, 3, 8, 0, tzinfo=timezone.utc)
    created_at = now - timedelta(seconds=seconds_ago)
    observed_at = now - timedelta(
        seconds=observed_seconds_ago if observed_seconds_ago is not None else seconds_ago
    )
    return {
        "event_id": f"event_{device_id}_{int(seconds_ago * 1000)}",
        "device_id": device_id,
        "label": label,
        "created_at": created_at.isoformat(),
        "rms_peak_time_ms": int(observed_at.timestamp() * 1000),
        "effective_latitude": latitude,
        "effective_longitude": longitude,
        "rms_peak": 1200.0,
        "note": "probability_aircraft=0.91",
    }


def main() -> None:
    reference = datetime(2026, 8, 3, 8, 0, tzinfo=timezone.utc)

    single = build_active_alert_region_measurement(
        [event("node_A01", seconds_ago=1, latitude=25.0471, longitude=121.5383)],
        reference_time=reference,
        window_seconds=10,
    )
    assert single is None

    segment = build_active_alert_region_measurement(
        [
            event("node_A01", seconds_ago=1, latitude=25.0471, longitude=121.5383),
            event("node_A02", seconds_ago=2, latitude=25.0478, longitude=121.5402),
        ],
        reference_time=reference,
        window_seconds=10,
    )
    assert segment is not None
    assert segment["region_type"] == "segment"
    assert segment["reporting_node_count"] == 2
    assert segment["source"] == "active_alert_region"

    polygon = build_active_alert_region_measurement(
        [
            event("node_A01", seconds_ago=1, latitude=25.0471, longitude=121.5383),
            event("node_A02", seconds_ago=2, latitude=25.0478, longitude=121.5402),
            event("node_A03", seconds_ago=3, latitude=25.0465, longitude=121.5391),
        ],
        reference_time=reference,
        window_seconds=10,
    )
    assert polygon is not None
    assert polygon["region_type"] == "polygon"
    assert polygon["reporting_node_count"] == 3
    assert set(polygon["reporting_device_ids"]) == {"node_A01", "node_A02", "node_A03"}

    expired = build_active_alert_region_measurement(
        [
            event("node_A01", seconds_ago=1, latitude=25.0471, longitude=121.5383),
            event("node_A02", seconds_ago=60, latitude=25.0478, longitude=121.5402),
            event("node_A03", seconds_ago=60, latitude=25.0465, longitude=121.5391),
        ],
        reference_time=reference,
        window_seconds=10,
    )
    assert expired is None

    zero_zero = build_active_alert_region_measurement(
        [
            event("node_A01", seconds_ago=1, latitude=0.0, longitude=0.0),
            event("node_A02", seconds_ago=1, latitude=25.0478, longitude=121.5402),
            event("node_A03", seconds_ago=1, latitude=25.0465, longitude=121.5391),
        ],
        reference_time=reference,
        window_seconds=10,
    )
    assert zero_zero is not None
    assert zero_zero["region_type"] == "segment"
    assert zero_zero["reporting_node_count"] == 2

    delayed_backend_arrival = build_active_alert_region_measurement(
        [
            event(
                "node_A01",
                seconds_ago=70,
                observed_seconds_ago=1,
                latitude=25.0471,
                longitude=121.5383,
            ),
            event(
                "node_A02",
                seconds_ago=65,
                observed_seconds_ago=2,
                latitude=25.0478,
                longitude=121.5402,
            ),
            event(
                "node_A03",
                seconds_ago=60,
                observed_seconds_ago=3,
                latitude=25.0465,
                longitude=121.5391,
            ),
        ],
        reference_time=reference,
        window_seconds=10,
    )
    assert delayed_backend_arrival is not None
    assert delayed_backend_arrival["region_type"] == "polygon"
    assert delayed_backend_arrival["reporting_node_count"] == 3

    print("Live alert region tracking tests passed")


if __name__ == "__main__":
    main()
