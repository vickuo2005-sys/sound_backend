import os
import asyncio
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.event_fusion import (  # noqa: E402
    get_event_group_detail,
    list_event_groups,
    parse_datetime,
    process_event,
)


def make_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        CREATE TABLE events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT UNIQUE,
            device_id TEXT,
            timestamp TEXT,
            latitude REAL,
            longitude REAL,
            rms_peak REAL,
            label TEXT,
            audio_path TEXT,
            audio_format TEXT,
            audio_size_bytes INTEGER,
            source_pcm_size_bytes INTEGER,
            audio_encoding_status TEXT,
            tdoa_clip_path TEXT,
            tdoa_clip_format TEXT,
            tdoa_clip_size_bytes INTEGER,
            tdoa_clip_start_sample INTEGER,
            tdoa_clip_end_sample INTEGER,
            tdoa_clip_peak_sample INTEGER,
            tdoa_clip_duration_ms INTEGER,
            tdoa_clip_source TEXT,
            note TEXT,
            timing_version INTEGER,
            timing_source TEXT,
            capture_start_time_ms INTEGER,
            event_start_sample INTEGER,
            event_end_sample INTEGER,
            rms_peak_sample INTEGER,
            sample_rate_hz INTEGER,
            channel_count INTEGER,
            audio_duration_ms INTEGER,
            device_event_time_ms INTEGER,
            event_end_time_ms INTEGER,
            rms_peak_time_ms INTEGER,
            created_at TEXT
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE event_groups (
            id TEXT PRIMARY KEY,
            group_kind TEXT DEFAULT 'fusion',
            label TEXT,
            group_label TEXT,
            status TEXT DEFAULT 'ACTIVE',
            first_event_time TEXT,
            last_event_time TEXT,
            start_time TEXT,
            end_time TEXT,
            node_count INTEGER DEFAULT 0,
            estimated_lat REAL,
            estimated_lng REAL,
            localization_method TEXT,
            method TEXT,
            confidence REAL,
            created_at TEXT,
            updated_at TEXT
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE event_group_observations (
            id TEXT PRIMARY KEY,
            group_id TEXT,
            event_db_id INTEGER,
            event_id TEXT,
            device_id TEXT,
            label TEXT,
            event_timestamp TEXT,
            latitude REAL,
            longitude REAL,
            rms_peak REAL,
            ai_probability REAL,
            aircraft_probability REAL,
            audio_path TEXT,
            audio_format TEXT,
            audio_size_bytes INTEGER,
            source_pcm_size_bytes INTEGER,
            audio_encoding_status TEXT,
            tdoa_clip_path TEXT,
            tdoa_clip_format TEXT,
            tdoa_clip_size_bytes INTEGER,
            tdoa_clip_start_sample INTEGER,
            tdoa_clip_end_sample INTEGER,
            tdoa_clip_peak_sample INTEGER,
            tdoa_clip_duration_ms INTEGER,
            tdoa_clip_source TEXT,
            timing_version INTEGER,
            timing_source TEXT,
            capture_start_time_ms INTEGER,
            event_start_sample INTEGER,
            event_end_sample INTEGER,
            rms_peak_sample INTEGER,
            sample_rate_hz INTEGER,
            channel_count INTEGER,
            audio_duration_ms INTEGER,
            device_event_time_ms INTEGER,
            event_end_time_ms INTEGER,
            rms_peak_time_ms INTEGER,
            created_at TEXT,
            observation_kind TEXT DEFAULT 'fusion'
        )
        """
    )
    connection.execute(
        """
        CREATE UNIQUE INDEX event_group_observations_fusion_event_id_key
        ON event_group_observations (event_id)
        WHERE observation_kind = 'fusion'
        """
    )
    return connection


def add_event(
    connection: sqlite3.Connection,
    event_id: str,
    device_id: str,
    label: str,
    event_time: datetime,
) -> dict:
    created_at = event_time.isoformat()
    cursor = connection.execute(
        """
        INSERT INTO events (
            event_id,
            device_id,
            timestamp,
            latitude,
            longitude,
            rms_peak,
            label,
            audio_path,
            audio_format,
            audio_size_bytes,
            source_pcm_size_bytes,
            audio_encoding_status,
            tdoa_clip_path,
            tdoa_clip_format,
            tdoa_clip_size_bytes,
            tdoa_clip_start_sample,
            tdoa_clip_end_sample,
            tdoa_clip_peak_sample,
            tdoa_clip_duration_ms,
            tdoa_clip_source,
            note,
            timing_version,
            timing_source,
            capture_start_time_ms,
            event_start_sample,
            event_end_sample,
            rms_peak_sample,
            sample_rate_hz,
            channel_count,
            audio_duration_ms,
            device_event_time_ms,
            event_end_time_ms,
            rms_peak_time_ms,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_id,
            device_id,
            event_time.isoformat(),
            25.033 + (hash(device_id) % 10) * 0.0001,
            121.565 + (hash(event_id) % 10) * 0.0001,
            0.8,
            label,
            f"audio/drone/{device_id}/20260718/{event_id}.mp3",
            "mp3",
            24000,
            160000,
            "MP3_SUCCESS",
            f"audio/drone/{device_id}/20260718/{event_id}_tdoa_clip.wav",
            "wav",
            64044,
            26000,
            58000,
            16000,
            2000,
            "RMS_PEAK",
            "probability_aircraft=0.900000, confidence=0.900000",
            1,
            "PCM_SAMPLE_INDEX",
            int(event_time.timestamp() * 1000) - 2000,
            32000,
            80000,
            42000,
            16000,
            1,
            5000,
            int(event_time.timestamp() * 1000),
            int(event_time.timestamp() * 1000) + 3000,
            int(event_time.timestamp() * 1000) + 625,
            created_at,
        ),
    )
    connection.commit()
    row = connection.execute(
        "SELECT * FROM events WHERE id = ?",
        (cursor.lastrowid,),
    ).fetchone()
    return dict(row)


