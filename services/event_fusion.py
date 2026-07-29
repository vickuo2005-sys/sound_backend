import json
import re
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from services.device_location_service import location_map, resolve_effective_location
from services.region_localization import REGION_METHOD, estimate_region


ACTIVE_STATUS = "ACTIVE"
CLOSED_STATUS = "CLOSED"
FUSION_KIND = "fusion"
LOCAL_EVENT_TIMEZONE = timezone(timedelta(hours=8))
LOCAL_EVENT_TIME_FORMATS = (
    "%Y/%m/%d %H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
)
DEFAULT_EPISODE_HOLD_SECONDS = 30.0
DEFAULT_LATE_ATTACH_SECONDS = 30.0
DEFAULT_GROUP_MERGE_SECONDS = 30.0
MAX_DYNAMIC_WINDOW_SECONDS = 30.0
MAX_EPISODE_SPAN_SECONDS = 60.0
MERGED_FRAGMENT_KIND = "merged_fragment"
TIMING_METADATA_FIELDS = [
    "timing_version",
    "timing_source",
    "capture_start_time_ms",
    "event_start_sample",
    "event_end_sample",
    "rms_peak_sample",
    "sample_rate_hz",
    "channel_count",
    "audio_duration_ms",
    "device_event_time_ms",
    "event_end_time_ms",
    "rms_peak_time_ms",
]
AUDIO_METADATA_FIELDS = [
    "audio_format",
    "audio_size_bytes",
    "source_pcm_size_bytes",
    "audio_encoding_status",
    "tdoa_clip_path",
    "tdoa_clip_format",
    "tdoa_clip_size_bytes",
    "tdoa_clip_start_sample",
    "tdoa_clip_end_sample",
    "tdoa_clip_peak_sample",
    "tdoa_clip_duration_ms",
    "tdoa_clip_source",
]


def parse_datetime(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, str):
        text = value.strip()
        try:
            normalized = text.replace("Z", "+00:00")
            parsed = datetime.fromisoformat(normalized)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            pass

        for date_format in LOCAL_EVENT_TIME_FORMATS:
            try:
                parsed = datetime.strptime(text, date_format)
                return parsed.replace(tzinfo=LOCAL_EVENT_TIMEZONE).astimezone(
                    timezone.utc
                )
            except ValueError:
                continue
    return None


def serialize_row(row: Optional[dict]) -> Optional[dict]:
    if row is None:
        return None

    serialized = {}
    for key, value in dict(row).items():
        if hasattr(value, "isoformat"):
            serialized[key] = value.isoformat()
        else:
            serialized[key] = value
    return serialized


