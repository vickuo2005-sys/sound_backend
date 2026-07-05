import json
import os
import re
import sqlite3
import csv
from datetime import datetime, timedelta, timezone
from io import StringIO
from typing import Any, Optional
from urllib.parse import quote

from fastapi import (
    FastAPI,
    File,
    Form,
    Header,
    HTTPException,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.responses import HTMLResponse, Response
from google.cloud import storage
from google.oauth2 import service_account
from pydantic import BaseModel


app = FastAPI()

DB_NAME = "sound_events.db"
DEFAULT_UPLOAD_TOKEN = "test-token-123"


class DashboardConnectionManager:
    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict) -> None:
        disconnected = []
        for websocket in list(self.active_connections):
            try:
                await websocket.send_json(message)
            except Exception:
                disconnected.append(websocket)

        for websocket in disconnected:
            self.disconnect(websocket)


dashboard_manager = DashboardConnectionManager()


class SoundEvent(BaseModel):
    event_id: str
    device_id: str
    timestamp: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    duration_s: Optional[float] = None
    rms_peak: Optional[float] = None
    label: Optional[str] = None
    audio_file_name: Optional[str] = None
    local_audio_path: Optional[str] = None
    audio_path: Optional[str] = None
    note: Optional[str] = None


class LocationUpdate(BaseModel):
    device_id: str
    latitude: float
    longitude: float
    is_listening: Optional[bool] = None
    upload_mode: Optional[str] = None
    battery: Optional[int] = None
    ai_status: Optional[str] = None
    backend_status: Optional[str] = None
    app_status: Optional[str] = None
    last_ai_label: Optional[str] = None
    last_upload_status: Optional[str] = None


class DeviceCommandCreate(BaseModel):
    device_id: str
    command: str
    value: Optional[Any] = None
    issued_by: Optional[str] = "dashboard"


class DeviceCommandAck(BaseModel):
    command_id: int
    device_id: str
    status: str
    message: Optional[str] = None


def current_time_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def current_date_yyyymmdd() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d")


SUPPORTED_DEVICE_COMMANDS = {
    "start_listening",
    "stop_listening",
    "set_detection_mode",
    "set_collection_mode",
}


def command_value_to_text(value: Optional[Any]) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


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


def status_from_last_seen(last_seen: Any, stored_status: Optional[str]) -> str:
    seen_at = parse_datetime(last_seen)
    if seen_at is None:
        return stored_status or "offline"
    if datetime.now(timezone.utc) - seen_at > timedelta(seconds=15):
        return "offline"
    return stored_status or "online"


EVENT_COLUMNS = [
    "id",
    "event_id",
    "device_id",
    "timestamp",
    "latitude",
    "longitude",
    "duration_s",
    "rms_peak",
    "label",
    "audio_file_name",
    "local_audio_path",
    "audio_path",
    "note",
    "created_at",
]

DEVICE_STATUS_COLUMNS = [
    "device_id",
    "latitude",
    "longitude",
    "last_seen",
    "status",
    "is_listening",
    "upload_mode",
    "battery",
    "ai_status",
    "backend_status",
    "app_status",
    "last_ai_label",
    "last_upload_status",
    "last_event_id",
    "last_event_at",
    "last_command_id",
    "updated_at",
]

DEVICE_COMMAND_COLUMNS = [
    "id",
    "device_id",
    "command",
    "value",
    "status",
    "issued_by",
    "created_at",
    "executed_at",
    "ack_message",
]


def get_database_url() -> str:
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        return ""

    if "sslmode=" not in database_url:
        separator = "&" if "?" in database_url else "?"
        database_url = f"{database_url}{separator}sslmode=require"

    return database_url


def use_postgres() -> bool:
    return bool(get_database_url())


def require_postgres() -> None:
    if not use_postgres():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="DATABASE_URL is not configured",
        )


def get_postgres_connection():
    import psycopg2
    import psycopg2.extras

    return psycopg2.connect(
        get_database_url(),
        cursor_factory=psycopg2.extras.RealDictCursor,
    )


def get_sqlite_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_NAME)
    connection.row_factory = sqlite3.Row
    return connection


def add_sqlite_column_if_missing(
    connection: sqlite3.Connection,
    table_name: str,
    column_name: str,
    column_definition: str,
) -> None:
    columns = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    existing_columns = {column["name"] for column in columns}

    if column_name not in existing_columns:
        connection.execute(
            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}"
        )