def observation_count(connection: sqlite3.Connection) -> int:
    row = connection.execute(
        """
        SELECT COUNT(*) AS total
        FROM event_group_observations
        WHERE observation_kind = 'fusion'
        """
    ).fetchone()
    return int(row["total"])


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def run_service_tests() -> None:
    connection = make_connection()
    base = datetime(2026, 7, 18, 4, 0, 0, tzinfo=timezone.utc)

    parsed_local_time = parse_datetime("2026/07/18 16:47:41")
    assert_equal(
        parsed_local_time,
        datetime(2026, 7, 18, 8, 47, 41, tzinfo=timezone.utc),
        "Test 0 local APP timestamp parsing",
    )

    group1 = process_event(
        connection,
        add_event(connection, "evt_a01_000", "node_A01", "aircraft", base),
        is_postgres=False,
        window_seconds=3,
    )
    assert_equal(group1["node_count"], 1, "Test 1 node_count")

    group1b = process_event(
        connection,
        add_event(connection, "evt_a02_001", "node_A02", "aircraft", base + timedelta(seconds=1)),
        is_postgres=False,
        window_seconds=3,
    )
    assert_equal(group1b["id"], group1["id"], "Test 2 group id")
    assert_equal(group1b["node_count"], 2, "Test 2 node_count")

    a03_record = add_event(connection, "evt_a03_002", "node_A03", "aircraft", base + timedelta(seconds=2))
    group1c = process_event(
        connection,
        a03_record,
        is_postgres=False,
        window_seconds=3,
    )
    assert_equal(group1c["id"], group1["id"], "Test 3 group id")
    assert_equal(group1c["node_count"], 3, "Test 3 node_count")

    before_duplicate = observation_count(connection)
    duplicate = process_event(
        connection,
        dict(a03_record),
        is_postgres=False,
        window_seconds=3,
    )
    after_duplicate = observation_count(connection)
    assert_equal(duplicate["id"], group1["id"], "Test 4 duplicate group id")
    assert_equal(after_duplicate, before_duplicate, "Test 4 duplicate observation count")

    refreshed_record = dict(a03_record)
    refreshed_record["audio_path"] = "audio/drone/node_A03/20260718/evt_a03_002_updated.mp3"
    refreshed_record["audio_size_bytes"] = 18000
    refreshed_record["audio_encoding_status"] = "MP3_SUCCESS"
    refreshed_record["tdoa_clip_path"] = (
        "audio/drone/node_A03/20260718/evt_a03_002_tdoa_clip.wav"
    )
    refreshed = process_event(
        connection,
        refreshed_record,
        is_postgres=False,
        window_seconds=3,
    )
    assert_equal(refreshed["id"], group1["id"], "Test 4b refreshed group id")
    assert_equal(observation_count(connection), before_duplicate, "Test 4b observation count")
    refreshed_detail = get_event_group_detail(connection, group1["id"], is_postgres=False)
    refreshed_observation = next(
        item
        for item in refreshed_detail["observations"]
        if item["event_id"] == "evt_a03_002"
    )
    assert_equal(
        refreshed_observation["audio_path"],
        refreshed_record["audio_path"],
        "Test 4b audio_path refreshed",
    )
    assert_equal(
        refreshed_observation["audio_size_bytes"],
        18000,
        "Test 4b audio_size_bytes refreshed",
    )

    same_device = process_event(
        connection,
        add_event(connection, "evt_a01_003", "node_A01", "aircraft", base + timedelta(seconds=2.5)),
        is_postgres=False,
        window_seconds=3,
    )
    assert_equal(same_device["id"], group1["id"], "Test 5 same device group id")
    assert_equal(same_device["node_count"], 3, "Test 5 distinct node_count")

    group2 = process_event(
        connection,
        add_event(connection, "evt_a04_008", "node_A04", "aircraft", base + timedelta(seconds=8)),
        is_postgres=False,
        window_seconds=3,
    )
    if group2["id"] == group1["id"]:
        raise AssertionError("Test 6 expected a new group after fusion window")

    other_group = process_event(
        connection,
        add_event(connection, "evt_other_009", "node_A02", "non_aircraft", base + timedelta(seconds=2)),
        is_postgres=False,
        window_seconds=3,
    )
    if other_group["id"] == group1["id"]:
        raise AssertionError("Test 7 expected a different group for different label")

    groups = list_event_groups(connection, is_postgres=False, limit=2)
    assert_equal(len(groups), 2, "Test 9 limit")
    detail = get_event_group_detail(connection, group1["id"], is_postgres=False)
    assert_equal(len(detail["observations"]), 4, "Test 10 observation detail count")
    timed_observation = detail["observations"][0]
    assert_equal(
        timed_observation["timing_source"],
        "PCM_SAMPLE_INDEX",
        "Test 11 timing source copied",
    )
    assert_equal(
        timed_observation["event_start_sample"],
        32000,
        "Test 11 event_start_sample copied",
    )
    assert_equal(
        timed_observation["sample_rate_hz"],
        16000,
        "Test 11 sample_rate_hz copied",
    )
    assert_equal(
        timed_observation["audio_format"],
        "mp3",
        "Test 12 audio_format copied",
    )
    assert_equal(
        timed_observation["tdoa_clip_format"],
        "wav",
        "Test 12 tdoa_clip_format copied",
    )


