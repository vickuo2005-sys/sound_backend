import asyncio
import os
import sqlite3
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.pop("DATABASE_URL", None)
os.environ.setdefault("UPLOAD_TOKEN", "test-only-token")

import main  # noqa: E402


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def assert_close(actual, expected, message: str, tolerance: float = 0.001) -> None:
    if actual is None or abs(float(actual) - expected) > tolerance:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def run_quality_tests() -> None:
    assert_equal(main.time_sync_quality_from_rtt(None), "missing", "No RTT")
    assert_equal(main.time_sync_quality_from_rtt(-1), "missing", "Negative RTT")
    assert_equal(main.time_sync_quality_from_rtt(20), "good", "Good RTT")
    assert_equal(main.time_sync_quality_from_rtt(100), "medium", "Medium RTT")
    assert_equal(main.time_sync_quality_from_rtt(250), "poor", "Poor RTT")
    assert_equal(main.time_sync_quality_from_rtt(450), "bad", "Bad RTT")
    assert_equal(
        main.normalize_time_sync_quality("STALE", 20),
        "stale",
        "Explicit stale quality",
    )
    assert_equal(
        main.normalize_time_sync_quality("unexpected", 120),
        "medium",
        "Fallback quality from RTT",
    )


def run_time_sync_route_test() -> None:
    payload = main.time_sync()
    assert_equal(payload["status"], "success", "time-sync status")
    if not isinstance(payload["server_time_ms"], int):
        raise AssertionError("server_time_ms should be an integer")
    assert_equal(
        payload["algorithm"],
        "client_midpoint_offset",
        "time-sync algorithm",
    )
    assert_equal(
        payload["quality_thresholds_ms"]["good"],
        50,
        "time-sync good threshold",
    )


def run_location_update_tests() -> None:
    original_db_name = main.DB_NAME
    try:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            main.DB_NAME = str(Path(temp_dir) / "sound_events.db")
            main.init_sqlite_db()

            row = main.upsert_device_location(
                device_id="node_SYNC",
                latitude=25.033,
                longitude=121.565,
                is_listening=True,
                upload_mode="detection",
                time_sync_offset_ms=12.5,
                time_sync_rtt_ms=42.3,
                time_sync_quality="good",
                time_sync_at="2026-07-18T12:00:00+00:00",
            )
            assert_equal(row["device_id"], "node_SYNC", "Initial device_id")
            assert_close(row["time_sync_offset_ms"], 12.5, "Initial offset")
            assert_close(row["time_sync_rtt_ms"], 42.3, "Initial RTT")
            assert_equal(row["time_sync_quality"], "good", "Initial quality")
            assert_equal(
                row["time_sync_at"],
                "2026-07-18T12:00:00+00:00",
                "Initial primary sync timestamp",
            )
            assert_equal(
                row["last_time_sync_at"],
                "2026-07-18T12:00:00+00:00",
                "Initial compatibility sync timestamp",
            )

            response = asyncio.run(
                main.update_location(
                    main.LocationUpdate(
                        device_id="node_SYNC",
                        latitude=25.034,
                        longitude=121.566,
                        is_listening=False,
                        upload_mode="collection",
                        time_sync_offset_ms=-3.25,
                        time_sync_rtt_ms=180,
                    )
                )
            )
            assert_equal(response["status"], "success", "Route update status")
            assert_equal(response["time_sync_quality"], "poor", "Route quality")
            assert_close(response["time_sync_rtt_ms"], 180, "Route RTT")

            status_payload = main.device_status()
            assert_equal(status_payload["count"], 1, "Device status count")
            device = status_payload["devices"][0]
            assert_close(device["latitude"], 25.034, "Updated latitude")
            assert_close(device["longitude"], 121.566, "Updated longitude")
            assert_close(device["time_sync_offset_ms"], -3.25, "Updated offset")
            assert_close(device["time_sync_rtt_ms"], 180, "Updated RTT")
            assert_equal(device["time_sync_quality"], "poor", "Updated quality")
            if not device["time_sync_at"]:
                raise AssertionError("time_sync_at should be filled when offset exists")
            if not device["last_time_sync_at"]:
                raise AssertionError("last_time_sync_at should be filled for compatibility")

            legacy_event_row = main.upsert_device_event_status(
                main.SoundEvent(
                    event_id="evt_legacy_no_sync",
                    device_id="node_SYNC",
                    timestamp="2026-07-18T12:01:00+00:00",
                    latitude=25.034,
                    longitude=121.566,
                    label="aircraft",
                )
            )
            assert_close(
                legacy_event_row["time_sync_rtt_ms"],
                180,
                "Legacy event preserves RTT",
            )
            assert_equal(
                legacy_event_row["time_sync_quality"],
                "poor",
                "Legacy event preserves quality",
            )
            assert_equal(
                legacy_event_row["time_sync_at"],
                device["time_sync_at"],
                "Legacy event preserves primary sync timestamp",
            )

            synced_event_row = main.upsert_device_event_status(
                main.SoundEvent(
                    event_id="evt_with_sync",
                    device_id="node_SYNC",
                    timestamp="2026-07-18T12:02:00+00:00",
                    latitude=25.034,
                    longitude=121.566,
                    label="aircraft",
                    device_event_time_ms=1_784_350_000_000,
                    time_sync_offset_ms=4.0,
                    time_sync_rtt_ms=20,
                )
            )
            assert_close(synced_event_row["time_sync_rtt_ms"], 20, "Event sync RTT")
            assert_equal(
                synced_event_row["time_sync_quality"],
                "good",
                "Event sync quality",
            )
            if not synced_event_row["time_sync_at"]:
                raise AssertionError("Synced event should refresh time_sync_at")
    finally:
        main.DB_NAME = original_db_name