def init_sqlite_db() -> None:
    with get_sqlite_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT,
                device_id TEXT,
                timestamp TEXT,
                latitude REAL,
                longitude REAL,
                duration_s REAL,
                rms_peak REAL,
                label TEXT,
                audio_file_name TEXT,
                local_audio_path TEXT,
                audio_path TEXT,
                note TEXT,
                created_at TEXT
            )
            """
        )
        add_sqlite_column_if_missing(
            connection=connection,
            table_name="events",
            column_name="audio_path",
            column_definition="TEXT",
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS device_status (
                device_id TEXT PRIMARY KEY,
                latitude REAL,
                longitude REAL,
                last_seen TEXT,
                status TEXT DEFAULT 'online',
                is_listening INTEGER,
                upload_mode TEXT,
                battery INTEGER,
                ai_status TEXT,
                backend_status TEXT,
                app_status TEXT,
                last_ai_label TEXT,
                last_upload_status TEXT,
                last_event_id TEXT,
                last_event_at TEXT,
                last_command_id INTEGER,
                updated_at TEXT
            )
            """
        )
        for column_name, column_definition in [
            ("latitude", "REAL"),
            ("longitude", "REAL"),
            ("last_seen", "TEXT"),
            ("status", "TEXT DEFAULT 'online'"),
            ("is_listening", "INTEGER"),
            ("upload_mode", "TEXT"),
            ("battery", "INTEGER"),
            ("ai_status", "TEXT"),
            ("backend_status", "TEXT"),
            ("app_status", "TEXT"),
            ("last_ai_label", "TEXT"),
            ("last_upload_status", "TEXT"),
            ("last_event_id", "TEXT"),
            ("last_event_at", "TEXT"),
            ("last_command_id", "INTEGER"),
            ("updated_at", "TEXT"),
        ]:
            add_sqlite_column_if_missing(
                connection=connection,
                table_name="device_status",
                column_name=column_name,
                column_definition=column_definition,
            )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS device_commands (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NOT NULL,
                command TEXT NOT NULL,
                value TEXT,
                status TEXT DEFAULT 'pending',
                issued_by TEXT,
                created_at TEXT,
                executed_at TEXT,
                ack_message TEXT
            )
            """
        )
        for column_name, column_definition in [
            ("device_id", "TEXT"),
            ("command", "TEXT"),
            ("value", "TEXT"),
            ("status", "TEXT DEFAULT 'pending'"),
            ("issued_by", "TEXT"),
            ("created_at", "TEXT"),
            ("executed_at", "TEXT"),
            ("ack_message", "TEXT"),
        ]:
            add_sqlite_column_if_missing(
                connection=connection,
                table_name="device_commands",
                column_name=column_name,
                column_definition=column_definition,
            )
        connection.commit()


def init_postgres_db() -> None:
    connection = get_postgres_connection()
    try:
        with connection:
            with connection.cursor() as cursor:
                columns = ", ".join(DEVICE_STATUS_COLUMNS)
                cursor.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS events (
                        id BIGSERIAL PRIMARY KEY,
                        event_id TEXT NOT NULL,
                        device_id TEXT,
                        timestamp TEXT,
                        latitude DOUBLE PRECISION,
                        longitude DOUBLE PRECISION,
                        duration_s DOUBLE PRECISION,
                        rms_peak DOUBLE PRECISION,
                        label TEXT,
                        audio_file_name TEXT,
                        local_audio_path TEXT,
                        audio_path TEXT,
                        note TEXT,
                        created_at TEXT
                    )
                    """
                )
                cursor.execute("ALTER TABLE events ADD COLUMN IF NOT EXISTS event_id TEXT")
                cursor.execute("ALTER TABLE events ADD COLUMN IF NOT EXISTS device_id TEXT")
                cursor.execute("ALTER TABLE events ADD COLUMN IF NOT EXISTS timestamp TEXT")
                cursor.execute(
                    "ALTER TABLE events ADD COLUMN IF NOT EXISTS latitude DOUBLE PRECISION"
                )
                cursor.execute(
                    "ALTER TABLE events ADD COLUMN IF NOT EXISTS longitude DOUBLE PRECISION"
                )
                cursor.execute(
                    "ALTER TABLE events ADD COLUMN IF NOT EXISTS duration_s DOUBLE PRECISION"
                )
                cursor.execute(
                    "ALTER TABLE events ADD COLUMN IF NOT EXISTS rms_peak DOUBLE PRECISION"
                )
                cursor.execute("ALTER TABLE events ADD COLUMN IF NOT EXISTS label TEXT")
                cursor.execute(
                    "ALTER TABLE events ADD COLUMN IF NOT EXISTS audio_file_name TEXT"
                )
                cursor.execute(
                    "ALTER TABLE events ADD COLUMN IF NOT EXISTS local_audio_path TEXT"
                )
                cursor.execute(
                    "ALTER TABLE events ADD COLUMN IF NOT EXISTS audio_path TEXT"
                )
                cursor.execute("ALTER TABLE events ADD COLUMN IF NOT EXISTS note TEXT")
                cursor.execute(
                    "ALTER TABLE events ADD COLUMN IF NOT EXISTS created_at TEXT"
                )
                cursor.execute(
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS events_event_id_key
                    ON events (event_id)
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS device_status (
                        device_id TEXT PRIMARY KEY,
                        latitude DOUBLE PRECISION,
                        longitude DOUBLE PRECISION,
                        last_seen TIMESTAMPTZ DEFAULT now(),
                        status TEXT DEFAULT 'online',
                        is_listening BOOLEAN,
                        upload_mode TEXT,
                        battery INTEGER,
                        ai_status TEXT,
                        backend_status TEXT,
                        app_status TEXT,
                        last_ai_label TEXT,
                        last_upload_status TEXT,
                        last_event_id TEXT,
                        last_event_at TIMESTAMPTZ,
                        last_command_id BIGINT,
                        updated_at TIMESTAMPTZ DEFAULT now()
                    )
                    """
                )
                for statement in [
                    "ALTER TABLE device_status ADD COLUMN IF NOT EXISTS latitude DOUBLE PRECISION",
                    "ALTER TABLE device_status ADD COLUMN IF NOT EXISTS longitude DOUBLE PRECISION",
                    "ALTER TABLE device_status ADD COLUMN IF NOT EXISTS last_seen TIMESTAMPTZ DEFAULT now()",
                    "ALTER TABLE device_status ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'online'",
                    "ALTER TABLE device_status ADD COLUMN IF NOT EXISTS is_listening BOOLEAN",
                    "ALTER TABLE device_status ADD COLUMN IF NOT EXISTS upload_mode TEXT",
                    "ALTER TABLE device_status ADD COLUMN IF NOT EXISTS battery INTEGER",
                    "ALTER TABLE device_status ADD COLUMN IF NOT EXISTS ai_status TEXT",
                    "ALTER TABLE device_status ADD COLUMN IF NOT EXISTS backend_status TEXT",
                    "ALTER TABLE device_status ADD COLUMN IF NOT EXISTS app_status TEXT",
                    "ALTER TABLE device_status ADD COLUMN IF NOT EXISTS last_ai_label TEXT",
                    "ALTER TABLE device_status ADD COLUMN IF NOT EXISTS last_upload_status TEXT",
                    "ALTER TABLE device_status ADD COLUMN IF NOT EXISTS last_event_id TEXT",
                    "ALTER TABLE device_status ADD COLUMN IF NOT EXISTS last_event_at TIMESTAMPTZ",
                    "ALTER TABLE device_status ADD COLUMN IF NOT EXISTS last_command_id BIGINT",
                    "ALTER TABLE device_status ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT now()",
                ]:
                    cursor.execute(statement)
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS device_commands (
                        id BIGSERIAL PRIMARY KEY,
                        device_id TEXT NOT NULL,
                        command TEXT NOT NULL,
                        value TEXT,
                        status TEXT DEFAULT 'pending',
                        issued_by TEXT,
                        created_at TIMESTAMPTZ DEFAULT now(),
                        executed_at TIMESTAMPTZ,
                        ack_message TEXT
                    )
                    """
                )
                for statement in [
                    "ALTER TABLE device_commands ADD COLUMN IF NOT EXISTS device_id TEXT",
                    "ALTER TABLE device_commands ADD COLUMN IF NOT EXISTS command TEXT",
                    "ALTER TABLE device_commands ADD COLUMN IF NOT EXISTS value TEXT",
                    "ALTER TABLE device_commands ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'pending'",
                    "ALTER TABLE device_commands ADD COLUMN IF NOT EXISTS issued_by TEXT",
                    "ALTER TABLE device_commands ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT now()",
                    "ALTER TABLE device_commands ADD COLUMN IF NOT EXISTS executed_at TIMESTAMPTZ",
                    "ALTER TABLE device_commands ADD COLUMN IF NOT EXISTS ack_message TEXT",
                ]:
                    cursor.execute(statement)
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS device_commands_pending_idx
                    ON device_commands (device_id, status, created_at)
                    """
                )
    finally:
        connection.close()


def init_db() -> None:
    if use_postgres():
        init_postgres_db()
    else:
        init_sqlite_db()


def event_values(event: SoundEvent, created_at: str) -> tuple:
    return (
        event.event_id,
        event.device_id,
        event.timestamp,
        event.latitude,
        event.longitude,
        event.duration_s,
        event.rms_peak,
        event.label,
        event.audio_file_name,
        event.local_audio_path,
        event.audio_path,
        event.note,
        created_at,
    )


def upsert_event_postgres(event: SoundEvent, created_at: str) -> int:
    connection = get_postgres_connection()
    try:
        with connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO events (
                        event_id,
                        device_id,
                        timestamp,
                        latitude,
                        longitude,
                        duration_s,
                        rms_peak,
                        label,
                        audio_file_name,
                        local_audio_path,
                        audio_path,
                        note,
                        created_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (event_id) DO UPDATE SET
                        device_id = EXCLUDED.device_id,
                        timestamp = EXCLUDED.timestamp,
                        latitude = EXCLUDED.latitude,
                        longitude = EXCLUDED.longitude,
                        duration_s = EXCLUDED.duration_s,
                        rms_peak = EXCLUDED.rms_peak,
                        label = EXCLUDED.label,
                        audio_file_name = EXCLUDED.audio_file_name,
                        local_audio_path = EXCLUDED.local_audio_path,
                        audio_path = EXCLUDED.audio_path,
                        note = EXCLUDED.note,
                        created_at = EXCLUDED.created_at
                    RETURNING id
                    """,
                    event_values(event, created_at),
                )
                row = cursor.fetchone()
                return int(row["id"])
    finally:
        connection.close()