def run_route_failure_test() -> None:
    os.environ.pop("DATABASE_URL", None)
    os.environ["UPLOAD_TOKEN"] = "test-token-123"

    import main  # noqa: E402

    original_db_name = main.DB_NAME
    original_fusion = main.process_event_fusion_for_event
    original_logger_disabled = main.logger.disabled
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
        main.DB_NAME = str(Path(temp_dir) / "sound_events.db")
        main.init_sqlite_db()
        main.logger.disabled = True

        def failing_fusion(event_id: str):
            raise RuntimeError(f"forced fusion failure for {event_id}")

        main.process_event_fusion_for_event = failing_fusion
        result = asyncio.run(
            main.create_event(
                main.SoundEvent(
                    event_id="evt_failure_safe",
                    device_id="node_A99",
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    latitude=25.033,
                    longitude=121.565,
                    duration_s=1.2,
                    rms_peak=0.75,
                    label="aircraft",
                    note="probability_aircraft=0.900000, confidence=0.900000",
                    timing_version=1,
                    timing_source="PCM_SAMPLE_INDEX",
                    capture_start_time_ms=1000000,
                    event_start_sample=16000,
                    event_end_sample=64000,
                    rms_peak_sample=28000,
                    sample_rate_hz=16000,
                    channel_count=1,
                    device_event_time_ms=1001000,
                    event_end_time_ms=1004000,
                    rms_peak_time_ms=1001750,
                    audio_duration_ms=4000,
                ),
                upload_token="test-token-123",
            )
        )
        assert_equal(result["status"], "success", "Test 8 POST status")
        with sqlite3.connect(main.DB_NAME) as connection:
            row = connection.execute(
                """
                SELECT timing_source, event_start_sample, sample_rate_hz
                FROM events
                WHERE event_id = ?
                """,
                ("evt_failure_safe",),
            ).fetchone()
            assert_equal(row[0], "PCM_SAMPLE_INDEX", "Test 8 timing source persisted")
            assert_equal(row[1], 16000, "Test 8 event_start_sample persisted")
            assert_equal(row[2], 16000, "Test 8 sample_rate_hz persisted")

    main.process_event_fusion_for_event = original_fusion
    main.DB_NAME = original_db_name
    main.logger.disabled = original_logger_disabled


def main() -> None:
    run_service_tests()
    run_route_failure_test()
    print("Event Fusion tests passed")


if __name__ == "__main__":
    main()