def run_event_time_sync_snapshot_tests() -> None:
    original_db_name = main.DB_NAME
    original_logger_disabled = main.logger.disabled
    try:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            main.DB_NAME = str(Path(temp_dir) / "sound_events.db")
            main.init_sqlite_db()
            main.logger.disabled = True

            result = asyncio.run(
                main.create_event(
                    main.SoundEvent(
                        event_id="evt_time_sync_snapshot",
                        device_id="node_SYNC_A01",
                        timestamp="2026-07-18T12:03:00+00:00",
                        latitude=25.033,
                        longitude=121.565,
                        duration_s=2.0,
                        rms_peak=0.8,
                        label="aircraft",
                        note="probability_aircraft=0.900000, confidence=0.900000",
                        timing_version=1,
                        timing_source="PCM_SAMPLE_INDEX",
                        capture_start_time_ms=999000,
                        event_start_sample=16000,
                        event_end_sample=48000,
                        rms_peak_sample=32000,
                        sample_rate_hz=16000,
                        channel_count=1,
                        audio_duration_ms=3000,
                        device_event_time_ms=1_000_000,
                        event_end_time_ms=1_002_000,
                        rms_peak_time_ms=1_000_000,
                        time_sync_version=1,
                        time_sync_offset_ms=12.5,
                        time_sync_rtt_ms=30,
                        time_sync_quality="good",
                        time_sync_synced_at_ms=999_900,
                        time_sync_age_ms=100,
                    ),
                    upload_token="test-only-token",
                )
            )
            assert_equal(result["status"], "success", "Event snapshot POST status")

            with sqlite3.connect(main.DB_NAME) as connection:
                connection.row_factory = sqlite3.Row
                event = dict(
                    connection.execute(
                        """
                        SELECT
                            time_sync_version,
                            time_sync_offset_ms,
                            time_sync_rtt_ms,
                            time_sync_quality,
                            time_sync_synced_at_ms,
                            time_sync_age_ms,
                            corrected_arrival_time_ms,
                            timing_quality
                        FROM events
                        WHERE event_id = ?
                        """,
                        ("evt_time_sync_snapshot",),
                    ).fetchone()
                )
                assert_equal(event["time_sync_version"], 1, "Event sync version")
                assert_close(event["time_sync_offset_ms"], 12.5, "Event sync offset")
                assert_close(event["time_sync_rtt_ms"], 30, "Event sync RTT")
                assert_equal(event["time_sync_quality"], "good", "Event sync quality")
                assert_equal(event["time_sync_synced_at_ms"], 999_900, "Event sync time")
                assert_equal(event["time_sync_age_ms"], 100, "Event sync age")
                assert_close(
                    event["corrected_arrival_time_ms"],
                    1_000_012.5,
                    "Event corrected arrival",
                )
                assert_equal(event["timing_quality"], "good", "Event timing quality")

                observation = dict(
                    connection.execute(
                        """
                        SELECT
                            time_sync_version,
                            time_sync_offset_ms,
                            time_sync_rtt_ms,
                            time_sync_quality,
                            time_sync_synced_at_ms,
                            time_sync_age_ms,
                            corrected_arrival_time_ms
                        FROM event_group_observations
                        WHERE event_id = ?
                        """,
                        ("evt_time_sync_snapshot",),
                    ).fetchone()
                )
                for key in (
                    "time_sync_version",
                    "time_sync_offset_ms",
                    "time_sync_rtt_ms",
                    "time_sync_quality",
                    "time_sync_synced_at_ms",
                    "time_sync_age_ms",
                    "corrected_arrival_time_ms",
                ):
                    assert_equal(observation[key], event[key], f"Observation snapshot {key}")

            stale = main.SoundEvent(
                event_id="evt_time_sync_stale",
                device_id="node_SYNC_A02",
                timestamp="2026-07-18T12:04:00+00:00",
                latitude=25.034,
                longitude=121.566,
                label="aircraft",
                device_event_time_ms=2_000_000,
                time_sync_version=1,
                time_sync_offset_ms=-10,
                time_sync_rtt_ms=40,
                time_sync_synced_at_ms=1_800_000,
                time_sync_age_ms=int(main.TIME_SYNC_MAX_AGE_SECONDS * 1000) + 1,
            )
            main.sanitize_time_sync_metadata(stale)
            assert_equal(
                main.timing_quality_for_event(stale),
                "stale",
                "Stale timing quality",
            )
            assert_close(
                main.corrected_arrival_time_ms(stale),
                1_999_990,
                "Stale corrected arrival still preserved",
            )
    finally:
        main.DB_NAME = original_db_name
        main.logger.disabled = original_logger_disabled


def main_entry() -> None:
    run_quality_tests()
    run_time_sync_route_test()
    run_location_update_tests()
    run_event_time_sync_snapshot_tests()
    print("Time sync tests passed")


if __name__ == "__main__":
    main_entry()