def upsert_event_sqlite(event: SoundEvent, created_at: str) -> int:
    with get_sqlite_connection() as connection:
        existing = connection.execute(
            "SELECT id FROM events WHERE event_id = ? LIMIT 1",
            (event.event_id,),
        ).fetchone()

        if existing:
            db_id = int(existing["id"])
            connection.execute(
                """
                UPDATE events
                SET
                    device_id = ?,
                    timestamp = ?,
                    latitude = ?,
                    longitude = ?,
                    duration_s = ?,
                    rms_peak = ?,
                    label = ?,
                    audio_file_name = ?,
                    local_audio_path = ?,
                    audio_path = ?,
                    note = ?,
                    created_at = ?
                WHERE id = ?
                """,
                (
                    event.device_id,
                    event.timestamp,
                    event.latitude,
                    event.longitude,
                    event.duration_s,
                    event.rms_peak,
                    event.label,
                    event.audio_file_name,
                    event.local_audio_path,
                    event.audio_path,
                    event.note,
                    created_at,
                    db_id,
                ),
            )
        else:
            cursor = connection.execute(
                """
                INSERT INTO events (
                    event_id,
                    device_id,
                    timestamp,
                    latitude,
                    longitude,
                    duration_s,
                    rms_peak,
                    label,
                    audio_file_name,
                    local_audio_path,
                    audio_path,
                    note,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                event_values(event, created_at),
            )
            db_id = int(cursor.lastrowid)

        connection.commit()
        return db_id


def save_event(event: SoundEvent, created_at: str) -> int:
    if use_postgres():
        return upsert_event_postgres(event, created_at)
    return upsert_event_sqlite(event, created_at)


def update_event_audio_path(event_id: str, audio_path: str) -> None:
    if use_postgres():
        connection = get_postgres_connection()
        try:
            with connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        UPDATE events
                        SET audio_path = %s
                        WHERE event_id = %s
                        """,
                        (audio_path, event_id),
                    )
        finally:
            connection.close()
        return

    with get_sqlite_connection() as connection:
        connection.execute(
            """
            UPDATE events
            SET audio_path = ?
            WHERE event_id = ?
            """,
            (audio_path, event_id),
        )
        connection.commit()


def list_recent_events() -> list[dict]:
    columns = ", ".join(EVENT_COLUMNS)

    if use_postgres():
        connection = get_postgres_connection()
        try:
            with connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        f"""
                        SELECT {columns}
                        FROM events
                        ORDER BY id DESC
                        LIMIT 50
                        """
                    )
                    return [dict(row) for row in cursor.fetchall()]
        finally:
            connection.close()

    with get_sqlite_connection() as connection:
        rows = connection.execute(
            f"""
            SELECT {columns}
            FROM events
            ORDER BY id DESC
            LIMIT 50
            """
        ).fetchall()

    return [dict(row) for row in rows]


def serialize_db_row(row: dict) -> dict:
    serialized = {}
    for key, value in row.items():
        if hasattr(value, "isoformat"):
            serialized[key] = value.isoformat()
        else:
            serialized[key] = value
    if "is_listening" in serialized and serialized["is_listening"] is not None:
        serialized["is_listening"] = bool(serialized["is_listening"])
    if "status" in serialized:
        serialized["status"] = status_from_last_seen(
            serialized.get("last_seen"),
            serialized.get("status"),
        )
    return serialized


def upsert_device_location(
    device_id: str,
    latitude: float,
    longitude: float,
    is_listening: Optional[bool] = None,
    upload_mode: Optional[str] = None,
    battery: Optional[int] = None,
    ai_status: Optional[str] = None,
    backend_status: Optional[str] = None,
    app_status: Optional[str] = None,
    last_ai_label: Optional[str] = None,
    last_upload_status: Optional[str] = None,
) -> dict:
    if not use_postgres():
        now = current_time_iso()
        with get_sqlite_connection() as connection:
            connection.execute(
                """
                INSERT INTO device_status (
                    device_id,
                    latitude,
                    longitude,
                    last_seen,
                    status,
                    is_listening,
                    upload_mode,
                    battery,
                    ai_status,
                    backend_status,
                    app_status,
                    last_ai_label,
                    last_upload_status,
                    updated_at
                )
                VALUES (?, ?, ?, ?, 'online', ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(device_id) DO UPDATE SET
                    latitude = excluded.latitude,
                    longitude = excluded.longitude,
                    last_seen = excluded.last_seen,
                    status = 'online',
                    is_listening = excluded.is_listening,
                    upload_mode = excluded.upload_mode,
                    battery = excluded.battery,
                    ai_status = excluded.ai_status,
                    backend_status = excluded.backend_status,
                    app_status = excluded.app_status,
                    last_ai_label = excluded.last_ai_label,
                    last_upload_status = excluded.last_upload_status,
                    updated_at = excluded.updated_at
                """,
                (
                    device_id,
                    latitude,
                    longitude,
                    now,
                    None if is_listening is None else int(is_listening),
                    upload_mode,
                    battery,
                    ai_status,
                    backend_status,
                    app_status,
                    last_ai_label,
                    last_upload_status,
                    now,
                ),
            )
            connection.commit()
            row = connection.execute(
                f"""
                SELECT {", ".join(DEVICE_STATUS_COLUMNS)}
                FROM device_status
                WHERE device_id = ?
                """,
                (device_id,),
            ).fetchone()
            return serialize_db_row(dict(row))

    connection = get_postgres_connection()
    try:
        with connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO device_status (
                        device_id,
                        latitude,
                        longitude,
                        last_seen,
                        status,
                        is_listening,
                        upload_mode,
                        battery,
                        ai_status,
                        backend_status,
                        app_status,
                        last_ai_label,
                        last_upload_status,
                        updated_at
                    )
                    VALUES (
                        %s, %s, %s, now(), 'online',
                        %s, %s, %s, %s, %s, %s, %s, %s, now()
                    )
                    ON CONFLICT (device_id) DO UPDATE SET
                        latitude = EXCLUDED.latitude,
                        longitude = EXCLUDED.longitude,
                        last_seen = now(),
                        status = 'online',
                        is_listening = EXCLUDED.is_listening,
                        upload_mode = EXCLUDED.upload_mode,
                        battery = EXCLUDED.battery,
                        ai_status = EXCLUDED.ai_status,
                        backend_status = EXCLUDED.backend_status,
                        app_status = EXCLUDED.app_status,
                        last_ai_label = EXCLUDED.last_ai_label,
                        last_upload_status = EXCLUDED.last_upload_status,
                        updated_at = now()
                    RETURNING
                        {columns}
                    """,
                    (
                        device_id,
                        latitude,
                        longitude,
                        is_listening,
                        upload_mode,
                        battery,
                        ai_status,
                        backend_status,
                        app_status,
                        last_ai_label,
                        last_upload_status,
                    ),
                )
                row = cursor.fetchone()
                return serialize_db_row(dict(row))
    finally:
        connection.close()


def upsert_device_event_status(event: SoundEvent) -> Optional[dict]:
    if not event.device_id or event.latitude is None or event.longitude is None:
        return None

    if not use_postgres():
        now = current_time_iso()
        with get_sqlite_connection() as connection:
            connection.execute(
                """
                INSERT INTO device_status (
                    device_id,
                    latitude,
                    longitude,
                    last_seen,
                    last_event_id,
                    last_event_at,
                    status,
                    last_ai_label,
                    last_upload_status,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, 'event', ?, 'metadata_uploaded', ?)
                ON CONFLICT(device_id) DO UPDATE SET
                    latitude = excluded.latitude,
                    longitude = excluded.longitude,
                    last_seen = excluded.last_seen,
                    last_event_id = excluded.last_event_id,
                    last_event_at = excluded.last_event_at,
                    status = 'event',
                    last_ai_label = excluded.last_ai_label,
                    last_upload_status = excluded.last_upload_status,
                    updated_at = excluded.updated_at
                """,
                (
                    event.device_id,
                    event.latitude,
                    event.longitude,
                    now,
                    event.event_id,
                    now,
                    event.label,
                    now,
                ),
            )
            connection.commit()
            row = connection.execute(
                f"""
                SELECT {", ".join(DEVICE_STATUS_COLUMNS)}
                FROM device_status
                WHERE device_id = ?
                """,
                (event.device_id,),
            ).fetchone()
            return serialize_db_row(dict(row))

    connection = get_postgres_connection()
    try:
        with connection:
            with connection.cursor() as cursor:
                columns = ", ".join(DEVICE_STATUS_COLUMNS)
                cursor.execute(
                    f"""
                    INSERT INTO device_status (
                        device_id,
                        latitude,
                        longitude,
                        last_seen,
                        last_event_id,
                        last_event_at,
                        status,
                        last_ai_label,
                        last_upload_status,
                        updated_at
                    )
                    VALUES (%s, %s, %s, now(), %s, now(), 'event', %s, 'metadata_uploaded', now())
                    ON CONFLICT (device_id) DO UPDATE SET
                        latitude = EXCLUDED.latitude,
                        longitude = EXCLUDED.longitude,
                        last_seen = now(),
                        last_event_id = EXCLUDED.last_event_id,
                        last_event_at = now(),
                        status = 'event',
                        last_ai_label = EXCLUDED.last_ai_label,
                        last_upload_status = EXCLUDED.last_upload_status,
                        updated_at = now()
                    RETURNING
                        {columns}
                    """,
                    (
                        event.device_id,
                        event.latitude,
                        event.longitude,
                        event.event_id,
                        event.label,
                    ),
                )
                row = cursor.fetchone()
                return serialize_db_row(dict(row))
    finally:
        connection.close()


def list_device_status_rows() -> list[dict]:
    columns = ", ".join(DEVICE_STATUS_COLUMNS)
    if not use_postgres():
        with get_sqlite_connection() as connection:
            rows = connection.execute(
                f"""
                SELECT {columns}
                FROM device_status
                ORDER BY device_id ASC
                """
            ).fetchall()
            return [serialize_db_row(dict(row)) for row in rows]

    connection = get_postgres_connection()
    try:
        with connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT {columns}
                    FROM device_status
                    ORDER BY device_id ASC
                    """
                )
                return [serialize_db_row(dict(row)) for row in cursor.fetchall()]
    finally:
        connection.close()


