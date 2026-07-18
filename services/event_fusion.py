import re
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Optional


ACTIVE_STATUS = "ACTIVE"
CLOSED_STATUS = "CLOSED"
FUSION_KIND = "fusion"


def parse_datetime(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    if isinstance(value, str):
        try:
            normalized = value.replace("Z", "+00:00")
            parsed = datetime.fromisoformat(normalized)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            return None
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
        parse_datetime(event_record.get("timestamp"))
        or parse_datetime(event_record.get("created_at"))
        or datetime.now(timezone.utc)
    )
    return parsed


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
) -> None:
    cutoff = event_time - timedelta(seconds=window_seconds)
    execute(
        cursor,
        is_postgres,
        """
        UPDATE event_groups
        SET status = %s,
            updated_at = %s
        WHERE COALESCE(group_kind, 'target_estimate') = %s
          AND COALESCE(status, %s) = %s
          AND COALESCE(label, group_label) = %s
          AND COALESCE(last_event_time, end_time) < %s
        """,
        (
            CLOSED_STATUS,
            db_time(datetime.now(timezone.utc), is_postgres),
            FUSION_KIND,
            ACTIVE_STATUS,
            ACTIVE_STATUS,
            label,
            db_time(cutoff, is_postgres),
        ),
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


def find_candidate_group(
    cursor: Any,
    label: str,
    event_time: datetime,
    window_seconds: float,
    is_postgres: bool,
) -> Optional[dict]:
    start = event_time - timedelta(seconds=window_seconds)
    end = event_time + timedelta(seconds=window_seconds)
    lock_clause = "FOR UPDATE" if is_postgres else ""
    execute(
        cursor,
        is_postgres,
        f"""
        SELECT *
        FROM event_groups
        WHERE COALESCE(group_kind, 'target_estimate') = %s
          AND COALESCE(status, %s) = %s
          AND COALESCE(label, group_label) = %s
          AND COALESCE(last_event_time, end_time) >= %s
          AND COALESCE(last_event_time, end_time) <= %s
        {lock_clause}
        """,
        (
            FUSION_KIND,
            ACTIVE_STATUS,
            ACTIVE_STATUS,
            label,
            db_time(start, is_postgres),
            db_time(end, is_postgres),
        ),
    )
    candidates = fetchall_dict(cursor)
    if not candidates:
        return None

    def distance(row: dict) -> float:
        group_time = parse_datetime(row.get("last_event_time") or row.get("end_time"))
        if group_time is None:
            return float("inf")
        return abs((event_time - group_time).total_seconds())

    return min(candidates, key=distance)


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
            created_at,
            observation_kind
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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


def update_group_rollup(cursor: Any, group_id: str, is_postgres: bool) -> dict:
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
    execute(
        cursor,
        is_postgres,
        """
        UPDATE event_groups
        SET first_event_time = %s,
            last_event_time = %s,
            start_time = %s,
            end_time = %s,
            node_count = %s,
            updated_at = %s
        WHERE id = %s
        """,
        (
            rollup.get("first_event_time"),
            rollup.get("last_event_time"),
            rollup.get("first_event_time"),
            rollup.get("last_event_time"),
            int(rollup.get("node_count") or 0),
            db_time(now, is_postgres),
            group_id,
        ),
    )
    execute(
        cursor,
        is_postgres,
        "SELECT * FROM event_groups WHERE id = %s LIMIT 1",
        (group_id,),
    )
    row = fetchone_dict(cursor) or {"id": group_id}
    return group_payload(cursor, row, is_postgres)


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
    return {
        "id": group_id,
        "label": serialized.get("label") or serialized.get("group_label"),
        "status": serialized.get("status") or ACTIVE_STATUS,
        "created_at": serialized.get("created_at"),
        "updated_at": serialized.get("updated_at"),
        "first_event_time": serialized.get("first_event_time") or serialized.get("start_time"),
        "last_event_time": serialized.get("last_event_time") or serialized.get("end_time"),
        "node_count": serialized.get("node_count") or len(devices),
        "estimated_lat": serialized.get("estimated_lat"),
        "estimated_lng": serialized.get("estimated_lng"),
        "localization_method": serialized.get("localization_method")
        or serialized.get("method"),
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

    with open_cursor(connection) as cursor:
        lock_fusion_label(cursor, label, is_postgres)
        close_stale_groups(cursor, label, event_time, window_seconds, is_postgres)

        existing_group = observation_group_for_event(cursor, event_id, is_postgres)
        if existing_group:
            return existing_group

        group = find_candidate_group(cursor, label, event_time, window_seconds, is_postgres)
        if not group:
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

        return update_group_rollup(cursor, group["id"], is_postgres)


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