def parse_json_field(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None
    return value


def normalize_label(label: Any) -> str:
    normalized = str(label or "").strip().lower()
    if normalized in {"drone", "uav"}:
        return "drone"
    if normalized in {"aircraft", "plane", "airplane"}:
        return "aircraft"
    if normalized in {"non_aircraft", "non-aircraft", "other", "noise"}:
        return "non_aircraft"
    return normalized or "unknown"


def parse_note_field(note: Any, key: str) -> Optional[str]:
    if not note:
        return None
    match = re.search(rf"(?:^|,\s*){re.escape(key)}=([^,]+)", str(note))
    if not match:
        return None
    return match.group(1).strip()


def parse_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def parse_int(value: Any) -> Optional[int]:
    number = parse_float(value)
    if number is None:
        return None
    return int(round(number))


def epoch_ms_to_datetime(value: Any) -> Optional[datetime]:
    milliseconds = parse_float(value)
    if milliseconds is None:
        return None
    try:
        return datetime.fromtimestamp(milliseconds / 1000.0, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def ai_probability_from_event(event_record: dict) -> Optional[float]:
    for key in ("ai_probability", "aircraft_probability", "probability_aircraft"):
        probability = parse_float(event_record.get(key))
        if probability is not None:
            return max(0.0, min(1.0, probability))

    note = event_record.get("note")
    for key in ("probability_aircraft", "aircraft_probability"):
        probability = parse_float(parse_note_field(note, key))
        if probability is not None:
            return max(0.0, min(1.0, probability))
    return None


def event_timestamp(event_record: dict) -> datetime:
    parsed = (
        epoch_ms_to_datetime(event_record.get("corrected_arrival_time_ms"))
        or epoch_ms_to_datetime(event_record.get("rms_peak_time_ms"))
        or epoch_ms_to_datetime(event_record.get("device_event_time_ms"))
        or parse_datetime(event_record.get("timestamp"))
        or parse_datetime(event_record.get("created_at"))
        or datetime.now(timezone.utc)
    )
    return parsed


def dynamic_fusion_window_seconds(
    event_record: dict,
    base_window_seconds: float,
) -> float:
    base_window = max(1.0, float(base_window_seconds or 1.0))
    quality = str(event_record.get("time_sync_quality") or "").strip().lower()
    rtt_ms = parse_float(event_record.get("time_sync_rtt_ms"))
    sync_age_ms = parse_float(event_record.get("time_sync_age_ms"))
    duration_seconds = (parse_float(event_record.get("audio_duration_ms")) or 0.0) / 1000.0

    if quality in {"excellent", "good"}:
        window = max(base_window, 3.0)
    elif quality in {"fair", "degraded"}:
        window = max(base_window, 6.0)
    elif quality in {"poor", "bad"}:
        window = max(base_window, 10.0)
    else:
        window = max(base_window, 10.0)

    if rtt_ms is not None:
        if rtt_ms > 500:
            window += 4.0
        elif rtt_ms > 200:
            window += 2.0

    if sync_age_ms is not None:
        if sync_age_ms > 300_000:
            window += 4.0
        elif sync_age_ms > 120_000:
            window += 2.0

    if duration_seconds > 0:
        window = max(window, min(MAX_DYNAMIC_WINDOW_SECONDS, duration_seconds + 2.0))

    return min(MAX_DYNAMIC_WINDOW_SECONDS, window)


def db_time(value: datetime, is_postgres: bool) -> Any:
    if is_postgres:
        return value
    return value.isoformat()


def placeholder(is_postgres: bool) -> str:
    return "%s" if is_postgres else "?"


def fetchone_dict(cursor: Any) -> Optional[dict]:
    row = cursor.fetchone()
    if row is None:
        return None
    return dict(row)


def fetchall_dict(cursor: Any) -> list[dict]:
    return [dict(row) for row in cursor.fetchall()]


def execute(cursor: Any, is_postgres: bool, sql: str, params: tuple = ()) -> Any:
    if is_postgres:
        return cursor.execute(sql, params)
    return cursor.execute(sql.replace("%s", "?"), params)


@contextmanager
def open_cursor(connection: Any):
    cursor = connection.cursor()
    try:
        yield cursor
    finally:
        try:
            cursor.close()
        except Exception:
            pass


def lock_fusion_label(cursor: Any, label: str, is_postgres: bool) -> None:
    if not is_postgres:
        return
    cursor.execute(
        "SELECT pg_advisory_xact_lock(hashtext(%s))",
        (f"event_fusion:{label}",),
    )


def close_stale_groups(
    cursor: Any,
    label: str,
    event_time: datetime,
    window_seconds: float,
    is_postgres: bool,
    exclude_group_id: Optional[str] = None,
) -> None:
    cutoff = event_time - timedelta(seconds=window_seconds)
    exclude_clause = ""
    params: list[Any] = [
        CLOSED_STATUS,
        db_time(datetime.now(timezone.utc), is_postgres),
        FUSION_KIND,
        ACTIVE_STATUS,
        ACTIVE_STATUS,
        label,
        db_time(cutoff, is_postgres),
    ]
    if exclude_group_id:
        exclude_clause = " AND id <> %s"
        params.append(exclude_group_id)

    execute(
        cursor,
        is_postgres,
        f"""
        UPDATE event_groups
        SET status = %s,
            updated_at = %s
        WHERE COALESCE(group_kind, 'target_estimate') = %s
          AND COALESCE(status, %s) = %s
          AND COALESCE(label, group_label) = %s
          AND COALESCE(last_event_time, end_time) < %s
          {exclude_clause}
        """,
        tuple(params),
    )


def observation_group_for_event(
    cursor: Any,
    event_id: str,
    is_postgres: bool,
) -> Optional[dict]:
    execute(
        cursor,
        is_postgres,
        """
        SELECT g.*
        FROM event_group_observations o
        JOIN event_groups g ON g.id = o.group_id
        WHERE o.event_id = %s
          AND COALESCE(o.observation_kind, 'target_estimate') = %s
        LIMIT 1
        """,
        (event_id, FUSION_KIND),
    )
    row = fetchone_dict(cursor)
    if not row:
        return None
    return group_payload(cursor, row, is_postgres)


def interval_distance_seconds(row: dict, event_time: datetime) -> float:
    first_time = parse_datetime(
        row.get("first_event_time")
        or row.get("start_time")
        or row.get("last_event_time")
        or row.get("end_time")
    )
    last_time = parse_datetime(
        row.get("last_event_time")
        or row.get("end_time")
        or row.get("first_event_time")
        or row.get("start_time")
    )
    if first_time is None and last_time is None:
        return float("inf")
    if first_time is None:
        first_time = last_time
    if last_time is None:
        last_time = first_time
    if last_time < first_time:
        first_time, last_time = last_time, first_time
    if first_time <= event_time <= last_time:
        return 0.0
    if event_time < first_time:
        return (first_time - event_time).total_seconds()
    return (event_time - last_time).total_seconds()


def group_time_bounds(row: dict) -> tuple[Optional[datetime], Optional[datetime]]:
    first_time = parse_datetime(
        row.get("first_event_time")
        or row.get("start_time")
        or row.get("last_event_time")
        or row.get("end_time")
    )
    last_time = parse_datetime(
        row.get("last_event_time")
        or row.get("end_time")
        or row.get("first_event_time")
        or row.get("start_time")
    )
    if first_time and last_time and last_time < first_time:
        return last_time, first_time
    return first_time, last_time


def interval_gap_seconds(first: dict, second: dict) -> float:
    first_start, first_end = group_time_bounds(first)
    second_start, second_end = group_time_bounds(second)
    if first_start is None or first_end is None or second_start is None or second_end is None:
        return float("inf")
    if first_start <= second_end and second_start <= first_end:
        return 0.0
    if first_end < second_start:
        return (second_start - first_end).total_seconds()
    return (first_start - second_end).total_seconds()


def merged_span_seconds(first: dict, second: dict) -> float:
    values = [
        value
        for value in (*group_time_bounds(first), *group_time_bounds(second))
        if value is not None
    ]
    if len(values) < 2:
        return float("inf")
    return (max(values) - min(values)).total_seconds()


def find_candidate_group(
    cursor: Any,
    label: str,
    event_time: datetime,
    window_seconds: float,
    is_postgres: bool,
    late_attach_seconds: float = DEFAULT_LATE_ATTACH_SECONDS,
) -> Optional[dict]:
    search_seconds = max(window_seconds, late_attach_seconds)
    start = event_time - timedelta(seconds=search_seconds)
    end = event_time + timedelta(seconds=search_seconds)
    lock_clause = "FOR UPDATE" if is_postgres else ""
    execute(
        cursor,
        is_postgres,
        f"""
        SELECT *
        FROM event_groups
        WHERE COALESCE(group_kind, 'target_estimate') = %s
          AND COALESCE(label, group_label) = %s
          AND COALESCE(last_event_time, end_time, updated_at) >= %s
          AND COALESCE(first_event_time, start_time, last_event_time, end_time, updated_at) <= %s
        {lock_clause}
        """,
        (
            FUSION_KIND,
            label,
            db_time(start, is_postgres),
            db_time(end, is_postgres),
        ),
    )
    candidates = []
    for row in fetchall_dict(cursor):
        status = str(row.get("status") or ACTIVE_STATUS).upper()
        distance_seconds = interval_distance_seconds(row, event_time)
        allowed_seconds = late_attach_seconds if status == CLOSED_STATUS else window_seconds
        if distance_seconds <= allowed_seconds:
            candidates.append(row)
    if not candidates:
        return None

    def score(row: dict) -> tuple[float, int, int]:
        status = str(row.get("status") or ACTIVE_STATUS).upper()
        active_penalty = 0 if status == ACTIVE_STATUS else 1
        node_count = int(row.get("node_count") or 0)
        return (interval_distance_seconds(row, event_time), active_penalty, -node_count)

    return min(candidates, key=score)


def create_group(
    cursor: Any,
    label: str,
    event_time: datetime,
    is_postgres: bool,
) -> dict:
    now = datetime.now(timezone.utc)
    group_id = str(uuid.uuid4())
    execute(
        cursor,
        is_postgres,
        """
        INSERT INTO event_groups (
            id,
            group_kind,
            label,
            group_label,
            status,
            first_event_time,
            last_event_time,
            start_time,
            end_time,
            node_count,
            estimated_lat,
            estimated_lng,
            localization_method,
            method,
            confidence,
            created_at,
            updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NULL, NULL, NULL, NULL, NULL, %s, %s)
        """,
        (
            group_id,
            FUSION_KIND,
            label,
            label,
            ACTIVE_STATUS,
            db_time(event_time, is_postgres),
            db_time(event_time, is_postgres),
            db_time(event_time, is_postgres),
            db_time(event_time, is_postgres),
            0,
            db_time(now, is_postgres),
            db_time(now, is_postgres),
        ),
    )
    return {"id": group_id}


def insert_observation(
    cursor: Any,
    group_id: str,
    event_record: dict,
    label: str,
    event_time: datetime,
    is_postgres: bool,
) -> bool:
    now = datetime.now(timezone.utc)
    observation_id = str(uuid.uuid4())
    ai_probability = ai_probability_from_event(event_record)
    sql = """
        INSERT INTO event_group_observations (
            id,
            group_id,
            event_db_id,
            event_id,
            device_id,
            label,
            event_timestamp,
            latitude,
            longitude,
            rms_peak,
            ai_probability,
            aircraft_probability,
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
            time_sync_version,
            time_sync_offset_ms,
            time_sync_rtt_ms,
            time_sync_quality,
            time_sync_synced_at_ms,
            time_sync_age_ms,
            corrected_arrival_time_ms,
            created_at,
            observation_kind
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    params = (
        observation_id,
        group_id,
        event_record.get("id"),
        event_record.get("event_id"),
        event_record.get("device_id"),
        label,
        db_time(event_time, is_postgres),
        event_record.get("latitude"),
        event_record.get("longitude"),
        event_record.get("rms_peak"),
        ai_probability,
        ai_probability,
        event_record.get("audio_path"),
        event_record.get("audio_format"),
        parse_int(event_record.get("audio_size_bytes")),
        parse_int(event_record.get("source_pcm_size_bytes")),
        event_record.get("audio_encoding_status"),
        event_record.get("tdoa_clip_path"),
        event_record.get("tdoa_clip_format"),
        parse_int(event_record.get("tdoa_clip_size_bytes")),
        parse_int(event_record.get("tdoa_clip_start_sample")),
        parse_int(event_record.get("tdoa_clip_end_sample")),
        parse_int(event_record.get("tdoa_clip_peak_sample")),
        parse_int(event_record.get("tdoa_clip_duration_ms")),
        event_record.get("tdoa_clip_source"),
        parse_int(event_record.get("timing_version")),
        event_record.get("timing_source"),
        parse_int(event_record.get("capture_start_time_ms")),
        parse_int(event_record.get("event_start_sample")),
        parse_int(event_record.get("event_end_sample")),
        parse_int(event_record.get("rms_peak_sample")),
        parse_int(event_record.get("sample_rate_hz")),
        parse_int(event_record.get("channel_count")),
        parse_int(event_record.get("audio_duration_ms")),
        parse_int(event_record.get("device_event_time_ms")),
        parse_int(event_record.get("event_end_time_ms")),
        parse_int(event_record.get("rms_peak_time_ms")),
        parse_int(event_record.get("time_sync_version")),
        event_record.get("time_sync_offset_ms"),
        event_record.get("time_sync_rtt_ms"),
        event_record.get("time_sync_quality"),
        parse_int(event_record.get("time_sync_synced_at_ms")),
        parse_int(event_record.get("time_sync_age_ms")),
        event_record.get("corrected_arrival_time_ms"),
        db_time(now, is_postgres),
        FUSION_KIND,
    )
    if is_postgres:
        cursor.execute(
            f"{sql} ON CONFLICT DO NOTHING RETURNING id",
            params,
        )
        return cursor.fetchone() is not None

    cursor.execute(sql.replace("%s", "?").replace("INSERT INTO", "INSERT OR IGNORE INTO", 1), params)
    return cursor.rowcount > 0


def update_group_rollup(
    cursor: Any,
    group_id: str,
    is_postgres: bool,
    mark_active: bool = False,
) -> dict:
    execute(
        cursor,
        is_postgres,
        """
        SELECT
            MIN(event_timestamp) AS first_event_time,
            MAX(event_timestamp) AS last_event_time,
            COUNT(DISTINCT device_id) AS node_count
        FROM event_group_observations
        WHERE group_id = %s
          AND COALESCE(observation_kind, 'target_estimate') = %s
        """,
        (group_id, FUSION_KIND),
    )
    rollup = fetchone_dict(cursor) or {}
    now = datetime.now(timezone.utc)
    status_sql = ", status = %s" if mark_active else ""
    params: list[Any] = [
        rollup.get("first_event_time"),
        rollup.get("last_event_time"),
        rollup.get("first_event_time"),
        rollup.get("last_event_time"),
        int(rollup.get("node_count") or 0),
        db_time(now, is_postgres),
    ]
    if mark_active:
        params.append(ACTIVE_STATUS)
    params.append(group_id)
    execute(
        cursor,
        is_postgres,
        f"""
        UPDATE event_groups
        SET first_event_time = %s,
            last_event_time = %s,
            start_time = %s,
            end_time = %s,
            node_count = %s,
            updated_at = %s
            {status_sql}
        WHERE id = %s
        """,
        tuple(params),
    )
    update_group_region(cursor, group_id, is_postgres)
    execute(
        cursor,
        is_postgres,
        "SELECT * FROM event_groups WHERE id = %s LIMIT 1",
        (group_id,),
    )
    row = fetchone_dict(cursor) or {"id": group_id}
    return group_payload(cursor, row, is_postgres)


def load_group_row(cursor: Any, group_id: str, is_postgres: bool) -> Optional[dict]:
    execute(
        cursor,
        is_postgres,
        """
        SELECT *
        FROM event_groups
        WHERE id = %s
        LIMIT 1
        """,
        (group_id,),
    )
    return fetchone_dict(cursor)


def find_mergeable_group(
    cursor: Any,
    target_group: dict,
    label: str,
    is_postgres: bool,
    merge_gap_seconds: float = DEFAULT_GROUP_MERGE_SECONDS,
    max_episode_span_seconds: float = MAX_EPISODE_SPAN_SECONDS,
) -> Optional[dict]:
    target_start, target_end = group_time_bounds(target_group)
    if target_start is None or target_end is None:
        return None

    search_start = target_start - timedelta(seconds=merge_gap_seconds)
    search_end = target_end + timedelta(seconds=merge_gap_seconds)
    lock_clause = "FOR UPDATE" if is_postgres else ""
    execute(
        cursor,
        is_postgres,
        f"""
        SELECT *
        FROM event_groups
        WHERE id <> %s
          AND COALESCE(group_kind, 'target_estimate') = %s
          AND COALESCE(label, group_label) = %s
          AND COALESCE(last_event_time, end_time, updated_at) >= %s
          AND COALESCE(first_event_time, start_time, last_event_time, end_time, updated_at) <= %s
        {lock_clause}
        """,
        (
            target_group.get("id"),
            FUSION_KIND,
            label,
            db_time(search_start, is_postgres),
            db_time(search_end, is_postgres),
        ),
    )

    candidates = []
    for row in fetchall_dict(cursor):
        gap_seconds = interval_gap_seconds(target_group, row)
        span_seconds = merged_span_seconds(target_group, row)
        if gap_seconds <= merge_gap_seconds and span_seconds <= max_episode_span_seconds:
            node_count = int(row.get("node_count") or 0)
            candidates.append((gap_seconds, -node_count, row))

    if not candidates:
        return None
    return min(candidates, key=lambda item: (item[0], item[1]))[2]


def merge_group_into(
    cursor: Any,
    source_group_id: str,
    target_group_id: str,
    is_postgres: bool,
) -> None:
    execute(
        cursor,
        is_postgres,
        """
        UPDATE event_group_observations
        SET group_id = %s
        WHERE group_id = %s
          AND COALESCE(observation_kind, 'target_estimate') = %s
        """,
        (target_group_id, source_group_id, FUSION_KIND),
    )
    execute(
        cursor,
        is_postgres,
        """
        UPDATE event_groups
        SET group_kind = %s,
            status = %s,
            updated_at = %s
        WHERE id = %s
        """,
        (
            MERGED_FRAGMENT_KIND,
            CLOSED_STATUS,
            db_time(datetime.now(timezone.utc), is_postgres),
            source_group_id,
        ),
    )


def merge_nearby_groups(
    cursor: Any,
    group_id: str,
    label: str,
    is_postgres: bool,
    merge_gap_seconds: float = DEFAULT_GROUP_MERGE_SECONDS,
    max_episode_span_seconds: float = MAX_EPISODE_SPAN_SECONDS,
) -> list[str]:
    merged_ids: list[str] = []
    while True:
        target_group = load_group_row(cursor, group_id, is_postgres)
        if not target_group:
            return merged_ids

        source_group = find_mergeable_group(
            cursor=cursor,
            target_group=target_group,
            label=label,
            is_postgres=is_postgres,
            merge_gap_seconds=merge_gap_seconds,
            max_episode_span_seconds=max_episode_span_seconds,
        )
        if not source_group:
            return merged_ids

        source_group_id = str(source_group.get("id") or "")
        if not source_group_id:
            return merged_ids
        merge_group_into(
            cursor=cursor,
            source_group_id=source_group_id,
            target_group_id=group_id,
            is_postgres=is_postgres,
        )
        merged_ids.append(source_group_id)
        update_group_rollup(cursor, group_id, is_postgres, mark_active=True)


def group_region_observations(cursor: Any, group_id: str, is_postgres: bool) -> list[dict]:
    execute(
        cursor,
        is_postgres,
        """
        SELECT
            device_id,
            latitude,
            longitude,
            label,
            event_timestamp
        FROM event_group_observations
        WHERE group_id = %s
          AND COALESCE(observation_kind, 'target_estimate') = %s
          AND device_id IS NOT NULL
        ORDER BY device_id ASC, event_timestamp ASC, created_at ASC
        """,
        (group_id, FUSION_KIND),
    )
    rows = fetchall_dict(cursor)
    device_ids = [str(row.get("device_id") or "") for row in rows if row.get("device_id")]
    fixed_locations = fixed_locations_for_devices(cursor, device_ids, is_postgres)
    resolved_rows = []
    for row in rows:
        effective = resolve_effective_location(
            device_id=row.get("device_id"),
            event_latitude=row.get("latitude"),
            event_longitude=row.get("longitude"),
            fixed_locations=fixed_locations,
        )
        if effective:
            resolved_rows.append(
                {
                    **row,
                    "raw_latitude": row.get("latitude"),
                    "raw_longitude": row.get("longitude"),
                    "latitude": effective["latitude"],
                    "longitude": effective["longitude"],
                    "effective_location_source": effective[
                        "effective_location_source"
                    ],
                }
            )
        else:
            resolved_rows.append(
                {
                    **row,
                    "raw_latitude": row.get("latitude"),
                    "raw_longitude": row.get("longitude"),
                    "latitude": None,
                    "longitude": None,
                    "effective_location_source": "none",
                }
            )
    return resolved_rows


def fixed_locations_for_devices(
    cursor: Any,
    device_ids: list[str],
    is_postgres: bool,
) -> dict[str, dict]:
    unique_device_ids = sorted({device_id for device_id in device_ids if device_id})
    if not unique_device_ids:
        return {}

    placeholders = ", ".join(["%s"] * len(unique_device_ids))
    execute(
        cursor,
        is_postgres,
        f"""
        SELECT device_id, latitude, longitude, location_source,
               accuracy_m, created_at, updated_at
        FROM device_locations
        WHERE device_id IN ({placeholders})
        """,
        tuple(unique_device_ids),
    )
    return location_map(fetchall_dict(cursor))


def update_group_region(cursor: Any, group_id: str, is_postgres: bool) -> dict:
    region = estimate_region(group_region_observations(cursor, group_id, is_postgres))
    now = datetime.now(timezone.utc)
    geojson = (
        json.dumps(region.get("region_geojson"), separators=(",", ":"))
        if region.get("region_geojson") is not None
        else None
    )
    device_ids_json = json.dumps(region.get("reporting_device_ids") or [], separators=(",", ":"))

    if is_postgres:
        cursor.execute(
            """
            UPDATE event_groups
            SET region_type = %s,
                region_center_lat = %s,
                region_center_lng = %s,
                region_geojson = %s::jsonb,
                reporting_node_count = %s,
                reporting_device_ids = %s::jsonb,
                region_updated_at = %s,
                estimated_lat = %s,
                estimated_lng = %s,
                localization_method = %s,
                method = %s,
                confidence = NULL,
                tdoa_residual_rmse_m = NULL,
                tdoa_node_count = NULL,
                time_sync_quality = NULL,
                updated_at = %s
            WHERE id = %s
            """,
            (
                region.get("region_type"),
                region.get("region_center_lat"),
                region.get("region_center_lng"),
                geojson,
                region.get("reporting_node_count"),
                device_ids_json,
                db_time(now, is_postgres),
                region.get("region_center_lat"),
                region.get("region_center_lng"),
                REGION_METHOD,
                REGION_METHOD,
                db_time(now, is_postgres),
                group_id,
            ),
        )
        return region

    cursor.execute(
        """
        UPDATE event_groups
        SET region_type = ?,
            region_center_lat = ?,
            region_center_lng = ?,
            region_geojson = ?,
            reporting_node_count = ?,
            reporting_device_ids = ?,
            region_updated_at = ?,
            estimated_lat = ?,
            estimated_lng = ?,
            localization_method = ?,
            method = ?,
            confidence = NULL,
            tdoa_residual_rmse_m = NULL,
            tdoa_node_count = NULL,
            time_sync_quality = NULL,
            updated_at = ?
        WHERE id = ?
        """,
        (
            region.get("region_type"),
            region.get("region_center_lat"),
            region.get("region_center_lng"),
            geojson,
            region.get("reporting_node_count"),
            device_ids_json,
            db_time(now, is_postgres),
            region.get("region_center_lat"),
            region.get("region_center_lng"),
            REGION_METHOD,
            REGION_METHOD,
            db_time(now, is_postgres),
            group_id,
        ),
    )
    return region


def active_group_ids_for_device(
    cursor: Any,
    device_id: str,
    is_postgres: bool,
) -> list[str]:
    execute(
        cursor,
        is_postgres,
        """
        SELECT DISTINCT o.group_id
        FROM event_group_observations o
        JOIN event_groups g ON g.id = o.group_id
        WHERE o.device_id = %s
          AND COALESCE(o.observation_kind, 'target_estimate') = %s
          AND COALESCE(g.group_kind, 'target_estimate') = %s
          AND UPPER(COALESCE(g.status, %s)) = %s
        """,
        (device_id, FUSION_KIND, FUSION_KIND, ACTIVE_STATUS, ACTIVE_STATUS),
    )
    return [str(row["group_id"]) for row in fetchall_dict(cursor) if row.get("group_id")]


def recompute_active_regions_for_device(
    connection: Any,
    device_id: str,
    is_postgres: bool,
) -> list[dict]:
    with open_cursor(connection) as cursor:
        group_ids = active_group_ids_for_device(cursor, device_id, is_postgres)
        return [
            update_group_rollup(cursor, group_id, is_postgres)
            for group_id in group_ids
        ]


def update_existing_observation_snapshot(
    cursor: Any,
    event_record: dict,
    is_postgres: bool,
) -> None:
    event_id = event_record.get("event_id")
    if not event_id:
        return

    execute(
        cursor,
        is_postgres,
        """
        UPDATE event_group_observations
        SET audio_path = %s,
            audio_format = %s,
            audio_size_bytes = %s,
            source_pcm_size_bytes = %s,
            audio_encoding_status = %s,
            tdoa_clip_path = %s,
            tdoa_clip_format = %s,
            tdoa_clip_size_bytes = %s,
            tdoa_clip_start_sample = %s,
            tdoa_clip_end_sample = %s,
            tdoa_clip_peak_sample = %s,
            tdoa_clip_duration_ms = %s,
            tdoa_clip_source = %s,
            timing_version = %s,
            timing_source = %s,
            capture_start_time_ms = %s,
            event_start_sample = %s,
            event_end_sample = %s,
            rms_peak_sample = %s,
            sample_rate_hz = %s,
            channel_count = %s,
            audio_duration_ms = %s,
            device_event_time_ms = %s,
            event_end_time_ms = %s,
            rms_peak_time_ms = %s,
            time_sync_version = %s,
            time_sync_offset_ms = %s,
            time_sync_rtt_ms = %s,
            time_sync_quality = %s,
            time_sync_synced_at_ms = %s,
            time_sync_age_ms = %s,
            corrected_arrival_time_ms = %s
        WHERE event_id = %s
          AND COALESCE(observation_kind, 'target_estimate') = %s
        """,
        (
            event_record.get("audio_path"),
            event_record.get("audio_format"),
            parse_int(event_record.get("audio_size_bytes")),
            parse_int(event_record.get("source_pcm_size_bytes")),
            event_record.get("audio_encoding_status"),
            event_record.get("tdoa_clip_path"),
            event_record.get("tdoa_clip_format"),
            parse_int(event_record.get("tdoa_clip_size_bytes")),
            parse_int(event_record.get("tdoa_clip_start_sample")),
            parse_int(event_record.get("tdoa_clip_end_sample")),
            parse_int(event_record.get("tdoa_clip_peak_sample")),
            parse_int(event_record.get("tdoa_clip_duration_ms")),
            event_record.get("tdoa_clip_source"),
            parse_int(event_record.get("timing_version")),
            event_record.get("timing_source"),
            parse_int(event_record.get("capture_start_time_ms")),
            parse_int(event_record.get("event_start_sample")),
            parse_int(event_record.get("event_end_sample")),
            parse_int(event_record.get("rms_peak_sample")),
            parse_int(event_record.get("sample_rate_hz")),
            parse_int(event_record.get("channel_count")),
            parse_int(event_record.get("audio_duration_ms")),
            parse_int(event_record.get("device_event_time_ms")),
            parse_int(event_record.get("event_end_time_ms")),
            parse_int(event_record.get("rms_peak_time_ms")),
            parse_int(event_record.get("time_sync_version")),
            event_record.get("time_sync_offset_ms"),
            event_record.get("time_sync_rtt_ms"),
            event_record.get("time_sync_quality"),
            parse_int(event_record.get("time_sync_synced_at_ms")),
            parse_int(event_record.get("time_sync_age_ms")),
            event_record.get("corrected_arrival_time_ms"),
            event_id,
            FUSION_KIND,
        ),
    )


def group_devices(cursor: Any, group_id: str, is_postgres: bool) -> list[str]:
    execute(
        cursor,
        is_postgres,
        """
        SELECT DISTINCT device_id
        FROM event_group_observations
        WHERE group_id = %s
          AND COALESCE(observation_kind, 'target_estimate') = %s
          AND device_id IS NOT NULL
        ORDER BY device_id ASC
        """,
        (group_id, FUSION_KIND),
    )
    return [str(row["device_id"]) for row in fetchall_dict(cursor)]


def group_payload(cursor: Any, row: dict, is_postgres: bool) -> dict:
    serialized = serialize_row(row) or {}
    group_id = serialized.get("id")
    devices = group_devices(cursor, group_id, is_postgres) if group_id else []
    reporting_device_ids = parse_json_field(serialized.get("reporting_device_ids"))
    if not isinstance(reporting_device_ids, list):
        reporting_device_ids = devices
    region_geojson = parse_json_field(serialized.get("region_geojson"))
    region_center_lat = serialized.get("region_center_lat")
    region_center_lng = serialized.get("region_center_lng")
    reporting_node_count = serialized.get("reporting_node_count")
    if reporting_node_count is None:
        reporting_node_count = len(reporting_device_ids)
    estimated_lat = serialized.get("estimated_lat")
    if estimated_lat is None:
        estimated_lat = region_center_lat
    estimated_lng = serialized.get("estimated_lng")
    if estimated_lng is None:
        estimated_lng = region_center_lng
    return {
        "id": group_id,
        "label": serialized.get("label") or serialized.get("group_label"),
        "status": serialized.get("status") or ACTIVE_STATUS,
        "created_at": serialized.get("created_at"),
        "updated_at": serialized.get("updated_at"),
        "first_event_time": serialized.get("first_event_time") or serialized.get("start_time"),
        "last_event_time": serialized.get("last_event_time") or serialized.get("end_time"),
        "node_count": serialized.get("node_count") or len(devices),
        "region_type": serialized.get("region_type"),
        "region_center_lat": region_center_lat,
        "region_center_lng": region_center_lng,
        "region_geojson": region_geojson,
        "reporting_node_count": reporting_node_count,
        "reporting_device_ids": reporting_device_ids,
        "region_updated_at": serialized.get("region_updated_at"),
        "estimated_lat": estimated_lat,
        "estimated_lng": estimated_lng,
        "localization_method": serialized.get("localization_method")
        or serialized.get("method")
        or (REGION_METHOD if serialized.get("region_type") else None),
        "confidence": serialized.get("confidence"),
        "devices": devices,
    }


def process_event(
    connection: Any,
    event_record: dict,
    is_postgres: bool,
    window_seconds: float = 3.0,
) -> Optional[dict]:
    event_id = event_record.get("event_id")
    if not event_id:
        return None

    label = normalize_label(event_record.get("label"))
    event_time = event_timestamp(event_record)
    fusion_window_seconds = dynamic_fusion_window_seconds(event_record, window_seconds)
    late_attach_seconds = max(DEFAULT_LATE_ATTACH_SECONDS, fusion_window_seconds)
    episode_hold_seconds = max(DEFAULT_EPISODE_HOLD_SECONDS, late_attach_seconds)

    with open_cursor(connection) as cursor:
        lock_fusion_label(cursor, label, is_postgres)

        existing_group = observation_group_for_event(cursor, event_id, is_postgres)
        if existing_group:
            update_existing_observation_snapshot(cursor, event_record, is_postgres)
            return update_group_rollup(cursor, existing_group["id"], is_postgres)

        group = find_candidate_group(
            cursor,
            label,
            event_time,
            fusion_window_seconds,
            is_postgres,
            late_attach_seconds=late_attach_seconds,
        )
        if not group:
            close_stale_groups(
                cursor,
                label,
                event_time,
                episode_hold_seconds,
                is_postgres,
            )
            group = create_group(cursor, label, event_time, is_postgres)

        inserted = insert_observation(
            cursor=cursor,
            group_id=group["id"],
            event_record=event_record,
            label=label,
            event_time=event_time,
            is_postgres=is_postgres,
        )
        if not inserted:
            return observation_group_for_event(cursor, event_id, is_postgres)

        updated_group = update_group_rollup(
            cursor,
            group["id"],
            is_postgres,
            mark_active=True,
        )
        merged_group_ids = merge_nearby_groups(
            cursor=cursor,
            group_id=group["id"],
            label=label,
            is_postgres=is_postgres,
        )
        if merged_group_ids:
            updated_group = update_group_rollup(
                cursor,
                group["id"],
                is_postgres,
                mark_active=True,
            )
            updated_group["merged_group_ids"] = merged_group_ids
        close_stale_groups(
            cursor,
            label,
            event_time,
            episode_hold_seconds,
            is_postgres,
            exclude_group_id=group["id"],
        )
        return updated_group


def list_event_groups(
    connection: Any,
    is_postgres: bool,
    limit: int = 20,
    status: Optional[str] = None,
    label: Optional[str] = None,
) -> list[dict]:
    safe_limit = max(1, min(int(limit or 20), 100))
    params: list[Any] = [FUSION_KIND]
    filters = ["COALESCE(group_kind, 'target_estimate') = %s"]

    if status:
        filters.append("UPPER(COALESCE(status, %s)) = %s")
        params.extend([ACTIVE_STATUS, status.strip().upper()])

    if label:
        filters.append("COALESCE(label, group_label) = %s")
        params.append(normalize_label(label))

    params.append(safe_limit)
    where_clause = " AND ".join(filters)
    with open_cursor(connection) as cursor:
        execute(
            cursor,
            is_postgres,
            f"""
            SELECT *
            FROM event_groups
            WHERE {where_clause}
            ORDER BY COALESCE(last_event_time, end_time, updated_at) DESC
            LIMIT %s
            """,
            tuple(params),
        )
        rows = fetchall_dict(cursor)
        return [group_payload(cursor, row, is_postgres) for row in rows]


def get_event_group_detail(
    connection: Any,
    group_id: str,
    is_postgres: bool,
) -> Optional[dict]:
    with open_cursor(connection) as cursor:
        execute(
            cursor,
            is_postgres,
            """
            SELECT *
            FROM event_groups
            WHERE id = %s
              AND COALESCE(group_kind, 'target_estimate') = %s
            LIMIT 1
            """,
            (group_id, FUSION_KIND),
        )
        group = fetchone_dict(cursor)
        if not group:
            return None

        payload = group_payload(cursor, group, is_postgres)
        execute(
            cursor,
            is_postgres,
            """
            SELECT
                event_id,
                event_db_id,
                device_id,
                label,
                event_timestamp,
                latitude,
                longitude,
                rms_peak,
                ai_probability,
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
                time_sync_version,
                time_sync_offset_ms,
                time_sync_rtt_ms,
                time_sync_quality,
                time_sync_synced_at_ms,
                time_sync_age_ms,
                corrected_arrival_time_ms,
                created_at
            FROM event_group_observations
            WHERE group_id = %s
              AND COALESCE(observation_kind, 'target_estimate') = %s
            ORDER BY event_timestamp ASC
            """,
            (group_id, FUSION_KIND),
        )
        observations = [serialize_row(row) for row in fetchall_dict(cursor)]
        payload["observations"] = observations
        return payload