def create_device_command(command: DeviceCommandCreate) -> dict:
    normalized_command = command.command.strip().lower()
    if normalized_command not in SUPPORTED_DEVICE_COMMANDS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported command",
        )

    value_text = command_value_to_text(command.value)
    issued_by = command.issued_by or "dashboard"

    if not use_postgres():
        created_at = current_time_iso()
        with get_sqlite_connection() as connection:
            connection.execute(
                """
                UPDATE device_commands
                SET status = 'expired',
                    executed_at = ?,
                    ack_message = 'superseded by newer dashboard command'
                WHERE device_id = ?
                  AND status = 'pending'
                """,
                (created_at, command.device_id),
            )
            cursor = connection.execute(
                """
                INSERT INTO device_commands (
                    device_id, command, value, status, issued_by, created_at
                )
                VALUES (?, ?, ?, 'pending', ?, ?)
                """,
                (
                    command.device_id,
                    normalized_command,
                    value_text,
                    issued_by,
                    created_at,
                ),
            )
            command_id = int(cursor.lastrowid)
            connection.execute(
                """
                UPDATE device_status
                SET last_command_id = ?, updated_at = ?
                WHERE device_id = ?
                """,
                (command_id, created_at, command.device_id),
            )
            connection.commit()
            return {"id": command_id, "status": "pending"}

    connection = get_postgres_connection()
    try:
        with connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE device_commands
                    SET status = 'expired',
                        executed_at = now(),
                        ack_message = 'superseded by newer dashboard command'
                    WHERE device_id = %s
                      AND status = 'pending'
                    """,
                    (command.device_id,),
                )
                cursor.execute(
                    """
                    INSERT INTO device_commands (
                        device_id, command, value, status, issued_by, created_at
                    )
                    VALUES (%s, %s, %s, 'pending', %s, now())
                    RETURNING id, status
                    """,
                    (
                        command.device_id,
                        normalized_command,
                        value_text,
                        issued_by,
                    ),
                )
                row = dict(cursor.fetchone())
                cursor.execute(
                    """
                    UPDATE device_status
                    SET last_command_id = %s, updated_at = now()
                    WHERE device_id = %s
                    """,
                    (row["id"], command.device_id),
                )
                return serialize_db_row(row)
    finally:
        connection.close()


def get_pending_device_command(device_id: str) -> Optional[dict]:
    columns = ", ".join(DEVICE_COMMAND_COLUMNS)

    if not use_postgres():
        with get_sqlite_connection() as connection:
            row = connection.execute(
                f"""
                SELECT {columns}
                FROM device_commands
                WHERE device_id = ?
                  AND status = 'pending'
                ORDER BY id ASC
                LIMIT 1
                """,
                (device_id,),
            ).fetchone()
            return serialize_db_row(dict(row)) if row else None

    connection = get_postgres_connection()
    try:
        with connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT {columns}
                    FROM device_commands
                    WHERE device_id = %s
                      AND status = 'pending'
                    ORDER BY id ASC
                    LIMIT 1
                    """,
                    (device_id,),
                )
                row = cursor.fetchone()
                return serialize_db_row(dict(row)) if row else None
    finally:
        connection.close()


