import asyncio
import os
import sys
import tempfile
import time
from datetime import datetime, timezone

os.environ["DATABASE_URL"] = ""
os.environ["LOCALIZATION_ENABLED"] = "true"
os.environ["UPLOAD_TOKEN"] = "test-only-token"

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import main  # noqa: E402
from services.localization.geo import xy_to_latlng  # noqa: E402
from services.localization.timestamp_tdoa import SOUND_SPEED_MPS  # noqa: E402


async def run_pipeline() -> None:
    original_db = main.DB_NAME
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        main.DB_NAME = path
        main.init_sqlite_db()
        origin_lat = 25.033
        origin_lng = 121.565
        nodes = [(-120.0, -100.0), (120.0, -100.0), (0.0, 130.0)]
        target_x = 30.0
        target_y = 20.0
        base_time_ms = 1_780_000_000_000.0
        timestamp = datetime(2026, 7, 22, 4, 0, 0, tzinfo=timezone.utc).isoformat()

        for index, (x, y) in enumerate(nodes, start=1):
            lat, lng = xy_to_latlng(x, y, origin_lat, origin_lng)
            distance_m = ((target_x - x) ** 2 + (target_y - y) ** 2) ** 0.5
            corrected_arrival = base_time_ms + distance_m / SOUND_SPEED_MPS * 1000.0
            device_time = corrected_arrival - 12.0
            event = main.SoundEvent(
                event_id=f"pipeline_evt_{index}",
                device_id=f"node_A0{index}",
                timestamp=timestamp,
                latitude=lat,
                longitude=lng,
                rms_peak=1000.0,
                label="aircraft",
                note="probability_aircraft=0.95, confidence=0.95",
                device_event_time_ms=device_time,
                time_sync_version=1,
                time_sync_offset_ms=12.0,
                time_sync_rtt_ms=20.0,
                time_sync_quality="good",
                time_sync_synced_at_ms=int(device_time - 1000),
                time_sync_age_ms=1000,
            )
            await main.create_event(event, upload_token="test-only-token")

        groups = []
        group = None
        localizations = []
        success_localization = None
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            await asyncio.sleep(0.1)
            groups = main.list_event_fusion_groups(limit=5)
            if not groups:
                continue
            group = next(
                (item for item in groups if item.get("node_count") == 3),
                None,
            )
            if not group:
                continue
            localizations = main.list_localization_results(limit=10, group_id=group["id"])
            success_localization = next(
                (
                    item
                    for item in localizations
                    if item.get("status") == "SUCCESS"
                    and item.get("method") == "timestamp_tdoa"
                ),
                None,
            )
            if success_localization:
                break

        assert groups, "expected fusion group"
        assert group, groups

        assert localizations, "expected localization result"
        assert success_localization, localizations

        tracks = main.list_tracks(limit=10)
        assert tracks, "expected track"
        assert tracks[0]["point_count"] >= 1, tracks[0]
        print("Localization pipeline tests passed")
    finally:
        main.DB_NAME = original_db
        try:
            os.remove(path)
        except OSError:
            pass


if __name__ == "__main__":
    asyncio.run(run_pipeline())