def acknowledge_device_command(ack: DeviceCommandAck) -> dict:
    normalized_status = ack.status.strip().lower()
    if normalized_status not in {"done", "failed"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="status must be done or failed",
        )

    if not use_postgres():
        executed_at = current_time_iso()
        with get_sqlite_connection() as connection:
            cursor = connection.execute(
                """
                UPDATE device_commands
                SET status = ?,
                    executed_at = ?,
                    ack_message = ?
                WHERE id = ?
                  AND device_id = ?
                """,
                (
                    normalized_status,
                    executed_at,
                    ack.message,
                    ack.command_id,
                    ack.device_id,
                ),
            )
            connection.execute(
                """
                UPDATE device_status
                SET last_command_id = ?, updated_at = ?
                WHERE device_id = ?
                """,
                (ack.command_id, executed_at, ack.device_id),
            )
            connection.commit()
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="Command not found")
            return {
                "ok": True,
                "command_id": ack.command_id,
                "status": normalized_status,
            }

    connection = get_postgres_connection()
    try:
        with connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE device_commands
                    SET status = %s,
                        executed_at = now(),
                        ack_message = %s
                    WHERE id = %s
                      AND device_id = %s
                    RETURNING id, status
                    """,
                    (
                        normalized_status,
                        ack.message,
                        ack.command_id,
                        ack.device_id,
                    ),
                )
                row = cursor.fetchone()
                if not row:
                    raise HTTPException(status_code=404, detail="Command not found")
                cursor.execute(
                    """
                    UPDATE device_status
                    SET last_command_id = %s, updated_at = now()
                    WHERE device_id = %s
                    """,
                    (ack.command_id, ack.device_id),
                )
                return {
                    "ok": True,
                    "command_id": int(row["id"]),
                    "status": row["status"],
                }
    finally:
        connection.close()


def parse_note_field(note: Optional[str], key: str) -> Optional[str]:
    if not note:
        return None
    pattern = rf"(?:^|,\s*){re.escape(key)}=([^,]+)"
    match = re.search(pattern, note)
    return match.group(1).strip() if match else None


def list_events_for_export() -> list[dict]:
    columns = ", ".join(EVENT_COLUMNS)
    if use_postgres():
        connection = get_postgres_connection()
        try:
            with connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        f"""
                        SELECT {columns}
                        FROM events
                        ORDER BY id DESC
                        LIMIT 5000
                        """
                    )
                    return [serialize_db_row(dict(row)) for row in cursor.fetchall()]
        finally:
            connection.close()

    with get_sqlite_connection() as connection:
        rows = connection.execute(
            f"""
            SELECT {columns}
            FROM events
            ORDER BY id DESC
            LIMIT 5000
            """
        ).fetchall()
        return [serialize_db_row(dict(row)) for row in rows]


def build_events_csv() -> str:
    output = StringIO()
    fieldnames = [
        "event_id",
        "device_id",
        "timestamp",
        "label",
        "confidence",
        "aircraft_probability",
        "latitude",
        "longitude",
        "upload_mode",
        "audio_path",
        "created_at",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for event in list_events_for_export():
        note = event.get("note")
        writer.writerow(
            {
                "event_id": event.get("event_id"),
                "device_id": event.get("device_id"),
                "timestamp": event.get("timestamp"),
                "label": event.get("label"),
                "confidence": parse_note_field(note, "confidence"),
                "aircraft_probability": parse_note_field(
                    note, "probability_aircraft"
                ),
                "latitude": event.get("latitude"),
                "longitude": event.get("longitude"),
                "upload_mode": parse_note_field(note, "upload_mode"),
                "audio_path": event.get("audio_path"),
                "created_at": event.get("created_at"),
            }
        )
    return output.getvalue()


def verify_upload_token(upload_token: Optional[str]) -> None:
    expected_token = os.getenv("UPLOAD_TOKEN", DEFAULT_UPLOAD_TOKEN)
    if upload_token != expected_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid upload token",
        )


def is_alert_event_label(label: Optional[str]) -> bool:
    if not label:
        return False
    return label.strip().lower() in {"aircraft", "drone"}


def safe_path_part(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return cleaned.strip("._") or "unknown"


def get_gcs_bucket() -> storage.Bucket:
    bucket_name = os.getenv("GCS_BUCKET_NAME")
    credentials_json = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON")

    if not bucket_name:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="GCS_BUCKET_NAME is not configured",
        )

    if not credentials_json:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="GOOGLE_APPLICATION_CREDENTIALS_JSON is not configured",
        )

    try:
        credentials_info = json.loads(credentials_json)
        credentials = service_account.Credentials.from_service_account_info(
            credentials_info
        )
        client = storage.Client(
            credentials=credentials,
            project=credentials_info.get("project_id"),
        )
        return client.bucket(bucket_name)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Google service account JSON is not valid",
        ) from exc


def audio_category_folder(
    label: Optional[str] = None,
    category: Optional[str] = None,
) -> str:
    normalized_category = (category or "").strip().lower()
    normalized_label = (label or "").strip().lower()

    if normalized_category in {"drone", "target"}:
        return "drone"

    if normalized_category in {"other", "non_target", "non-target"}:
        return "other"

    if normalized_label in {"aircraft", "drone"}:
        return "drone"

    return "other"


def build_audio_path(
    device_id: str,
    event_id: str,
    label: Optional[str] = None,
    category: Optional[str] = None,
) -> str:
    category_folder = audio_category_folder(label=label, category=category)
    safe_device_id = safe_path_part(device_id)
    safe_event_id = safe_path_part(event_id)
    return (
        f"audio/{category_folder}/"
        f"{safe_device_id}/{current_date_yyyymmdd()}/{safe_event_id}.wav"
    )


init_db()


@app.get("/")
def root():
    return {
        "status": "ok",
        "message": "Sound detector backend is running",
    }


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "time": current_time_iso(),
    }


@app.post("/events")
async def create_event(
    event: SoundEvent,
    upload_token: Optional[str] = Header(default=None, alias="x-upload-token"),
):
    verify_upload_token(upload_token)
    created_at = current_time_iso()
    db_id = save_event(event, created_at)
    device_row = None

    if is_alert_event_label(event.label):
        device_row = upsert_device_event_status(event)

    if device_row:
        await dashboard_manager.broadcast(
            {
                "type": "event_trigger",
                "device_id": event.device_id,
                "event_id": event.event_id,
                "latitude": event.latitude,
                "longitude": event.longitude,
                "last_event_at": device_row.get("last_event_at"),
                "status": "event",
                "rms_peak": event.rms_peak,
            }
        )

    return {
        "status": "success",
        "message": "Event received",
        "event_id": event.event_id,
        "db_id": db_id,
    }


@app.get("/events")
def list_events():
    events = list_recent_events()

    return {
        "status": "success",
        "count": len(events),
        "events": events,
    }


@app.post("/location-update")
async def update_location(location: LocationUpdate):
    device_row = upsert_device_location(
        device_id=location.device_id,
        latitude=location.latitude,
        longitude=location.longitude,
        is_listening=location.is_listening,
        upload_mode=location.upload_mode,
        battery=location.battery,
        ai_status=location.ai_status,
        backend_status=location.backend_status,
        app_status=location.app_status,
        last_ai_label=location.last_ai_label,
        last_upload_status=location.last_upload_status,
    )

    await dashboard_manager.broadcast(
        {
            "type": "location_update",
            **device_row,
        }
    )

    return {
        "status": "success",
        "device_id": location.device_id,
        "latitude": location.latitude,
        "longitude": location.longitude,
    }


@app.get("/device-status")
def device_status():
    devices = list_device_status_rows()

    return {
        "status": "success",
        "count": len(devices),
        "devices": devices,
    }


@app.post("/device-command")
async def device_command(command: DeviceCommandCreate):
    row = create_device_command(command)
    await dashboard_manager.broadcast(
        {
            "type": "device_command_created",
            "device_id": command.device_id,
            "command_id": row.get("id"),
            "command": command.command,
            "status": row.get("status"),
        }
    )
    return {
        "ok": True,
        "command_id": row.get("id"),
        "status": row.get("status", "pending"),
    }


@app.get("/device-command/{device_id}")
def device_command_poll(device_id: str):
    command = get_pending_device_command(device_id)
    if not command:
        return {"has_command": False}

    return {
        "has_command": True,
        "command_id": command.get("id"),
        "command": command.get("command"),
        "value": command.get("value"),
        "created_at": command.get("created_at"),
    }


@app.post("/device-command-ack")
async def device_command_ack(ack: DeviceCommandAck):
    result = acknowledge_device_command(ack)
    await dashboard_manager.broadcast(
        {
            "type": "device_command_ack",
            "device_id": ack.device_id,
            "command_id": ack.command_id,
            "status": result.get("status"),
            "message": ack.message,
        }
    )
    return result


@app.get("/events/export.csv")
def export_events_csv():
    csv_text = build_events_csv()
    return Response(
        content=csv_text,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="sound_events_export.csv"'
        },
    )


@app.websocket("/ws/dashboard")
async def dashboard_websocket(websocket: WebSocket):
    await dashboard_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        dashboard_manager.disconnect(websocket)


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    maps_api_key = os.getenv("GOOGLE_MAPS_API_KEY", "")

    maps_script_url = ""
    if maps_api_key:
        maps_script_url = (
            "https://maps.googleapis.com/maps/api/js?"
            f"key={quote(maps_api_key)}&callback=initMap"
        )

    html = """
    <!doctype html>
    <html lang="zh-Hant">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Sound Detector V2.1 Command Center</title>
        <style>
            :root {
                --bg: #101419;
                --panel: #171e26;
                --panel-2: #1f2833;
                --line: #2f3a45;
                --text: #eef4f8;
                --muted: #a8b3bd;
                --good: #45c486;
                --warn: #f0b84d;
                --bad: #f06767;
                --accent: #6bb8ff;
            }
            * { box-sizing: border-box; }
            body {
                margin: 0;
                font-family: Arial, "Noto Sans TC", sans-serif;
                background: var(--bg);
                color: var(--text);
            }
            header {
                padding: 14px 18px;
                border-bottom: 1px solid var(--line);
                background: #0d1116;
                display: flex;
                justify-content: space-between;
                gap: 12px;
                align-items: center;
            }
            h1 { margin: 0; font-size: 20px; }
            .subtitle { color: var(--muted); font-size: 13px; margin-top: 3px; }
            .topbar {
                display: grid;
                grid-template-columns: repeat(5, minmax(120px, 1fr));
                gap: 10px;
                padding: 12px 18px;
            }
            .stat, .panel, .node-card, .event-row {
                background: var(--panel);
                border: 1px solid var(--line);
                border-radius: 8px;
            }
            .stat { padding: 12px; }
            .stat .label { color: var(--muted); font-size: 12px; }
            .stat .value { font-size: 22px; font-weight: 800; margin-top: 4px; }
            .layout {
                display: grid;
                grid-template-columns: 320px minmax(360px, 1fr) 340px;
                grid-template-rows: minmax(420px, 56vh) auto;
                gap: 12px;
                padding: 0 18px 18px;
            }
            .panel { min-height: 0; overflow: hidden; display: flex; flex-direction: column; }
            .panel h2 {
                font-size: 15px;
                margin: 0;
                padding: 12px;
                border-bottom: 1px solid var(--line);
            }
            .panel-body { padding: 12px; overflow: auto; }
            #map {
                height: 100%;
                min-height: 420px;
                background: #202832;
            }
            .map-panel { position: relative; }
            .map-note {
                position: absolute;
                left: 12px;
                bottom: 12px;
                z-index: 2;
                background: rgba(13,17,22,.86);
                border: 1px solid var(--line);
                padding: 8px 10px;
                border-radius: 8px;
                font-size: 12px;
                color: var(--muted);
            }
            .node-card { padding: 12px; margin-bottom: 10px; }
            .node-title {
                display: flex;
                justify-content: space-between;
                gap: 8px;
                align-items: center;
                font-weight: 800;
            }
            .pill {
                display: inline-flex;
                align-items: center;
                border: 1px solid var(--line);
                border-radius: 999px;
                padding: 3px 8px;
                font-size: 12px;
                color: var(--muted);
                white-space: nowrap;
            }
            .pill.online { color: var(--good); border-color: rgba(69,196,134,.45); }
            .pill.offline { color: var(--bad); border-color: rgba(240,103,103,.45); }
            .kv {
                display: grid;
                grid-template-columns: 110px 1fr;
                gap: 5px 8px;
                font-size: 12px;
                margin: 10px 0;
                color: var(--muted);
            }
            .kv strong { color: var(--text); font-weight: 600; }
            .actions { display: flex; flex-wrap: wrap; gap: 7px; }
            button, .link-button {
                border: 1px solid #415060;
                background: var(--panel-2);
                color: var(--text);
                border-radius: 7px;
                padding: 7px 9px;
                font-size: 12px;
                cursor: pointer;
                text-decoration: none;
                display: inline-flex;
                align-items: center;
                justify-content: center;
            }
            button:hover, .link-button:hover { border-color: var(--accent); }
            button.primary { background: #174365; border-color: #2e83c5; }
            button.danger { background: #4a2228; border-color: #9d4853; }
            .event-row { padding: 10px; margin-bottom: 8px; font-size: 12px; }
            .event-row.target { border-color: rgba(240,184,77,.65); }
            .event-title { display: flex; justify-content: space-between; gap: 8px; font-weight: 800; }
            .timeline { grid-column: 1 / span 3; }
            .filters { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 10px; }
            .reports-grid {
                display: grid;
                grid-template-columns: repeat(2, minmax(120px, 1fr));
                gap: 8px;
            }
            .report-box {
                background: #111820;
                border: 1px solid var(--line);
                border-radius: 8px;
                padding: 10px;
            }
            .report-box .label { color: var(--muted); font-size: 12px; }
            .report-box .value { font-size: 20px; font-weight: 800; margin-top: 4px; }
            .marker-label {
                color: #111;
                background: #fff;
                border: 2px solid #111;
                border-radius: 999px;
                padding: 2px 6px;
                font-weight: 800;
                font-size: 12px;
                box-shadow: 0 2px 8px rgba(0,0,0,.35);
            }
            .pulse-label {
                animation: pulse 900ms ease-in-out infinite;
                outline: 3px solid rgba(255, 201, 87, .75);
            }
            @keyframes pulse {
                0% { transform: scale(1); box-shadow: 0 0 0 0 rgba(255, 201, 87, .8); }
                70% { transform: scale(1.12); box-shadow: 0 0 0 12px rgba(255, 201, 87, 0); }
                100% { transform: scale(1); box-shadow: 0 0 0 0 rgba(255, 201, 87, 0); }
            }
            @media (max-width: 980px) {
                header { align-items: flex-start; flex-direction: column; }
                .topbar { grid-template-columns: repeat(3, 1fr); padding: 10px; }
                .layout {
                    grid-template-columns: 1fr;
                    grid-template-rows: auto;
                    padding: 0 10px 14px;
                }
                .map-panel { order: 2; }
                #map { min-height: 300px; }
                .timeline { grid-column: auto; }
            }
            @media (max-width: 560px) {
                .topbar { grid-template-columns: 1fr 1fr; }
                .stat .value { font-size: 18px; }
                .kv { grid-template-columns: 92px 1fr; }
                .actions button { flex: 1 1 45%; }
            }
        </style>
    </head>
    <body>
        <header>
            <div>
                <h1>聲音偵測戰情室 V2.1</h1>
                <div class="subtitle">遠端節點管理、即時警示、事件報表與 CSV 匯出</div>
            </div>
            <a class="link-button" href="/events/export.csv">Export CSV</a>
        </header>

        <section class="topbar">
            <div class="stat"><div class="label">Online Nodes</div><div class="value" id="onlineCount">0</div></div>
            <div class="stat"><div class="label">Active Alerts</div><div class="value" id="activeAlertCount">0</div></div>
            <div class="stat"><div class="label">Today Drone Events</div><div class="value" id="todayDroneCount">0</div></div>
            <div class="stat"><div class="label">Upload Status</div><div class="value" id="uploadSummary">-</div></div>
            <div class="stat"><div class="label">System Status</div><div class="value" id="systemStatus">Loading</div></div>
        </section>

        <main class="layout">
            <section class="panel">
                <h2>節點管理</h2>
                <div class="panel-body" id="nodeList"></div>
            </section>

            <section class="panel map-panel">
                <h2>節點地圖</h2>
                <div id="map"></div>
                <div class="map-note">只有 aircraft / drone 事件會觸發 7 秒閃爍，GPS 更新不會清掉警示。</div>
            </section>

            <section class="panel">
                <h2>即時警示</h2>
                <div class="panel-body" id="alertList"></div>
                <h2>Reports</h2>
                <div class="panel-body">
                    <div class="reports-grid" id="reportsGrid"></div>
                </div>
            </section>

            <section class="panel timeline">
                <h2>事件時間軸</h2>
                <div class="panel-body">
                    <div class="filters">
                        <button onclick="setFilter('all')">All</button>
                        <button onclick="setFilter('drone')">Drone only</button>
                        <button onclick="setFilter('other')">Other only</button>
                    </div>
                    <div id="timelineList"></div>
                </div>
            </section>
        </main>

        <script>
            let map;
            let infoWindow;
            const devices = new Map();
            const events = [];
            const markers = new Map();
            const alertUntil = new Map();
            let currentFilter = 'all';

            function safe(value, fallback = '-') {
                return value === null || value === undefined || value === '' ? fallback : value;
            }

            function isTarget(label) {
                const value = (label || '').toLowerCase();
                return value === 'aircraft' || value === 'drone';
            }

            function isToday(timestamp) {
                if (!timestamp) return false;
                const date = new Date(timestamp);
                const now = new Date();
                return date.getFullYear() === now.getFullYear()
                    && date.getMonth() === now.getMonth()
                    && date.getDate() === now.getDate();
            }

            function shortDeviceLabel(deviceId) {
                const match = String(deviceId || '').match(/A\\d+/i);
                return match ? match[0].toUpperCase() : String(deviceId || '?').slice(-4);
            }

            function markerShape(deviceId) {
                if (deviceId === 'node_A01') return '○';
                if (deviceId === 'node_A02') return '□';
                if (deviceId === 'node_A03') return '△';
                if (deviceId === 'node_A04') return '◇';
                return '⬡';
            }

            window.initMap = function initMap() {
                if (!window.google) return;
                map = new google.maps.Map(document.getElementById('map'), {
                    center: { lat: 25.033, lng: 121.565 },
                    zoom: 12,
                    mapTypeControl: false,
                    streetViewControl: false,
                    fullscreenControl: true,
                });
                infoWindow = new google.maps.InfoWindow();
                refreshAll();
            };

            function markerIcon(device) {
                const active = isAlertActive(device.device_id);
                const label = `${markerShape(device.device_id)} ${shortDeviceLabel(device.device_id)}`;
                const html = `<div xmlns="http://www.w3.org/1999/xhtml" class="marker-label ${active ? 'pulse-label' : ''}">${label}</div>`;
                return {
                    url: 'data:image/svg+xml;charset=UTF-8,' + encodeURIComponent(`
                        <svg xmlns="http://www.w3.org/2000/svg" width="92" height="38">
                            <foreignObject width="92" height="38">${html}</foreignObject>
                        </svg>
                    `),
                    scaledSize: new google.maps.Size(92, 38),
                    anchor: new google.maps.Point(46, 19),
                };
            }

            function isAlertActive(deviceId) {
                const until = alertUntil.get(deviceId);
                return Boolean(until && Date.now() < until);
            }

            function updateMapMarker(device) {
                if (!map || !window.google) return;
                const lat = Number(device.latitude);
                const lng = Number(device.longitude);
                if (!Number.isFinite(lat) || !Number.isFinite(lng)) return;

                const position = { lat, lng };
                let marker = markers.get(device.device_id);
                if (!marker) {
                    marker = new google.maps.Marker({
                        map,
                        position,
                        title: `${device.device_id} - ${safe(device.upload_mode)}`,
                        icon: markerIcon(device),
                    });
                    marker.addListener('click', () => {
                        infoWindow.setContent(`
                            <strong>${safe(device.device_id)}</strong><br>
                            latitude: ${safe(device.latitude)}<br>
                            longitude: ${safe(device.longitude)}<br>
                            last_seen: ${safe(device.last_seen)}<br>
                            last_event_id: ${safe(device.last_event_id)}<br>
                            last_event_at: ${safe(device.last_event_at)}<br>
                            status: ${safe(device.status)}<br>
                            mode: ${safe(device.upload_mode)}<br>
                            listening: ${safe(device.is_listening)}
                        `);
                        infoWindow.open({ map, anchor: marker });
                    });
                    markers.set(device.device_id, marker);
                } else {
                    marker.setPosition(position);
                    marker.setTitle(`${device.device_id} - ${safe(device.upload_mode)}`);
                    marker.setIcon(markerIcon(device));
                }
            }

            function setFilter(filter) {
                currentFilter = filter;
                renderTimeline();
            }

            async function sendCommand(deviceId, command) {
                try {
                    const response = await fetch('/device-command', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            device_id: deviceId,
                            command,
                            value: null,
                            issued_by: 'dashboard',
                        }),
                    });
                    const body = await response.json();
                    if (!response.ok) throw new Error(body.detail || response.statusText);
                    document.getElementById('systemStatus').textContent = `Command #${body.command_id}`;
                } catch (error) {
                    document.getElementById('systemStatus').textContent = 'Command failed';
                    alert(`Command failed: ${error}`);
                }
            }

            function renderNodes() {
                const list = document.getElementById('nodeList');
                const values = Array.from(devices.values());
                if (!values.length) {
                    list.innerHTML = '<div class="subtitle">目前沒有節點狀態</div>';
                    return;
                }
                list.innerHTML = values.map(device => `
                    <div class="node-card">
                        <div class="node-title">
                            <span>${safe(device.device_id)}</span>
                            <span class="pill ${device.status === 'online' || device.status === 'event' ? 'online' : 'offline'}">${safe(device.status)}</span>
                        </div>
                        <div class="kv">
                            <span>Listening</span><strong>${device.is_listening ? 'yes' : 'no'}</strong>
                            <span>Mode</span><strong>${safe(device.upload_mode)}</strong>
                            <span>GPS</span><strong>${device.latitude && device.longitude ? 'ok' : 'waiting'}</strong>
                            <span>Battery</span><strong>${safe(device.battery)}</strong>
                            <span>AI</span><strong>${safe(device.ai_status)}</strong>
                            <span>Last seen</span><strong>${safe(device.last_seen)}</strong>
                            <span>Last event</span><strong>${safe(device.last_event_at)}</strong>
                        </div>
                        <div class="actions">
                            <button class="primary" onclick="sendCommand('${device.device_id}', 'start_listening')">Start</button>
                            <button class="danger" onclick="sendCommand('${device.device_id}', 'stop_listening')">Stop</button>
                            <button onclick="sendCommand('${device.device_id}', 'set_detection_mode')">Detection</button>
                            <button onclick="sendCommand('${device.device_id}', 'set_collection_mode')">Collection</button>
                        </div>
                    </div>
                `).join('');
            }

            function renderAlerts() {
                const targetEvents = events.filter(event => isTarget(event.label)).slice(0, 12);
                const list = document.getElementById('alertList');
                list.innerHTML = targetEvents.length ? targetEvents.map(event => `
                    <div class="event-row target">
                        <div class="event-title"><span>${safe(event.label)}</span><span>${safe(event.device_id)}</span></div>
                        <div>${safe(event.timestamp)}</div>
                        <div>prob ${noteValue(event.note, 'probability_aircraft')} / conf ${noteValue(event.note, 'confidence')}</div>
                        <div>${safe(event.latitude)}, ${safe(event.longitude)}</div>
                        ${event.audio_path ? `<a class="link-button" href="#" onclick="return false;">audio ready</a>` : ''}
                    </div>
                `).join('') : '<div class="subtitle">目前沒有 target 警示</div>';
            }

            function noteValue(note, key) {
                const match = String(note || '').match(new RegExp(`(?:^|,\\\\s*)${key}=([^,]+)`));
                return match ? match[1] : '-';
            }

            function renderTimeline() {
                const list = document.getElementById('timelineList');
                const filtered = events.filter(event => {
                    if (currentFilter === 'drone') return isTarget(event.label);
                    if (currentFilter === 'other') return !isTarget(event.label);
                    return true;
                }).slice(0, 50);
                list.innerHTML = filtered.length ? filtered.map(event => `
                    <div class="event-row ${isTarget(event.label) ? 'target' : ''}">
                        <div class="event-title"><span>${safe(event.label)}</span><span>${safe(event.device_id)}</span></div>
                        <div>${safe(event.timestamp)}</div>
                        <div>confidence ${noteValue(event.note, 'confidence')} · mode ${noteValue(event.note, 'upload_mode')} · ${event.audio_path ? 'audio uploaded' : 'audio pending'}</div>
                    </div>
                `).join('') : '<div class="subtitle">目前沒有事件</div>';
            }

            function renderReports() {
                const todayEvents = events.filter(event => isToday(event.created_at || event.timestamp));
                const drone = todayEvents.filter(event => isTarget(event.label));
                const other = todayEvents.filter(event => !isTarget(event.label));
                const uploaded = todayEvents.filter(event => Boolean(event.audio_path));
                const byNode = {};
                todayEvents.forEach(event => {
                    byNode[event.device_id || 'unknown'] = (byNode[event.device_id || 'unknown'] || 0) + 1;
                });
                document.getElementById('reportsGrid').innerHTML = `
                    <div class="report-box"><div class="label">Today drone</div><div class="value">${drone.length}</div></div>
                    <div class="report-box"><div class="label">Today other</div><div class="value">${other.length}</div></div>
                    <div class="report-box"><div class="label">Drone ratio</div><div class="value">${todayEvents.length ? Math.round(drone.length / todayEvents.length * 100) : 0}%</div></div>
                    <div class="report-box"><div class="label">Audio uploaded</div><div class="value">${uploaded.length}</div></div>
                    <div class="report-box" style="grid-column:1/-1"><div class="label">By node</div><div>${Object.entries(byNode).map(([k,v]) => `${k}: ${v}`).join('<br>') || '-'}</div></div>
                `;
                document.getElementById('todayDroneCount').textContent = drone.length;
                document.getElementById('uploadSummary').textContent = `${uploaded.length}/${todayEvents.length}`;
            }

            function renderSummary() {
                const values = Array.from(devices.values());
                const online = values.filter(device => device.status === 'online' || device.status === 'event').length;
                const active = values.filter(device => isAlertActive(device.device_id)).length;
                document.getElementById('onlineCount').textContent = online;
                document.getElementById('activeAlertCount').textContent = active;
                document.getElementById('systemStatus').textContent = values.length ? 'Live' : 'Waiting';
            }

            function renderAll() {
                Array.from(devices.values()).forEach(updateMapMarker);
                renderNodes();
                renderAlerts();
                renderTimeline();
                renderReports();
                renderSummary();
            }

            async function refreshAll() {
                try {
                    const [statusResponse, eventsResponse] = await Promise.all([
                        fetch('/device-status'),
                        fetch('/events'),
                    ]);
                    const statusData = await statusResponse.json();
                    const eventsData = await eventsResponse.json();
                    (statusData.devices || []).forEach(device => devices.set(device.device_id, device));
                    events.splice(0, events.length, ...(eventsData.events || []));
                    renderAll();
                } catch (error) {
                    document.getElementById('systemStatus').textContent = 'Fetch error';
                }
            }

            function connectWebSocket() {
                const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
                const ws = new WebSocket(`${protocol}//${window.location.host}/ws/dashboard`);
                ws.onmessage = event => {
                    const data = JSON.parse(event.data);
                    if (data.type === 'location_update') {
                        devices.set(data.device_id, { ...(devices.get(data.device_id) || {}), ...data });
                        renderAll();
                    }
                    if (data.type === 'event_trigger') {
                        alertUntil.set(data.device_id, Date.now() + 7000);
                        devices.set(data.device_id, { ...(devices.get(data.device_id) || {}), ...data, status: 'event' });
                        refreshAll();
                    }
                    if (data.type === 'device_command_ack') {
                        document.getElementById('systemStatus').textContent = `Ack ${data.status}`;
                        refreshAll();
                    }
                };
                ws.onclose = () => setTimeout(connectWebSocket, 2500);
            }

            setInterval(() => {
                renderAll();
            }, 1000);
            setInterval(refreshAll, 5000);
            refreshAll();
            connectWebSocket();
        </script>
        __MAPS_SCRIPT_TAG__
    </body>
    </html>
    """
    maps_script_tag = ""
    if maps_script_url:
        maps_script_tag = f"<script async defer src=\"{maps_script_url}\"></script>"
    html = html.replace("__MAPS_SCRIPT_TAG__", maps_script_tag)
    return HTMLResponse(content=html)


@app.post("/upload-audio")
def upload_audio(
    event_id: str = Form(...),
    device_id: str = Form(...),
    label: Optional[str] = Form(default=None),
    category: Optional[str] = Form(default=None),
    file: UploadFile = File(...),
    upload_token: Optional[str] = Header(default=None, alias="x-upload-token"),
):
    verify_upload_token(upload_token)

    if not file.filename or not file.filename.lower().endswith(".wav"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only .wav files are allowed",
        )

    category_folder = audio_category_folder(label=label, category=category)
    audio_path = build_audio_path(
        device_id=device_id,
        event_id=event_id,
        label=label,
        category=category,
    )
    bucket = get_gcs_bucket()
    blob = bucket.blob(audio_path)

    try:
        file.file.seek(0)
        blob.upload_from_file(
            file.file,
            content_type=file.content_type or "audio/wav",
        )
        update_event_audio_path(event_id=event_id, audio_path=audio_path)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload audio file",
        ) from exc
    finally:
        file.file.close()

    return {
        "status": "success",
        "message": "Audio uploaded",
        "event_id": event_id,
        "device_id": device_id,
        "label": label,
        "category": category_folder,
        "audio_path": audio_path,
    }
