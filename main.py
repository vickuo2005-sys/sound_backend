import json
import logging
import math
import os
import re
import sqlite3
import csv
import uuid
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
    Query,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.responses import HTMLResponse, Response
from google.cloud import storage
from google.oauth2 import service_account
from pydantic import BaseModel

from services.event_fusion import (
    get_event_group_detail as get_fusion_group_detail,
    list_event_groups as list_fusion_groups,
    process_event as process_fusion_event,
)


app = FastAPI()

DB_NAME = "sound_events.db"
DEFAULT_UPLOAD_TOKEN = "test-token-123"
logger = logging.getLogger("sound_backend")
EVENT_FUSION_WINDOW_SECONDS = float(os.getenv("EVENT_FUSION_WINDOW_SECONDS", "3") or 3)
EVENT_GROUP_WINDOW_SECONDS = EVENT_FUSION_WINDOW_SECONDS
TARGET_ESTIMATE_METHOD = "weighted_centroid"
TDOA_ESTIMATE_METHOD = "tdoa_timestamp"
TDOA_FALLBACK_METHOD = "weighted_centroid_fallback"
SOUND_SPEED_MPS = 343.0
TDOA_MAX_RTT_MS = 300.0
TDOA_TIME_TOLERANCE_SECONDS = 0.3
TDOA_MIN_NODE_SPREAD_M = 5.0
TDOA_MAX_OUTSIDE_BOUNDS_M = 300.0


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
    timing_version: Optional[int] = None
    timing_source: Optional[str] = None
    capture_start_time_ms: Optional[int] = None
    event_start_sample: Optional[int] = None
    event_end_sample: Optional[int] = None
    rms_peak_sample: Optional[int] = None
    sample_rate_hz: Optional[int] = None
    channel_count: Optional[int] = None
    device_event_time_ms: Optional[float] = None
    event_start_time_ms: Optional[float] = None
    event_end_time_ms: Optional[float] = None
    rms_peak_time_ms: Optional[int] = None
    rms_peak_offset_ms: Optional[float] = None
    sample_rate: Optional[int] = None
    audio_duration_ms: Optional[float] = None
    time_sync_offset_ms: Optional[float] = None
    time_sync_rtt_ms: Optional[float] = None


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
    "timing_version",
    "timing_source",
    "capture_start_time_ms",
    "event_start_sample",
    "event_end_sample",
    "rms_peak_sample",
    "sample_rate_hz",
    "channel_count",
    "device_event_time_ms",
    "event_start_time_ms",
    "event_end_time_ms",
    "rms_peak_time_ms",
    "rms_peak_offset_ms",
    "sample_rate",
    "audio_duration_ms",
    "time_sync_offset_ms",
    "time_sync_rtt_ms",
    "corrected_arrival_time_ms",
    "timing_quality",
]

EVENT_WRITE_COLUMNS = [column for column in EVENT_COLUMNS if column != "id"]

NEW_TIMING_METADATA_COLUMNS = [
    "timing_version",
    "timing_source",
    "capture_start_time_ms",
    "event_start_sample",
    "event_end_sample",
    "rms_peak_sample",
    "sample_rate_hz",
    "channel_count",
    "rms_peak_time_ms",
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

EVENT_GROUP_COLUMNS = [
    "id",
    "group_kind",
    "label",
    "group_label",
    "status",
    "first_event_time",
    "start_time",
    "last_event_time",
    "end_time",
    "node_count",
    "estimated_lat",
    "estimated_lng",
    "localization_method",
    "confidence",
    "uncertainty_radius_m",
    "method",
    "tdoa_residual_rmse_m",
    "tdoa_node_count",
    "time_sync_quality",
    "created_at",
    "updated_at",
]

EVENT_GROUP_OBSERVATION_COLUMNS = [
    "id",
    "group_id",
    "event_db_id",
    "event_id",
    "device_id",
    "label",
    "latitude",
    "longitude",
    "rms_peak",
    "ai_probability",
    "aircraft_probability",
    "audio_path",
    "event_timestamp",
    "weight",
    "corrected_arrival_time_ms",
    "time_sync_rtt_ms",
    "tdoa_used",
    "tdoa_residual_m",
    "observation_kind",
    "created_at",
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
                created_at TEXT,
                timing_version INTEGER,
                timing_source TEXT,
                capture_start_time_ms INTEGER,
                event_start_sample INTEGER,
                event_end_sample INTEGER,
                rms_peak_sample INTEGER,
                sample_rate_hz INTEGER,
                channel_count INTEGER,
                device_event_time_ms REAL,
                event_start_time_ms REAL,
                event_end_time_ms REAL,
                rms_peak_time_ms INTEGER,
                rms_peak_offset_ms REAL,
                sample_rate INTEGER,
                audio_duration_ms REAL,
                time_sync_offset_ms REAL,
                time_sync_rtt_ms REAL,
                corrected_arrival_time_ms REAL,
                timing_quality TEXT
            )
            """
        )
        for column_name, column_definition in [
            ("audio_path", "TEXT"),
            ("timing_version", "INTEGER"),
            ("timing_source", "TEXT"),
            ("capture_start_time_ms", "INTEGER"),
            ("event_start_sample", "INTEGER"),
            ("event_end_sample", "INTEGER"),
            ("rms_peak_sample", "INTEGER"),
            ("sample_rate_hz", "INTEGER"),
            ("channel_count", "INTEGER"),
            ("device_event_time_ms", "REAL"),
            ("event_start_time_ms", "REAL"),
            ("event_end_time_ms", "REAL"),
            ("rms_peak_time_ms", "INTEGER"),
            ("rms_peak_offset_ms", "REAL"),
            ("sample_rate", "INTEGER"),
            ("audio_duration_ms", "REAL"),
            ("time_sync_offset_ms", "REAL"),
            ("time_sync_rtt_ms", "REAL"),
            ("corrected_arrival_time_ms", "REAL"),
            ("timing_quality", "TEXT"),
        ]:
            add_sqlite_column_if_missing(
                connection=connection,
                table_name="events",
                column_name=column_name,
                column_definition=column_definition,
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
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS event_groups (
                id TEXT PRIMARY KEY,
                group_kind TEXT DEFAULT 'fusion',
                label TEXT,
                group_label TEXT,
                status TEXT DEFAULT 'ACTIVE',
                first_event_time TEXT,
                start_time TEXT,
                last_event_time TEXT,
                end_time TEXT,
                node_count INTEGER,
                estimated_lat REAL,
                estimated_lng REAL,
                localization_method TEXT,
                confidence REAL,
                uncertainty_radius_m REAL,
                method TEXT,
                tdoa_residual_rmse_m REAL,
                tdoa_node_count INTEGER,
                time_sync_quality TEXT,
                created_at TEXT,
                updated_at TEXT
            )
            """
        )
        for column_name, column_definition in [
            ("group_kind", "TEXT DEFAULT 'fusion'"),
            ("label", "TEXT"),
            ("group_label", "TEXT"),
            ("status", "TEXT DEFAULT 'ACTIVE'"),
            ("first_event_time", "TEXT"),
            ("start_time", "TEXT"),
            ("last_event_time", "TEXT"),
            ("end_time", "TEXT"),
            ("node_count", "INTEGER"),
            ("estimated_lat", "REAL"),
            ("estimated_lng", "REAL"),
            ("localization_method", "TEXT"),
            ("confidence", "REAL"),
            ("uncertainty_radius_m", "REAL"),
            ("method", "TEXT"),
            ("tdoa_residual_rmse_m", "REAL"),
            ("tdoa_node_count", "INTEGER"),
            ("time_sync_quality", "TEXT"),
            ("created_at", "TEXT"),
            ("updated_at", "TEXT"),
        ]:
            add_sqlite_column_if_missing(
                connection=connection,
                table_name="event_groups",
                column_name=column_name,
                column_definition=column_definition,
            )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS event_group_observations (
                id TEXT PRIMARY KEY,
                group_id TEXT,
                event_db_id INTEGER,
                event_id TEXT,
                device_id TEXT,
                label TEXT,
                latitude REAL,
                longitude REAL,
                rms_peak REAL,
                ai_probability REAL,
                aircraft_probability REAL,
                audio_path TEXT,
                event_timestamp TEXT,
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
                weight REAL,
                corrected_arrival_time_ms REAL,
                time_sync_rtt_ms REAL,
                tdoa_used INTEGER DEFAULT 0,
                tdoa_residual_m REAL,
                observation_kind TEXT DEFAULT 'fusion',
                created_at TEXT
            )
            """
        )
        for column_name, column_definition in [
            ("group_id", "TEXT"),
            ("event_db_id", "INTEGER"),
            ("event_id", "TEXT"),
            ("device_id", "TEXT"),
            ("label", "TEXT"),
            ("latitude", "REAL"),
            ("longitude", "REAL"),
            ("rms_peak", "REAL"),
            ("ai_probability", "REAL"),
            ("aircraft_probability", "REAL"),
            ("audio_path", "TEXT"),
            ("event_timestamp", "TEXT"),
            ("timing_version", "INTEGER"),
            ("timing_source", "TEXT"),
            ("capture_start_time_ms", "INTEGER"),
            ("event_start_sample", "INTEGER"),
            ("event_end_sample", "INTEGER"),
            ("rms_peak_sample", "INTEGER"),
            ("sample_rate_hz", "INTEGER"),
            ("channel_count", "INTEGER"),
            ("audio_duration_ms", "INTEGER"),
            ("device_event_time_ms", "INTEGER"),
            ("event_end_time_ms", "INTEGER"),
            ("rms_peak_time_ms", "INTEGER"),
            ("weight", "REAL"),
            ("corrected_arrival_time_ms", "REAL"),
            ("time_sync_rtt_ms", "REAL"),
            ("tdoa_used", "INTEGER DEFAULT 0"),
            ("tdoa_residual_m", "REAL"),
            ("observation_kind", "TEXT DEFAULT 'fusion'"),
            ("created_at", "TEXT"),
        ]:
            add_sqlite_column_if_missing(
                connection=connection,
                table_name="event_group_observations",
                column_name=column_name,
                column_definition=column_definition,
            )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS event_groups_updated_at_idx
            ON event_groups (updated_at)
            """
        )
        connection.execute(
            """
            UPDATE event_groups
            SET group_kind = 'target_estimate'
            WHERE COALESCE(group_kind, 'fusion') = 'fusion'
              AND (
                    estimated_lat IS NOT NULL
                 OR estimated_lng IS NOT NULL
                 OR uncertainty_radius_m IS NOT NULL
                 OR method IS NOT NULL
                 OR tdoa_residual_rmse_m IS NOT NULL
              )
            """
        )
        connection.execute(
            """
            UPDATE event_group_observations
            SET observation_kind = 'target_estimate'
            WHERE COALESCE(observation_kind, 'fusion') = 'fusion'
              AND (
                    weight IS NOT NULL
                 OR corrected_arrival_time_ms IS NOT NULL
                 OR time_sync_rtt_ms IS NOT NULL
                 OR tdoa_residual_m IS NOT NULL
              )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS event_groups_fusion_lookup_idx
            ON event_groups (label, status, last_event_time)
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS event_group_observations_group_idx
            ON event_group_observations (group_id)
            """
        )
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS event_group_observations_fusion_event_id_key
            ON event_group_observations (event_id)
            WHERE observation_kind = 'fusion'
            """
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
                        created_at TEXT,
                        timing_version INTEGER,
                        timing_source TEXT,
                        capture_start_time_ms BIGINT,
                        event_start_sample BIGINT,
                        event_end_sample BIGINT,
                        rms_peak_sample BIGINT,
                        sample_rate_hz INTEGER,
                        channel_count INTEGER,
                        device_event_time_ms DOUBLE PRECISION,
                        event_start_time_ms DOUBLE PRECISION,
                        event_end_time_ms DOUBLE PRECISION,
                        rms_peak_time_ms BIGINT,
                        rms_peak_offset_ms DOUBLE PRECISION,
                        sample_rate INTEGER,
                        audio_duration_ms DOUBLE PRECISION,
                        time_sync_offset_ms DOUBLE PRECISION,
                        time_sync_rtt_ms DOUBLE PRECISION,
                        corrected_arrival_time_ms DOUBLE PRECISION,
                        timing_quality TEXT
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
                for statement in [
                    "ALTER TABLE events ADD COLUMN IF NOT EXISTS timing_version INTEGER",
                    "ALTER TABLE events ADD COLUMN IF NOT EXISTS timing_source TEXT",
                    "ALTER TABLE events ADD COLUMN IF NOT EXISTS capture_start_time_ms BIGINT",
                    "ALTER TABLE events ADD COLUMN IF NOT EXISTS event_start_sample BIGINT",
                    "ALTER TABLE events ADD COLUMN IF NOT EXISTS event_end_sample BIGINT",
                    "ALTER TABLE events ADD COLUMN IF NOT EXISTS rms_peak_sample BIGINT",
                    "ALTER TABLE events ADD COLUMN IF NOT EXISTS sample_rate_hz INTEGER",
                    "ALTER TABLE events ADD COLUMN IF NOT EXISTS channel_count INTEGER",
                    "ALTER TABLE events ADD COLUMN IF NOT EXISTS device_event_time_ms DOUBLE PRECISION",
                    "ALTER TABLE events ADD COLUMN IF NOT EXISTS event_start_time_ms DOUBLE PRECISION",
                    "ALTER TABLE events ADD COLUMN IF NOT EXISTS event_end_time_ms DOUBLE PRECISION",
                    "ALTER TABLE events ADD COLUMN IF NOT EXISTS rms_peak_time_ms BIGINT",
                    "ALTER TABLE events ADD COLUMN IF NOT EXISTS rms_peak_offset_ms DOUBLE PRECISION",
                    "ALTER TABLE events ADD COLUMN IF NOT EXISTS sample_rate INTEGER",
                    "ALTER TABLE events ADD COLUMN IF NOT EXISTS audio_duration_ms DOUBLE PRECISION",
                    "ALTER TABLE events ADD COLUMN IF NOT EXISTS time_sync_offset_ms DOUBLE PRECISION",
                    "ALTER TABLE events ADD COLUMN IF NOT EXISTS time_sync_rtt_ms DOUBLE PRECISION",
                    "ALTER TABLE events ADD COLUMN IF NOT EXISTS corrected_arrival_time_ms DOUBLE PRECISION",
                    "ALTER TABLE events ADD COLUMN IF NOT EXISTS timing_quality TEXT",
                ]:
                    cursor.execute(statement)
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
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS event_groups (
                        id UUID PRIMARY KEY,
                        group_kind TEXT DEFAULT 'fusion',
                        label TEXT,
                        group_label TEXT,
                        status TEXT DEFAULT 'ACTIVE',
                        first_event_time TIMESTAMPTZ,
                        start_time TIMESTAMPTZ,
                        last_event_time TIMESTAMPTZ,
                        end_time TIMESTAMPTZ,
                        node_count INTEGER,
                        estimated_lat DOUBLE PRECISION,
                        estimated_lng DOUBLE PRECISION,
                        localization_method TEXT,
                        confidence DOUBLE PRECISION,
                        uncertainty_radius_m DOUBLE PRECISION,
                        method TEXT,
                        tdoa_residual_rmse_m DOUBLE PRECISION,
                        tdoa_node_count INTEGER,
                        time_sync_quality TEXT,
                        created_at TIMESTAMPTZ DEFAULT now(),
                        updated_at TIMESTAMPTZ DEFAULT now()
                    )
                    """
                )
                for statement in [
                    "ALTER TABLE event_groups ADD COLUMN IF NOT EXISTS group_kind TEXT DEFAULT 'fusion'",
                    "ALTER TABLE event_groups ADD COLUMN IF NOT EXISTS label TEXT",
                    "ALTER TABLE event_groups ADD COLUMN IF NOT EXISTS group_label TEXT",
                    "ALTER TABLE event_groups ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'ACTIVE'",
                    "ALTER TABLE event_groups ADD COLUMN IF NOT EXISTS first_event_time TIMESTAMPTZ",
                    "ALTER TABLE event_groups ADD COLUMN IF NOT EXISTS start_time TIMESTAMPTZ",
                    "ALTER TABLE event_groups ADD COLUMN IF NOT EXISTS last_event_time TIMESTAMPTZ",
                    "ALTER TABLE event_groups ADD COLUMN IF NOT EXISTS end_time TIMESTAMPTZ",
                    "ALTER TABLE event_groups ADD COLUMN IF NOT EXISTS node_count INTEGER",
                    "ALTER TABLE event_groups ADD COLUMN IF NOT EXISTS estimated_lat DOUBLE PRECISION",
                    "ALTER TABLE event_groups ADD COLUMN IF NOT EXISTS estimated_lng DOUBLE PRECISION",
                    "ALTER TABLE event_groups ADD COLUMN IF NOT EXISTS localization_method TEXT",
                    "ALTER TABLE event_groups ADD COLUMN IF NOT EXISTS confidence DOUBLE PRECISION",
                    "ALTER TABLE event_groups ADD COLUMN IF NOT EXISTS uncertainty_radius_m DOUBLE PRECISION",
                    "ALTER TABLE event_groups ADD COLUMN IF NOT EXISTS method TEXT",
                    "ALTER TABLE event_groups ADD COLUMN IF NOT EXISTS tdoa_residual_rmse_m DOUBLE PRECISION",
                    "ALTER TABLE event_groups ADD COLUMN IF NOT EXISTS tdoa_node_count INTEGER",
                    "ALTER TABLE event_groups ADD COLUMN IF NOT EXISTS time_sync_quality TEXT",
                    "ALTER TABLE event_groups ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT now()",
                    "ALTER TABLE event_groups ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT now()",
                ]:
                    cursor.execute(statement)
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS event_group_observations (
                        id UUID PRIMARY KEY,
                        group_id UUID REFERENCES event_groups(id) ON DELETE CASCADE,
                        event_db_id BIGINT REFERENCES events(id),
                        event_id TEXT,
                        device_id TEXT,
                        label TEXT,
                        latitude DOUBLE PRECISION,
                        longitude DOUBLE PRECISION,
                        rms_peak DOUBLE PRECISION,
                        ai_probability DOUBLE PRECISION,
                        aircraft_probability DOUBLE PRECISION,
                        audio_path TEXT,
                        event_timestamp TIMESTAMPTZ,
                        timing_version INTEGER,
                        timing_source TEXT,
                        capture_start_time_ms BIGINT,
                        event_start_sample BIGINT,
                        event_end_sample BIGINT,
                        rms_peak_sample BIGINT,
                        sample_rate_hz INTEGER,
                        channel_count INTEGER,
                        audio_duration_ms BIGINT,
                        device_event_time_ms BIGINT,
                        event_end_time_ms BIGINT,
                        rms_peak_time_ms BIGINT,
                        weight DOUBLE PRECISION,
                        corrected_arrival_time_ms DOUBLE PRECISION,
                        time_sync_rtt_ms DOUBLE PRECISION,
                        tdoa_used BOOLEAN DEFAULT false,
                        tdoa_residual_m DOUBLE PRECISION,
                        observation_kind TEXT DEFAULT 'fusion',
                        created_at TIMESTAMPTZ DEFAULT now()
                    )
                    """
                )
                for statement in [
                    "ALTER TABLE event_group_observations ADD COLUMN IF NOT EXISTS group_id UUID",
                    "ALTER TABLE event_group_observations ADD COLUMN IF NOT EXISTS event_db_id BIGINT",
                    "ALTER TABLE event_group_observations ADD COLUMN IF NOT EXISTS event_id TEXT",
                    "ALTER TABLE event_group_observations ADD COLUMN IF NOT EXISTS device_id TEXT",
                    "ALTER TABLE event_group_observations ADD COLUMN IF NOT EXISTS label TEXT",
                    "ALTER TABLE event_group_observations ADD COLUMN IF NOT EXISTS latitude DOUBLE PRECISION",
                    "ALTER TABLE event_group_observations ADD COLUMN IF NOT EXISTS longitude DOUBLE PRECISION",
                    "ALTER TABLE event_group_observations ADD COLUMN IF NOT EXISTS rms_peak DOUBLE PRECISION",
                    "ALTER TABLE event_group_observations ADD COLUMN IF NOT EXISTS ai_probability DOUBLE PRECISION",
                    "ALTER TABLE event_group_observations ADD COLUMN IF NOT EXISTS aircraft_probability DOUBLE PRECISION",
                    "ALTER TABLE event_group_observations ADD COLUMN IF NOT EXISTS audio_path TEXT",
                    "ALTER TABLE event_group_observations ADD COLUMN IF NOT EXISTS event_timestamp TIMESTAMPTZ",
                    "ALTER TABLE event_group_observations ADD COLUMN IF NOT EXISTS timing_version INTEGER",
                    "ALTER TABLE event_group_observations ADD COLUMN IF NOT EXISTS timing_source TEXT",
                    "ALTER TABLE event_group_observations ADD COLUMN IF NOT EXISTS capture_start_time_ms BIGINT",
                    "ALTER TABLE event_group_observations ADD COLUMN IF NOT EXISTS event_start_sample BIGINT",
                    "ALTER TABLE event_group_observations ADD COLUMN IF NOT EXISTS event_end_sample BIGINT",
                    "ALTER TABLE event_group_observations ADD COLUMN IF NOT EXISTS rms_peak_sample BIGINT",
                    "ALTER TABLE event_group_observations ADD COLUMN IF NOT EXISTS sample_rate_hz INTEGER",
                    "ALTER TABLE event_group_observations ADD COLUMN IF NOT EXISTS channel_count INTEGER",
                    "ALTER TABLE event_group_observations ADD COLUMN IF NOT EXISTS audio_duration_ms BIGINT",
                    "ALTER TABLE event_group_observations ADD COLUMN IF NOT EXISTS device_event_time_ms BIGINT",
                    "ALTER TABLE event_group_observations ADD COLUMN IF NOT EXISTS event_end_time_ms BIGINT",
                    "ALTER TABLE event_group_observations ADD COLUMN IF NOT EXISTS rms_peak_time_ms BIGINT",
                    "ALTER TABLE event_group_observations ADD COLUMN IF NOT EXISTS weight DOUBLE PRECISION",
                    "ALTER TABLE event_group_observations ADD COLUMN IF NOT EXISTS corrected_arrival_time_ms DOUBLE PRECISION",
                    "ALTER TABLE event_group_observations ADD COLUMN IF NOT EXISTS time_sync_rtt_ms DOUBLE PRECISION",
                    "ALTER TABLE event_group_observations ADD COLUMN IF NOT EXISTS tdoa_used BOOLEAN DEFAULT false",
                    "ALTER TABLE event_group_observations ADD COLUMN IF NOT EXISTS tdoa_residual_m DOUBLE PRECISION",
                    "ALTER TABLE event_group_observations ADD COLUMN IF NOT EXISTS observation_kind TEXT DEFAULT 'fusion'",
                    "ALTER TABLE event_group_observations ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT now()",
                ]:
                    cursor.execute(statement)
                cursor.execute(
                    """
                    UPDATE event_groups
                    SET group_kind = 'target_estimate'
                    WHERE COALESCE(group_kind, 'fusion') = 'fusion'
                      AND (
                            estimated_lat IS NOT NULL
                         OR estimated_lng IS NOT NULL
                         OR uncertainty_radius_m IS NOT NULL
                         OR method IS NOT NULL
                         OR tdoa_residual_rmse_m IS NOT NULL
                      )
                    """
                )
                cursor.execute(
                    """
                    UPDATE event_group_observations
                    SET observation_kind = 'target_estimate'
                    WHERE COALESCE(observation_kind, 'fusion') = 'fusion'
                      AND (
                            weight IS NOT NULL
                         OR corrected_arrival_time_ms IS NOT NULL
                         OR time_sync_rtt_ms IS NOT NULL
                         OR tdoa_residual_m IS NOT NULL
                      )
                    """
                )
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS event_groups_updated_at_idx
                    ON event_groups (updated_at DESC)
                    """
                )
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS event_groups_fusion_lookup_idx
                    ON event_groups (label, status, last_event_time)
                    """
                )
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS event_group_observations_group_idx
                    ON event_group_observations (group_id)
                    """
                )
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS event_group_observations_event_id_idx
                    ON event_group_observations (event_id)
                    """
                )
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS event_group_observations_device_idx
                    ON event_group_observations (device_id)
                    """
                )
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS event_group_observations_time_idx
                    ON event_group_observations (event_timestamp)
                    """
                )
                cursor.execute(
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS event_group_observations_fusion_event_id_key
                    ON event_group_observations (event_id)
                    WHERE observation_kind = 'fusion'
                    """
                )
    finally:
        connection.close()


def init_db() -> None:
    if use_postgres():
        init_postgres_db()
    else:
        init_sqlite_db()


def corrected_arrival_time_ms(event: SoundEvent) -> Optional[float]:
    if (
        event.event_start_time_ms is not None
        and event.rms_peak_offset_ms is not None
        and event.time_sync_offset_ms is not None
    ):
        return (
            event.event_start_time_ms
            + event.rms_peak_offset_ms
            + event.time_sync_offset_ms
        )

    if event.device_event_time_ms is not None and event.time_sync_offset_ms is not None:
        return event.device_event_time_ms + event.time_sync_offset_ms

    return None


def timing_quality_for_event(event: SoundEvent) -> str:
    if corrected_arrival_time_ms(event) is None:
        return "missing"

    if event.time_sync_rtt_ms is None:
        return "missing"

    if event.time_sync_rtt_ms <= 50:
        return "good"
    if event.time_sync_rtt_ms <= 150:
        return "medium"
    if event.time_sync_rtt_ms <= 300:
        return "poor"
    return "poor"


def has_new_timing_metadata(event: SoundEvent) -> bool:
    return any(getattr(event, column) is not None for column in NEW_TIMING_METADATA_COLUMNS)


def sanitize_timing_metadata(event: SoundEvent) -> None:
    if not has_new_timing_metadata(event):
        return

    problems = []
    if event.timing_version is not None and event.timing_version < 1:
        problems.append("timing_version must be >= 1")
    if event.sample_rate_hz is not None and event.sample_rate_hz <= 0:
        problems.append("sample_rate_hz must be > 0")
    if event.channel_count is not None and event.channel_count <= 0:
        problems.append("channel_count must be > 0")
    for column in ("event_start_sample", "event_end_sample", "rms_peak_sample"):
        value = getattr(event, column)
        if value is not None and value < 0:
            problems.append(f"{column} must be >= 0")
    if event.audio_duration_ms is not None and event.audio_duration_ms < 0:
        problems.append("audio_duration_ms must be >= 0")
    if (
        event.event_start_sample is not None
        and event.event_end_sample is not None
        and event.event_end_sample < event.event_start_sample
    ):
        problems.append("event_end_sample must be >= event_start_sample")
    if (
        event.rms_peak_sample is not None
        and event.event_end_sample is not None
        and event.rms_peak_sample > event.event_end_sample
    ):
        problems.append("rms_peak_sample must be <= event_end_sample")

    if not problems:
        return

    logger.warning(
        "Invalid timing metadata ignored for event_id=%s: %s",
        event.event_id,
        "; ".join(problems),
    )
    for column in NEW_TIMING_METADATA_COLUMNS:
        setattr(event, column, None)
    event.audio_duration_ms = None


def event_values(event: SoundEvent, created_at: str) -> tuple:
    values = {
        "event_id": event.event_id,
        "device_id": event.device_id,
        "timestamp": event.timestamp,
        "latitude": event.latitude,
        "longitude": event.longitude,
        "duration_s": event.duration_s,
        "rms_peak": event.rms_peak,
        "label": event.label,
        "audio_file_name": event.audio_file_name,
        "local_audio_path": event.local_audio_path,
        "audio_path": event.audio_path,
        "note": event.note,
        "created_at": created_at,
        "timing_version": event.timing_version,
        "timing_source": event.timing_source,
        "capture_start_time_ms": event.capture_start_time_ms,
        "event_start_sample": event.event_start_sample,
        "event_end_sample": event.event_end_sample,
        "rms_peak_sample": event.rms_peak_sample,
        "sample_rate_hz": event.sample_rate_hz,
        "channel_count": event.channel_count,
        "device_event_time_ms": event.device_event_time_ms,
        "event_start_time_ms": event.event_start_time_ms,
        "event_end_time_ms": event.event_end_time_ms,
        "rms_peak_time_ms": event.rms_peak_time_ms,
        "rms_peak_offset_ms": event.rms_peak_offset_ms,
        "sample_rate": event.sample_rate,
        "audio_duration_ms": event.audio_duration_ms,
        "time_sync_offset_ms": event.time_sync_offset_ms,
        "time_sync_rtt_ms": event.time_sync_rtt_ms,
        "corrected_arrival_time_ms": corrected_arrival_time_ms(event),
        "timing_quality": timing_quality_for_event(event),
    }
    return tuple(values[column] for column in EVENT_WRITE_COLUMNS)


def upsert_event_postgres(event: SoundEvent, created_at: str) -> int:
    columns = ", ".join(EVENT_WRITE_COLUMNS)
    placeholders = ", ".join(["%s"] * len(EVENT_WRITE_COLUMNS))
    update_columns = [column for column in EVENT_WRITE_COLUMNS if column != "event_id"]
    update_clause = ",\n                        ".join(
        f"{column} = EXCLUDED.{column}" for column in update_columns
    )
    connection = get_postgres_connection()
    try:
        with connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    INSERT INTO events ({columns})
                    VALUES ({placeholders})
                    ON CONFLICT (event_id) DO UPDATE SET
                        {update_clause}
                    RETURNING id
                    """,
                    event_values(event, created_at),
                )
                row = cursor.fetchone()
                return int(row["id"])
    finally:
        connection.close()


def upsert_event_sqlite(event: SoundEvent, created_at: str) -> int:
    columns = ", ".join(EVENT_WRITE_COLUMNS)
    placeholders = ", ".join(["?"] * len(EVENT_WRITE_COLUMNS))
    update_columns = [column for column in EVENT_WRITE_COLUMNS if column != "event_id"]
    update_clause = ",\n                    ".join(
        f"{column} = ?" for column in update_columns
    )
    values = event_values(event, created_at)
    with get_sqlite_connection() as connection:
        existing = connection.execute(
            "SELECT id FROM events WHERE event_id = ? LIMIT 1",
            (event.event_id,),
        ).fetchone()

        if existing:
            db_id = int(existing["id"])
            connection.execute(
                f"""
                UPDATE events
                SET
                    {update_clause}
                WHERE id = ?
                """,
                values[1:] + (db_id,),
            )
        else:
            cursor = connection.execute(
                f"""
                INSERT INTO events ({columns})
                VALUES ({placeholders})
                """,
                values,
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


def get_event_by_event_id(event_id: str) -> Optional[dict]:
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
                        WHERE event_id = %s
                        LIMIT 1
                        """,
                        (event_id,),
                    )
                    row = cursor.fetchone()
                    return serialize_db_row(dict(row)) if row else None
        finally:
            connection.close()

    with get_sqlite_connection() as connection:
        row = connection.execute(
            f"""
            SELECT {columns}
            FROM events
            WHERE event_id = ?
            LIMIT 1
            """,
            (event_id,),
        ).fetchone()
        return serialize_db_row(dict(row)) if row else None


def process_event_fusion_for_event(event_id: str) -> Optional[dict]:
    event_record = get_event_by_event_id(event_id)
    if not event_record:
        return None

    if use_postgres():
        connection = get_postgres_connection()
        try:
            with connection:
                return process_fusion_event(
                    connection=connection,
                    event_record=event_record,
                    is_postgres=True,
                    window_seconds=EVENT_FUSION_WINDOW_SECONDS,
                )
        finally:
            connection.close()

    with get_sqlite_connection() as connection:
        return process_fusion_event(
            connection=connection,
            event_record=event_record,
            is_postgres=False,
            window_seconds=EVENT_FUSION_WINDOW_SECONDS,
        )


def list_event_fusion_groups(
    limit: int = 20,
    status_filter: Optional[str] = None,
    label_filter: Optional[str] = None,
) -> list[dict]:
    if use_postgres():
        connection = get_postgres_connection()
        try:
            with connection:
                return list_fusion_groups(
                    connection=connection,
                    is_postgres=True,
                    limit=limit,
                    status=status_filter,
                    label=label_filter,
                )
        finally:
            connection.close()

    with get_sqlite_connection() as connection:
        return list_fusion_groups(
            connection=connection,
            is_postgres=False,
            limit=limit,
            status=status_filter,
            label=label_filter,
        )


def get_event_fusion_group(group_id: str) -> Optional[dict]:
    if use_postgres():
        connection = get_postgres_connection()
        try:
            with connection:
                return get_fusion_group_detail(
                    connection=connection,
                    group_id=group_id,
                    is_postgres=True,
                )
        finally:
            connection.close()

    with get_sqlite_connection() as connection:
        return get_fusion_group_detail(
            connection=connection,
            group_id=group_id,
            is_postgres=False,
        )


def serialize_db_row(row: dict) -> dict:
    serialized = {}
    for key, value in row.items():
        if hasattr(value, "isoformat"):
            serialized[key] = value.isoformat()
        else:
            serialized[key] = value
    if "is_listening" in serialized and serialized["is_listening"] is not None:
        serialized["is_listening"] = bool(serialized["is_listening"])
    if "tdoa_used" in serialized and serialized["tdoa_used"] is not None:
        serialized["tdoa_used"] = bool(serialized["tdoa_used"])
    if "status" in serialized and "last_seen" in serialized:
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
                columns = ", ".join(DEVICE_STATUS_COLUMNS)
                cursor.execute(
                    f"""
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
            now = current_time_iso()
            connection.execute(
                """
                INSERT INTO device_status (
                    device_id,
                    last_seen,
                    status,
                    backend_status,
                    app_status,
                    updated_at
                )
                VALUES (?, ?, 'online', 'connected', 'polling', ?)
                ON CONFLICT(device_id) DO UPDATE SET
                    last_seen = excluded.last_seen,
                    status = 'online',
                    backend_status = 'connected',
                    app_status = COALESCE(device_status.app_status, 'polling'),
                    updated_at = excluded.updated_at
                """,
                (device_id, now, now),
            )
            connection.commit()
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
                    """
                    INSERT INTO device_status (
                        device_id,
                        last_seen,
                        status,
                        backend_status,
                        app_status,
                        updated_at
                    )
                    VALUES (%s, now(), 'online', 'connected', 'polling', now())
                    ON CONFLICT (device_id) DO UPDATE SET
                        last_seen = now(),
                        status = 'online',
                        backend_status = 'connected',
                        app_status = COALESCE(device_status.app_status, 'polling'),
                        updated_at = now()
                    """,
                    (device_id,),
                )
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
            command_row = connection.execute(
                """
                SELECT command
                FROM device_commands
                WHERE id = ?
                  AND device_id = ?
                LIMIT 1
                """,
                (ack.command_id, ack.device_id),
            ).fetchone()
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
            command_name = command_row["command"] if command_row else ""
            state_command_name = command_name if normalized_status == "done" else ""
            connection.execute(
                """
                INSERT INTO device_status (
                    device_id,
                    last_seen,
                    status,
                    backend_status,
                    app_status,
                    is_listening,
                    upload_mode,
                    last_command_id,
                    updated_at
                )
                VALUES (
                    ?,
                    ?,
                    'online',
                    'connected',
                    CASE
                        WHEN ? = 'start_listening' THEN 'listening'
                        WHEN ? = 'stop_listening' THEN 'stopped'
                        ELSE 'polling'
                    END,
                    CASE
                        WHEN ? = 'start_listening' THEN 1
                        WHEN ? = 'stop_listening' THEN 0
                        ELSE NULL
                    END,
                    CASE
                        WHEN ? = 'set_detection_mode' THEN 'detection'
                        WHEN ? = 'set_collection_mode' THEN 'collection'
                        ELSE NULL
                    END,
                    ?,
                    ?
                )
                ON CONFLICT(device_id) DO UPDATE SET
                    last_seen = excluded.last_seen,
                    status = 'online',
                    backend_status = 'connected',
                    app_status = CASE
                        WHEN ? = 'start_listening' THEN 'listening'
                        WHEN ? = 'stop_listening' THEN 'stopped'
                        ELSE device_status.app_status
                    END,
                    is_listening = CASE
                        WHEN ? = 'start_listening' THEN 1
                        WHEN ? = 'stop_listening' THEN 0
                        ELSE device_status.is_listening
                    END,
                    upload_mode = CASE
                        WHEN ? = 'set_detection_mode' THEN 'detection'
                        WHEN ? = 'set_collection_mode' THEN 'collection'
                        ELSE device_status.upload_mode
                    END,
                    last_command_id = excluded.last_command_id,
                    updated_at = excluded.updated_at
                """,
                (
                    ack.device_id,
                    executed_at,
                    state_command_name,
                    state_command_name,
                    state_command_name,
                    state_command_name,
                    state_command_name,
                    state_command_name,
                    ack.command_id,
                    executed_at,
                    state_command_name,
                    state_command_name,
                    state_command_name,
                    state_command_name,
                    state_command_name,
                    state_command_name,
                ),
            )
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
                    RETURNING id, status, command
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
                command_name = row["command"]
                state_command_name = command_name if normalized_status == "done" else ""
                cursor.execute(
                    """
                    INSERT INTO device_status (
                        device_id,
                        last_seen,
                        status,
                        backend_status,
                        app_status,
                        is_listening,
                        upload_mode,
                        last_command_id,
                        updated_at
                    )
                    VALUES (
                        %s,
                        now(),
                        'online',
                        'connected',
                        CASE
                            WHEN %s = 'start_listening' THEN 'listening'
                            WHEN %s = 'stop_listening' THEN 'stopped'
                            ELSE 'polling'
                        END,
                        CASE
                            WHEN %s = 'start_listening' THEN TRUE
                            WHEN %s = 'stop_listening' THEN FALSE
                            ELSE NULL
                        END,
                        CASE
                            WHEN %s = 'set_detection_mode' THEN 'detection'
                            WHEN %s = 'set_collection_mode' THEN 'collection'
                            ELSE NULL
                        END,
                        %s,
                        now()
                    )
                    ON CONFLICT (device_id) DO UPDATE SET
                        last_seen = now(),
                        status = 'online',
                        backend_status = 'connected',
                        app_status = CASE
                            WHEN %s = 'start_listening' THEN 'listening'
                            WHEN %s = 'stop_listening' THEN 'stopped'
                            ELSE device_status.app_status
                        END,
                        is_listening = CASE
                            WHEN %s = 'start_listening' THEN TRUE
                            WHEN %s = 'stop_listening' THEN FALSE
                            ELSE device_status.is_listening
                        END,
                        upload_mode = CASE
                            WHEN %s = 'set_detection_mode' THEN 'detection'
                            WHEN %s = 'set_collection_mode' THEN 'collection'
                            ELSE device_status.upload_mode
                        END,
                        last_command_id = EXCLUDED.last_command_id,
                        updated_at = now()
                    """,
                    (
                        ack.device_id,
                        state_command_name,
                        state_command_name,
                        state_command_name,
                        state_command_name,
                        state_command_name,
                        state_command_name,
                        ack.command_id,
                        state_command_name,
                        state_command_name,
                        state_command_name,
                        state_command_name,
                        state_command_name,
                        state_command_name,
                    ),
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


def parse_float_value(value: Any) -> Optional[float]:
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


def event_aircraft_probability(row: dict) -> Optional[float]:
    note = row.get("note")
    probability = parse_float_value(parse_note_field(note, "probability_aircraft"))
    if probability is None:
        probability = parse_float_value(parse_note_field(note, "aircraft_probability"))
    if probability is None:
        return None
    return max(0.0, min(1.0, probability))


def event_timestamp_for_fusion(row: dict) -> Optional[datetime]:
    corrected = parse_float_value(row.get("corrected_arrival_time_ms"))
    if corrected is not None:
        return datetime.fromtimestamp(corrected / 1000.0, tz=timezone.utc)
    return parse_datetime(row.get("timestamp")) or parse_datetime(row.get("created_at"))


def fusion_weight(rms_peak: Any, aircraft_probability: Optional[float]) -> float:
    rms_value = parse_float_value(rms_peak)
    base_weight = 1.0 + math.log1p(max(rms_value or 0.0, 0.0))
    if aircraft_probability is None:
        return max(base_weight, 1e-6)
    return max(base_weight * max(aircraft_probability, 1e-6), 1e-6)


def fusion_confidence(node_count: int) -> float:
    if node_count >= 4:
        return 0.80
    if node_count == 3:
        return 0.65
    return 0.45


def fusion_uncertainty_radius(node_count: int) -> float:
    if node_count >= 4:
        return 40.0
    if node_count == 3:
        return 60.0
    return 100.0


def group_time_sync_quality(rtts: list[float]) -> str:
    if not rtts:
        return "missing"

    average_rtt = sum(rtts) / len(rtts)
    if average_rtt <= 50:
        return "good"
    if average_rtt <= 150:
        return "medium"
    if average_rtt <= 300:
        return "poor"
    return "poor"


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    radius = 6_371_000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return 2 * radius * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def local_origin(observations: list[dict]) -> tuple[float, float]:
    return (
        sum(float(item["latitude"]) for item in observations) / len(observations),
        sum(float(item["longitude"]) for item in observations) / len(observations),
    )


def latlng_to_local_xy(
    lat: float,
    lng: float,
    origin_lat: float,
    origin_lng: float,
) -> tuple[float, float]:
    meters_per_degree_lat = 111_320.0
    meters_per_degree_lng = meters_per_degree_lat * math.cos(math.radians(origin_lat))
    return (
        (lng - origin_lng) * meters_per_degree_lng,
        (lat - origin_lat) * meters_per_degree_lat,
    )


def local_xy_to_latlng(
    x: float,
    y: float,
    origin_lat: float,
    origin_lng: float,
) -> tuple[float, float]:
    meters_per_degree_lat = 111_320.0
    meters_per_degree_lng = meters_per_degree_lat * math.cos(math.radians(origin_lat))
    return (
        origin_lat + (y / meters_per_degree_lat),
        origin_lng + (x / meters_per_degree_lng),
    )


def weighted_centroid_latlng(observations: list[dict]) -> tuple[float, float]:
    total_weight = sum(max(float(item.get("weight") or 0.0), 1e-6) for item in observations)
    return (
        sum(float(item["latitude"]) * float(item.get("weight") or 1.0) for item in observations)
        / total_weight,
        sum(float(item["longitude"]) * float(item.get("weight") or 1.0) for item in observations)
        / total_weight,
    )


def tdoa_uncertainty_radius(
    node_count: int,
    average_rtt_ms: float,
    residual_rmse_m: float,
    quality: str,
) -> float:
    node_bonus = 30.0 if node_count == 3 else 15.0 if node_count == 4 else 0.0
    uncertainty = 30.0 + (average_rtt_ms * 0.343) + residual_rmse_m + node_bonus
    if quality == "poor":
        uncertainty = max(uncertainty, 100.0)
    return max(30.0, uncertainty)


def tdoa_confidence(
    node_count: int,
    average_rtt_ms: float,
    residual_rmse_m: float,
    quality: str,
) -> float:
    quality_penalty = {"good": 0.0, "medium": 0.08, "poor": 0.18}.get(quality, 0.25)
    score = 0.72 + min(max(node_count - 3, 0), 3) * 0.05
    score -= min(average_rtt_ms, 300.0) / 1500.0
    score -= min(residual_rmse_m, 150.0) / 400.0
    score -= quality_penalty
    return max(0.35, min(0.92, score))


def estimate_position_tdoa(observations: list[dict]) -> dict:
    node_ids = {str(item.get("device_id")) for item in observations if item.get("device_id")}
    if len(node_ids) < 3:
        return {"success": False, "reason": "insufficient_nodes"}

    usable = []
    for item in observations:
        corrected = parse_float_value(item.get("corrected_arrival_time_ms"))
        rtt = parse_float_value(item.get("time_sync_rtt_ms"))
        if (
            item.get("latitude") is None
            or item.get("longitude") is None
            or corrected is None
            or rtt is None
        ):
            return {"success": False, "reason": "insufficient_timing"}
        if rtt > TDOA_MAX_RTT_MS:
            return {"success": False, "reason": "poor_time_sync"}
        usable.append({**item, "corrected_arrival_time_ms": corrected, "time_sync_rtt_ms": rtt})

    max_distance = 0.0
    for i, first in enumerate(usable):
        for second in usable[i + 1 :]:
            max_distance = max(
                max_distance,
                haversine_m(
                    float(first["latitude"]),
                    float(first["longitude"]),
                    float(second["latitude"]),
                    float(second["longitude"]),
                ),
            )
    if max_distance < TDOA_MIN_NODE_SPREAD_M:
        return {"success": False, "reason": "insufficient_node_spread"}

    corrected_times = [float(item["corrected_arrival_time_ms"]) for item in usable]
    max_dt_s = (max(corrected_times) - min(corrected_times)) / 1000.0
    max_allowed_dt_s = (max_distance / SOUND_SPEED_MPS) + TDOA_TIME_TOLERANCE_SECONDS
    if max_dt_s > max_allowed_dt_s:
        return {"success": False, "reason": "unreasonable_tdoa"}

    try:
        from scipy.optimize import least_squares
    except Exception:
        return {"success": False, "reason": "scipy_unavailable"}

    origin_lat, origin_lng = local_origin(usable)
    nodes = []
    for item in usable:
        x, y = latlng_to_local_xy(
            float(item["latitude"]),
            float(item["longitude"]),
            origin_lat,
            origin_lng,
        )
        nodes.append({**item, "x": x, "y": y})

    reference = min(nodes, key=lambda item: float(item["corrected_arrival_time_ms"]))
    centroid_lat, centroid_lng = weighted_centroid_latlng(usable)
    initial_x, initial_y = latlng_to_local_xy(centroid_lat, centroid_lng, origin_lat, origin_lng)

    def residuals(params: Any) -> list[float]:
        source_x = float(params[0])
        source_y = float(params[1])
        reference_distance = math.hypot(source_x - reference["x"], source_y - reference["y"])
        values = []
        for node in nodes:
            if node["device_id"] == reference["device_id"]:
                continue
            distance = math.hypot(source_x - node["x"], source_y - node["y"])
            dt_s = (
                float(node["corrected_arrival_time_ms"])
                - float(reference["corrected_arrival_time_ms"])
            ) / 1000.0
            values.append((distance - reference_distance) - (SOUND_SPEED_MPS * dt_s))
        return values

    try:
        result = least_squares(residuals, [initial_x, initial_y])
    except Exception:
        return {"success": False, "reason": "tdoa_solver_failed"}

    source_x = float(result.x[0])
    source_y = float(result.x[1])
    min_x = min(node["x"] for node in nodes) - TDOA_MAX_OUTSIDE_BOUNDS_M
    max_x = max(node["x"] for node in nodes) + TDOA_MAX_OUTSIDE_BOUNDS_M
    min_y = min(node["y"] for node in nodes) - TDOA_MAX_OUTSIDE_BOUNDS_M
    max_y = max(node["y"] for node in nodes) + TDOA_MAX_OUTSIDE_BOUNDS_M
    if not (min_x <= source_x <= max_x and min_y <= source_y <= max_y):
        return {"success": False, "reason": "tdoa_out_of_bounds"}

    residual_values = residuals([source_x, source_y])
    residual_rmse = math.sqrt(
        sum(value * value for value in residual_values) / max(len(residual_values), 1)
    )
    average_rtt = sum(float(item["time_sync_rtt_ms"]) for item in usable) / len(usable)
    quality = group_time_sync_quality([float(item["time_sync_rtt_ms"]) for item in usable])
    estimated_lat, estimated_lng = local_xy_to_latlng(source_x, source_y, origin_lat, origin_lng)

    residual_by_device = {str(reference["device_id"]): 0.0}
    for node, residual in zip(
        [node for node in nodes if node["device_id"] != reference["device_id"]],
        residual_values,
    ):
        residual_by_device[str(node["device_id"])] = float(residual)

    return {
        "success": True,
        "estimated_lat": estimated_lat,
        "estimated_lng": estimated_lng,
        "residual_rmse_m": residual_rmse,
        "average_rtt_ms": average_rtt,
        "time_sync_quality": quality,
        "uncertainty_radius_m": tdoa_uncertainty_radius(
            len(node_ids),
            average_rtt,
            residual_rmse,
            quality,
        ),
        "confidence": tdoa_confidence(len(node_ids), average_rtt, residual_rmse, quality),
        "residual_by_device": residual_by_device,
        "used_device_ids": [str(item["device_id"]) for item in usable],
    }


def list_recent_target_events_for_fusion() -> list[dict]:
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
                        WHERE LOWER(label) IN ('aircraft', 'drone')
                          AND latitude IS NOT NULL
                          AND longitude IS NOT NULL
                        ORDER BY id DESC
                        LIMIT 100
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
            WHERE LOWER(label) IN ('aircraft', 'drone')
              AND latitude IS NOT NULL
              AND longitude IS NOT NULL
            ORDER BY id DESC
            LIMIT 100
            """
        ).fetchall()
        return [serialize_db_row(dict(row)) for row in rows]


def build_fusion_observations(event: SoundEvent, created_at: str) -> list[dict]:
    if not is_alert_event_label(event.label):
        return []
    if event.latitude is None or event.longitude is None:
        return []

    reference_time = parse_datetime(event.timestamp) or parse_datetime(created_at)
    if reference_time is None:
        reference_time = datetime.now(timezone.utc)

    window = timedelta(seconds=EVENT_GROUP_WINDOW_SECONDS)
    selected_by_device: dict[str, dict] = {}

    for row in list_recent_target_events_for_fusion():
        event_time = event_timestamp_for_fusion(row)
        if event_time is None:
            continue
        if event_time < reference_time - window or event_time > reference_time + window:
            continue
        if row.get("device_id") is None:
            continue
        if row.get("latitude") is None or row.get("longitude") is None:
            continue

        device_id = str(row.get("device_id"))
        probability = event_aircraft_probability(row)
        weight = fusion_weight(row.get("rms_peak"), probability)
        candidate = {
            "event_id": row.get("event_id"),
            "device_id": device_id,
            "latitude": float(row.get("latitude")),
            "longitude": float(row.get("longitude")),
            "rms_peak": parse_float_value(row.get("rms_peak")),
            "aircraft_probability": probability,
            "event_timestamp": event_time,
            "weight": weight,
            "label": row.get("label") or "aircraft",
            "corrected_arrival_time_ms": parse_float_value(
                row.get("corrected_arrival_time_ms")
            ),
            "time_sync_rtt_ms": parse_float_value(row.get("time_sync_rtt_ms")),
            "tdoa_used": False,
            "tdoa_residual_m": None,
        }

        existing = selected_by_device.get(device_id)
        if existing is None:
            selected_by_device[device_id] = candidate
            continue

        existing_time = existing.get("event_timestamp")
        if isinstance(existing_time, datetime) and event_time > existing_time:
            selected_by_device[device_id] = candidate

    observations = list(selected_by_device.values())
    observations.sort(key=lambda item: item["device_id"])
    return observations


def weighted_centroid_estimate(
    observations: list[dict],
    method: str = TARGET_ESTIMATE_METHOD,
    time_sync_quality: Optional[str] = None,
) -> Optional[dict]:
    if len(observations) < 2:
        return None

    total_weight = sum(max(float(item.get("weight") or 0.0), 1e-6) for item in observations)
    if total_weight <= 0:
        return None

    estimated_lat = sum(item["latitude"] * item["weight"] for item in observations) / total_weight
    estimated_lng = sum(item["longitude"] * item["weight"] for item in observations) / total_weight
    event_times = [item["event_timestamp"] for item in observations if item.get("event_timestamp")]
    node_count = len({item["device_id"] for item in observations})
    labels = [str(item.get("label") or "").lower() for item in observations]
    group_label = "drone" if "drone" in labels else "aircraft"
    now = current_time_iso()

    return {
        "id": str(uuid.uuid4()),
        "group_label": group_label,
        "start_time": min(event_times).isoformat() if event_times else now,
        "end_time": max(event_times).isoformat() if event_times else now,
        "node_count": node_count,
        "estimated_lat": estimated_lat,
        "estimated_lng": estimated_lng,
        "confidence": fusion_confidence(node_count),
        "uncertainty_radius_m": fusion_uncertainty_radius(node_count),
        "method": method,
        "tdoa_residual_rmse_m": None,
        "tdoa_node_count": None,
        "time_sync_quality": time_sync_quality,
        "created_at": now,
        "updated_at": now,
        "devices": [item["device_id"] for item in observations],
        "observations": observations,
    }


def target_estimate_from_observations(observations: list[dict]) -> Optional[dict]:
    if len(observations) < 2:
        return None

    node_count = len({item["device_id"] for item in observations})
    tdoa_result = estimate_position_tdoa(observations)

    if tdoa_result.get("success"):
        weighted = weighted_centroid_estimate(
            observations,
            method=TDOA_ESTIMATE_METHOD,
            time_sync_quality=tdoa_result.get("time_sync_quality"),
        )
        if weighted is None:
            return None

        used_devices = set(tdoa_result.get("used_device_ids") or [])
        residual_by_device = tdoa_result.get("residual_by_device") or {}
        for item in weighted["observations"]:
            item["tdoa_used"] = item.get("device_id") in used_devices
            item["tdoa_residual_m"] = residual_by_device.get(str(item.get("device_id")))

        weighted["estimated_lat"] = tdoa_result["estimated_lat"]
        weighted["estimated_lng"] = tdoa_result["estimated_lng"]
        weighted["confidence"] = tdoa_result["confidence"]
        weighted["uncertainty_radius_m"] = tdoa_result["uncertainty_radius_m"]
        weighted["method"] = TDOA_ESTIMATE_METHOD
        weighted["tdoa_residual_rmse_m"] = tdoa_result["residual_rmse_m"]
        weighted["tdoa_node_count"] = node_count
        weighted["time_sync_quality"] = tdoa_result.get("time_sync_quality")
        return weighted

    fallback_method = TDOA_FALLBACK_METHOD if node_count >= 3 else TARGET_ESTIMATE_METHOD
    fallback_quality = tdoa_result.get("reason") or "insufficient"
    return weighted_centroid_estimate(
        observations,
        method=fallback_method,
        time_sync_quality=fallback_quality,
    )


def store_target_estimate(estimate: dict) -> dict:
    group_id = estimate["id"]
    observations = estimate.get("observations", [])

    if use_postgres():
        connection = get_postgres_connection()
        try:
            with connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO event_groups (
                            id,
                            group_kind,
                            label,
                            group_label,
                            status,
                            first_event_time,
                            start_time,
                            last_event_time,
                            end_time,
                            node_count,
                            estimated_lat,
                            estimated_lng,
                            localization_method,
                            confidence,
                            uncertainty_radius_m,
                            method,
                            tdoa_residual_rmse_m,
                            tdoa_node_count,
                            time_sync_quality,
                            created_at,
                            updated_at
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            group_id,
                            "target_estimate",
                            estimate["group_label"],
                            estimate["group_label"],
                            "CLOSED",
                            estimate["start_time"],
                            estimate["start_time"],
                            estimate["end_time"],
                            estimate["end_time"],
                            estimate["node_count"],
                            estimate["estimated_lat"],
                            estimate["estimated_lng"],
                            estimate["method"],
                            estimate["confidence"],
                            estimate["uncertainty_radius_m"],
                            estimate["method"],
                            estimate.get("tdoa_residual_rmse_m"),
                            estimate.get("tdoa_node_count"),
                            estimate.get("time_sync_quality"),
                            estimate["created_at"],
                            estimate["updated_at"],
                        ),
                    )
                    for item in observations:
                        cursor.execute(
                            """
                            INSERT INTO event_group_observations (
                                id,
                                group_id,
                                event_id,
                                device_id,
                                label,
                                latitude,
                                longitude,
                                rms_peak,
                                ai_probability,
                                aircraft_probability,
                                audio_path,
                                event_timestamp,
                                weight,
                                corrected_arrival_time_ms,
                                time_sync_rtt_ms,
                                tdoa_used,
                                tdoa_residual_m,
                                observation_kind,
                                created_at
                            )
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            """,
                            (
                                str(uuid.uuid4()),
                                group_id,
                                item.get("event_id"),
                                item.get("device_id"),
                                item.get("label"),
                                item.get("latitude"),
                                item.get("longitude"),
                                item.get("rms_peak"),
                                item.get("aircraft_probability"),
                                item.get("aircraft_probability"),
                                item.get("audio_path"),
                                item.get("event_timestamp").isoformat()
                                if hasattr(item.get("event_timestamp"), "isoformat")
                                else item.get("event_timestamp"),
                                item.get("weight"),
                                item.get("corrected_arrival_time_ms"),
                                item.get("time_sync_rtt_ms"),
                                bool(item.get("tdoa_used")),
                                item.get("tdoa_residual_m"),
                                "target_estimate",
                                estimate["created_at"],
                            ),
                        )
        finally:
            connection.close()
    else:
        with get_sqlite_connection() as connection:
            connection.execute(
                """
                INSERT INTO event_groups (
                    id,
                    group_kind,
                    label,
                    group_label,
                    status,
                    first_event_time,
                    start_time,
                    last_event_time,
                    end_time,
                    node_count,
                    estimated_lat,
                    estimated_lng,
                    localization_method,
                    confidence,
                    uncertainty_radius_m,
                    method,
                    tdoa_residual_rmse_m,
                    tdoa_node_count,
                    time_sync_quality,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    group_id,
                    "target_estimate",
                    estimate["group_label"],
                    estimate["group_label"],
                    "CLOSED",
                    estimate["start_time"],
                    estimate["start_time"],
                    estimate["end_time"],
                    estimate["end_time"],
                    estimate["node_count"],
                    estimate["estimated_lat"],
                    estimate["estimated_lng"],
                    estimate["method"],
                    estimate["confidence"],
                    estimate["uncertainty_radius_m"],
                    estimate["method"],
                    estimate.get("tdoa_residual_rmse_m"),
                    estimate.get("tdoa_node_count"),
                    estimate.get("time_sync_quality"),
                    estimate["created_at"],
                    estimate["updated_at"],
                ),
            )
            for item in observations:
                timestamp = item.get("event_timestamp")
                connection.execute(
                    """
                    INSERT INTO event_group_observations (
                        id,
                        group_id,
                        event_id,
                        device_id,
                        label,
                        latitude,
                        longitude,
                        rms_peak,
                        ai_probability,
                        aircraft_probability,
                        audio_path,
                        event_timestamp,
                        weight,
                        corrected_arrival_time_ms,
                        time_sync_rtt_ms,
                        tdoa_used,
                        tdoa_residual_m,
                        observation_kind,
                        created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid.uuid4()),
                        group_id,
                        item.get("event_id"),
                        item.get("device_id"),
                        item.get("label"),
                        item.get("latitude"),
                        item.get("longitude"),
                        item.get("rms_peak"),
                        item.get("aircraft_probability"),
                        item.get("aircraft_probability"),
                        item.get("audio_path"),
                        timestamp.isoformat() if hasattr(timestamp, "isoformat") else timestamp,
                        item.get("weight"),
                        item.get("corrected_arrival_time_ms"),
                        item.get("time_sync_rtt_ms"),
                        1 if item.get("tdoa_used") else 0,
                        item.get("tdoa_residual_m"),
                        "target_estimate",
                        estimate["created_at"],
                    ),
                )
            connection.commit()

    return target_estimate_payload(estimate)


def create_target_estimate_for_event(
    event: SoundEvent,
    created_at: str,
) -> Optional[dict]:
    observations = build_fusion_observations(event, created_at)
    estimate = target_estimate_from_observations(observations)
    if estimate is None:
        return None
    return store_target_estimate(estimate)


def target_estimate_payload(estimate: dict) -> dict:
    group_id = estimate.get("id")
    observations = []
    for item in estimate.get("observations", []) or []:
        observations.append(
            {
                "device_id": item.get("device_id"),
                "corrected_arrival_time_ms": item.get("corrected_arrival_time_ms"),
                "time_sync_rtt_ms": item.get("time_sync_rtt_ms"),
                "tdoa_used": bool(item.get("tdoa_used")),
                "tdoa_residual_m": item.get("tdoa_residual_m"),
            }
        )

    return {
        "group_id": str(group_id) if group_id is not None else None,
        "label": estimate.get("group_label"),
        "estimated_lat": estimate.get("estimated_lat"),
        "estimated_lng": estimate.get("estimated_lng"),
        "confidence": estimate.get("confidence"),
        "uncertainty_radius_m": estimate.get("uncertainty_radius_m"),
        "method": estimate.get("method"),
        "node_count": estimate.get("node_count"),
        "devices": estimate.get("devices", []),
        "tdoa_residual_rmse_m": estimate.get("tdoa_residual_rmse_m"),
        "tdoa_node_count": estimate.get("tdoa_node_count"),
        "time_sync_quality": estimate.get("time_sync_quality"),
        "observations": observations,
        "created_at": estimate.get("created_at"),
        "updated_at": estimate.get("updated_at"),
    }


def list_target_estimates(limit: int = 10) -> list[dict]:
    safe_limit = max(1, min(limit, 100))
    columns = ", ".join(EVENT_GROUP_COLUMNS)

    if use_postgres():
        connection = get_postgres_connection()
        try:
            with connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        f"""
                        SELECT {columns}
                        FROM event_groups
                        WHERE COALESCE(group_kind, 'target_estimate') = 'target_estimate'
                        ORDER BY updated_at DESC
                        LIMIT %s
                        """,
                        (safe_limit,),
                    )
                    groups = [serialize_db_row(dict(row)) for row in cursor.fetchall()]
                    for group in groups:
                        cursor.execute(
                            """
                            SELECT
                                device_id,
                                corrected_arrival_time_ms,
                                time_sync_rtt_ms,
                                tdoa_used,
                                tdoa_residual_m
                            FROM event_group_observations
                            WHERE group_id = %s
                              AND COALESCE(observation_kind, 'target_estimate') = 'target_estimate'
                            ORDER BY device_id ASC
                            """,
                            (group["id"],),
                        )
                        observation_rows = [serialize_db_row(dict(row)) for row in cursor.fetchall()]
                        group["devices"] = [
                            row["device_id"] for row in observation_rows if row.get("device_id")
                        ]
                        group["observations"] = observation_rows
                    return [target_estimate_payload(group) for group in groups]
        finally:
            connection.close()

    with get_sqlite_connection() as connection:
        rows = connection.execute(
            f"""
            SELECT {columns}
            FROM event_groups
            WHERE COALESCE(group_kind, 'target_estimate') = 'target_estimate'
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (safe_limit,),
        ).fetchall()
        groups = [serialize_db_row(dict(row)) for row in rows]
        for group in groups:
            device_rows = connection.execute(
                """
                SELECT
                    device_id,
                    corrected_arrival_time_ms,
                    time_sync_rtt_ms,
                    tdoa_used,
                    tdoa_residual_m
                FROM event_group_observations
                WHERE group_id = ?
                  AND COALESCE(observation_kind, 'target_estimate') = 'target_estimate'
                ORDER BY device_id ASC
                """,
                (group["id"],),
            ).fetchall()
            observation_rows = [serialize_db_row(dict(row)) for row in device_rows]
            group["devices"] = [
                row["device_id"] for row in observation_rows if row["device_id"]
            ]
            group["observations"] = observation_rows
        return [target_estimate_payload(group) for group in groups]


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


@app.get("/time-sync")
def time_sync():
    now = datetime.now(timezone.utc)
    return {
        "server_time_ms": int(now.timestamp() * 1000),
        "server_time_iso": now.isoformat(),
    }


@app.post("/events")
async def create_event(
    event: SoundEvent,
    upload_token: Optional[str] = Header(default=None, alias="x-upload-token"),
):
    verify_upload_token(upload_token)
    sanitize_timing_metadata(event)
    created_at = current_time_iso()
    db_id = save_event(event, created_at)
    device_row = None
    event_group = None

    try:
        event_group = process_event_fusion_for_event(event.event_id)
    except Exception:
        logger.exception("Event fusion failed for event_id=%s", event.event_id)

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

    if event_group:
        await dashboard_manager.broadcast(
            {
                "type": "event_group",
                "group": event_group,
            }
        )

    target_estimate = None
    if is_alert_event_label(event.label):
        target_estimate = create_target_estimate_for_event(event, created_at)

    if target_estimate:
        await dashboard_manager.broadcast(
            {
                "type": "target_estimate",
                **target_estimate,
            }
        )

    return {
        "status": "success",
        "message": "Event received",
        "event_id": event.event_id,
        "db_id": db_id,
    }


@app.get("/target-estimates")
def target_estimates(limit: int = Query(default=10, ge=1, le=100)):
    return list_target_estimates(limit=limit)


@app.get("/event-groups")
def event_groups(
    limit: int = Query(default=20, ge=1, le=100),
    status: Optional[str] = Query(default=None),
    label: Optional[str] = Query(default=None),
):
    groups = list_event_fusion_groups(
        limit=limit,
        status_filter=status,
        label_filter=label,
    )
    return {
        "status": "success",
        "count": len(groups),
        "event_groups": groups,
    }


@app.get("/event-groups/{group_id}")
def event_group_detail(group_id: str):
    group = get_event_fusion_group(group_id)
    if not group:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event group not found",
        )
    return {
        "status": "success",
        "group": group,
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


@app.get("/events/{event_id}/audio-url")
def event_audio_url(event_id: str):
    event = get_event_by_event_id(event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    audio_path = event.get("audio_path")
    if not audio_path:
        raise HTTPException(status_code=404, detail="Audio file is not uploaded")

    try:
        bucket = get_gcs_bucket()
        blob = bucket.blob(audio_path)
        signed_url = blob.generate_signed_url(
            version="v4",
            expiration=timedelta(minutes=10),
            method="GET",
            response_type="audio/wav",
            response_disposition=f'inline; filename="{event_id}.wav"',
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create audio playback URL",
        ) from exc

    return {
        "status": "success",
        "event_id": event_id,
        "audio_path": audio_path,
        "expires_in_seconds": 600,
        "url": signed_url,
    }


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
        <title>聲音偵測戰情室 V2.1</title>
        <style>
            :root {
                --bg: #0f1115;
                --panel: #171a20;
                --panel-2: #20242b;
                --panel-3: #111419;
                --line: #303743;
                --text: #f4f7fb;
                --muted: #aab3bd;
                --good: #2ec27e;
                --warn: #f6c85f;
                --bad: #ff6b6b;
                --accent: #4aa3ff;
                --accent-2: #60d394;
            }
            * { box-sizing: border-box; }
            body {
                margin: 0;
                font-family: Arial, "Noto Sans TC", sans-serif;
                background: linear-gradient(180deg, #11151b 0%, var(--bg) 42%, #0c0e12 100%);
                color: var(--text);
                min-height: 100vh;
            }
            header {
                padding: 16px 20px;
                border-bottom: 1px solid var(--line);
                background: rgba(13, 16, 21, .96);
                display: flex;
                justify-content: space-between;
                gap: 12px;
                align-items: center;
            }
            h1 { margin: 0; font-size: 22px; letter-spacing: .02em; }
            .subtitle { color: var(--muted); font-size: 13px; margin-top: 3px; }
            .header-actions {
                display: flex;
                align-items: center;
                gap: 8px;
                flex-wrap: wrap;
                justify-content: flex-end;
            }
            .topbar {
                display: grid;
                grid-template-columns: repeat(4, minmax(120px, 1fr));
                gap: 12px;
                padding: 12px 16px;
            }
            .stat, .panel, .node-card, .event-row {
                background: var(--panel);
                border: 1px solid var(--line);
                border-radius: 12px;
            }
            .stat {
                padding: 13px 14px;
                min-height: 80px;
                background: linear-gradient(180deg, #1a1e25, #151920);
            }
            .stat .label { color: var(--muted); font-size: 12px; }
            .stat .value { font-size: 24px; font-weight: 900; margin-top: 6px; }
            .layout {
                display: grid;
                grid-template-columns: minmax(300px, 360px) minmax(520px, 1fr) minmax(320px, 390px);
                grid-template-rows: minmax(560px, calc(100vh - 280px)) minmax(260px, 31vh);
                gap: 12px;
                padding: 0 16px 16px;
            }
            .panel { min-height: 0; overflow: hidden; display: flex; flex-direction: column; }
            .side-stack {
                min-height: 0;
                display: flex;
                flex-direction: column;
                gap: 12px;
                overflow-y: auto;
                padding-right: 4px;
            }
            .side-stack .panel {
                flex: 0 0 auto;
                min-height: 170px;
            }
            .side-stack .audio-panel { min-height: 156px; }
            .side-stack .alert-panel { min-height: 190px; }
            .side-stack .event-groups-panel { min-height: 330px; }
            .side-stack .target-panel { min-height: 230px; }
            .panel h2 {
                font-size: 15px;
                margin: 0;
                padding: 12px 14px;
                border-bottom: 1px solid var(--line);
                background: var(--panel-3);
                letter-spacing: .03em;
            }
            .panel-body { padding: 10px; overflow: auto; }
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
                background: rgba(13,17,22,.90);
                border: 1px solid var(--line);
                padding: 8px 10px;
                border-radius: 8px;
                font-size: 12px;
                color: var(--muted);
                max-width: calc(100% - 24px);
            }
            .node-card {
                padding: 12px;
                margin-bottom: 10px;
                background: linear-gradient(180deg, #1a1e25, #151920);
            }
            .node-card.online { border-color: rgba(69,196,134,.45); }
            .node-card.offline { opacity: .8; }
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
                grid-template-columns: 78px minmax(0, 1fr);
                gap: 4px 8px;
                font-size: 12px;
                margin: 8px 0;
                color: var(--muted);
            }
            .kv strong {
                color: var(--text);
                font-weight: 650;
                min-width: 0;
                overflow-wrap: anywhere;
            }
            .node-meta {
                display: flex;
                flex-wrap: wrap;
                gap: 6px;
                margin: 7px 0 8px;
            }
            .mini-chip {
                border: 1px solid var(--line);
                border-radius: 999px;
                color: var(--muted);
                padding: 3px 7px;
                font-size: 11px;
                white-space: nowrap;
            }
            .mini-chip.good { color: var(--good); border-color: rgba(69,196,134,.45); }
            .mini-chip.warn { color: var(--warn); border-color: rgba(240,184,77,.55); }
            .actions {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 7px;
            }
            button, .link-button {
                border: 1px solid #415060;
                background: var(--panel-2);
                color: var(--text);
                border-radius: 8px;
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
            button.warn { background: #4b3415; border-color: #b7791f; color: #ffd68a; }
            button.active { border-color: var(--good); color: var(--good); }
            .event-row {
                padding: 10px 11px;
                margin-bottom: 8px;
                font-size: 12px;
                background: #151920;
                cursor: pointer;
            }
            .event-row:hover { border-color: var(--accent); }
            .event-row.selected {
                background: rgba(54,162,235,.12);
                border-color: rgba(54,162,235,.75);
            }
            .event-row.target { border-color: rgba(240,184,77,.65); }
            .event-row.target.selected {
                background: rgba(240,184,77,.12);
                border-color: rgba(240,184,77,.95);
            }
            .event-title { display: flex; justify-content: space-between; gap: 8px; font-weight: 800; }
            .event-title span {
                min-width: 0;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            .event-grid {
                display: grid;
                grid-template-columns: 1fr auto;
                gap: 8px;
                align-items: center;
            }
            .event-detail {
                color: var(--muted);
                line-height: 1.35;
                overflow-wrap: anywhere;
            }
            .timing-box {
                margin-top: 8px;
                padding: 9px;
                border: 1px solid rgba(74,163,255,.34);
                border-radius: 8px;
                background: rgba(74,163,255,.08);
            }
            .timing-title {
                color: var(--accent);
                font-weight: 900;
                font-size: 12px;
                margin-bottom: 6px;
            }
            .timing-grid {
                display: grid;
                grid-template-columns: repeat(2, minmax(0, 1fr));
                gap: 5px 10px;
                font-size: 12px;
            }
            .timing-grid span {
                color: var(--muted);
                overflow-wrap: anywhere;
            }
            .timing-grid strong {
                color: var(--text);
                font-weight: 800;
                overflow-wrap: anywhere;
            }
            .preview-actions {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 8px;
                margin-top: 7px;
            }
            .preview-status {
                color: var(--accent-2);
                font-weight: 800;
            }
            .preview-close {
                min-height: 28px;
                padding: 4px 9px;
                font-size: 12px;
            }
            .map-info-card {
                min-width: 220px;
                max-width: 300px;
                color: #111827;
                font-size: 13px;
                line-height: 1.45;
            }
            .map-info-card strong {
                display: block;
                margin-bottom: 6px;
                color: #0f172a;
                font-size: 15px;
            }
            .map-info-row {
                display: grid;
                grid-template-columns: 86px 1fr;
                gap: 8px;
                padding: 3px 0;
                border-top: 1px solid #e5e7eb;
            }
            .map-info-row span:first-child {
                color: #64748b;
                font-weight: 700;
            }
            .map-info-row span:last-child {
                color: #111827;
                overflow-wrap: anywhere;
            }
            .timeline { grid-column: 1 / span 3; }
            .filters { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 10px; }
            .filters button.active { color: var(--accent-2); border-color: rgba(96,211,148,.65); }
            .audio-player {
                margin: 10px;
                padding: 10px;
                background: var(--panel-3);
                border: 1px solid var(--line);
                border-radius: 8px;
                flex: 0 0 auto;
            }
            .audio-player .title {
                color: var(--muted);
                font-size: 12px;
                margin-bottom: 8px;
            }
            .audio-player audio {
                width: 100%;
                height: 40px;
            }
            .right-scroll {
                flex: 1 1 0;
                min-height: 0;
                overflow: auto;
            }
            .map-marker {
                position: absolute;
                transform: translate(-50%, -50%);
                pointer-events: auto;
                z-index: 4;
            }
            .map-marker.target-estimate-anchor {
                transform: translate(22px, -112px);
                z-index: 8;
            }
            .map-marker.target-estimate-anchor::before {
                content: "";
                position: absolute;
                left: -28px;
                top: 105px;
                width: 12px;
                height: 12px;
                border-radius: 999px;
                border: 3px solid #fed7aa;
                background: #f97316;
                box-shadow: 0 0 0 5px rgba(249,115,22,.24), 0 4px 12px rgba(0,0,0,.35);
                pointer-events: none;
            }
            .map-marker.target-estimate-anchor::after {
                content: "";
                position: absolute;
                left: -18px;
                top: 86px;
                width: 34px;
                height: 2px;
                background: rgba(249,115,22,.8);
                transform: rotate(-38deg);
                transform-origin: left center;
                pointer-events: none;
            }
            .node-marker {
                position: relative;
                display: inline-flex;
                align-items: center;
                gap: 7px;
                min-width: 76px;
                min-height: 38px;
                padding: 6px 10px;
                color: #101820;
                background: #fff;
                border: 3px solid #101820;
                border-radius: 12px;
                font-size: 15px;
                font-weight: 900;
                line-height: 1;
                white-space: nowrap;
                box-shadow: 0 6px 18px rgba(0,0,0,.35);
                cursor: pointer;
                user-select: none;
            }
            .node-marker .shape {
                width: 18px;
                height: 18px;
                background: #101820;
                border: 2px solid #101820;
                flex: 0 0 auto;
            }
            .node-marker.circle .shape { border-radius: 999px; }
            .node-marker.square .shape { border-radius: 2px; }
            .node-marker.triangle .shape {
                width: 0;
                height: 0;
                background: transparent;
                border-left: 10px solid transparent;
                border-right: 10px solid transparent;
                border-bottom: 18px solid #101820;
            }
            .node-marker.diamond .shape {
                width: 16px;
                height: 16px;
                transform: rotate(45deg);
            }
            .node-marker.hexagon .shape {
                clip-path: polygon(25% 0%, 75% 0%, 100% 50%, 75% 100%, 25% 100%, 0% 50%);
            }
            .node-marker.alert {
                border-color: #f59e0b;
                background: #fff7e6;
                animation: alert-bounce 780ms ease-in-out infinite;
            }
            .node-marker.alert .shape { background: #d97706; border-color: #d97706; }
            .node-marker.alert.triangle .shape {
                background: transparent;
                border-bottom-color: #d97706;
            }
            .node-marker.alert::before,
            .node-marker.alert::after {
                content: "";
                position: absolute;
                inset: -12px;
                border: 3px solid rgba(245, 158, 11, .72);
                border-radius: 16px;
                animation: alert-ripple 1.25s ease-out infinite;
                pointer-events: none;
            }
            .node-marker.alert::after {
                animation-delay: .45s;
            }
            .target-estimate-marker {
                position: relative;
                display: block;
                width: 118px;
                height: 74px;
                border: 2px solid rgba(249,115,22,.95);
                border-radius: 6px;
                background: rgba(15,23,42,.14);
                color: #fff7ed;
                box-shadow: 0 8px 22px rgba(0,0,0,.35);
                cursor: pointer;
                user-select: none;
            }
            .target-estimate-marker.active {
                animation: target-box-pulse 1.1s ease-in-out infinite;
            }
            .target-estimate-marker .target-corner {
                position: absolute;
                width: 24px;
                height: 24px;
                border-color: #fed7aa;
                pointer-events: none;
            }
            .target-estimate-marker .tl {
                top: -4px;
                left: -4px;
                border-left: 5px solid;
                border-top: 5px solid;
            }
            .target-estimate-marker .tr {
                top: -4px;
                right: -4px;
                border-right: 5px solid;
                border-top: 5px solid;
            }
            .target-estimate-marker .bl {
                bottom: -4px;
                left: -4px;
                border-left: 5px solid;
                border-bottom: 5px solid;
            }
            .target-estimate-marker .br {
                bottom: -4px;
                right: -4px;
                border-right: 5px solid;
                border-bottom: 5px solid;
            }
            .target-estimate-marker .target-cross {
                position: absolute;
                left: 50%;
                top: 50%;
                width: 28px;
                height: 28px;
                transform: translate(-50%, -50%);
                border: 2px solid rgba(254,215,170,.92);
                border-radius: 999px;
                pointer-events: none;
            }
            .target-estimate-marker .target-cross::before,
            .target-estimate-marker .target-cross::after {
                content: "";
                position: absolute;
                background: rgba(254,215,170,.92);
            }
            .target-estimate-marker .target-cross::before {
                left: 50%;
                top: -9px;
                width: 2px;
                height: 44px;
                transform: translateX(-50%);
            }
            .target-estimate-marker .target-cross::after {
                left: -9px;
                top: 50%;
                width: 44px;
                height: 2px;
                transform: translateY(-50%);
            }
            .target-estimate-marker .target-tag,
            .target-estimate-marker .target-meta {
                position: absolute;
                left: 8px;
                max-width: calc(100% - 16px);
                padding: 3px 7px;
                border-radius: 4px;
                background: rgba(124,45,18,.92);
                color: #fffbeb;
                font-size: 12px;
                font-weight: 900;
                line-height: 1.1;
                white-space: nowrap;
                box-shadow: 0 4px 14px rgba(0,0,0,.28);
            }
            .target-estimate-marker .target-tag {
                top: -30px;
                letter-spacing: .08em;
            }
            .target-estimate-marker .target-meta {
                bottom: -28px;
                background: rgba(15,23,42,.9);
                color: #fed7aa;
            }
            .target-estimate-marker::after {
                content: "";
                position: absolute;
                inset: -18px;
                border-radius: 12px;
                border: 3px solid rgba(249,115,22,.48);
                opacity: 0;
                pointer-events: none;
            }
            .target-estimate-marker.active::after {
                opacity: 1;
                animation: alert-ripple 1.4s ease-out infinite;
            }
            @keyframes alert-bounce {
                0%, 100% { transform: scale(1); }
                50% { transform: scale(1.08); }
            }
            @keyframes target-box-pulse {
                0%, 100% {
                    transform: scale(1);
                    box-shadow: 0 8px 22px rgba(0,0,0,.35), 0 0 0 rgba(249,115,22,0);
                }
                50% {
                    transform: scale(1.04);
                    box-shadow: 0 10px 28px rgba(0,0,0,.45), 0 0 20px rgba(249,115,22,.45);
                }
            }
            @keyframes alert-ripple {
                0% { opacity: .9; transform: scale(.86); }
                100% { opacity: 0; transform: scale(1.45); }
            }
            @media (max-width: 980px) {
                header { align-items: flex-start; flex-direction: column; }
                .header-actions { justify-content: flex-start; }
                .topbar { grid-template-columns: repeat(3, 1fr); padding: 10px; }
                .layout {
                    grid-template-columns: 1fr;
                    grid-template-rows: auto;
                    padding: 0 10px 14px;
                }
                .map-panel { order: 2; }
                .side-stack {
                    order: 3;
                    max-height: none;
                    overflow: visible;
                }
                #map { min-height: 300px; }
                .timeline { grid-column: auto; order: 4; }
            }
            @media (max-width: 560px) {
                header { padding: 14px; }
                h1 { font-size: 20px; }
                .topbar { grid-template-columns: 1fr 1fr; }
                .stat .value { font-size: 18px; }
                .kv { grid-template-columns: 92px 1fr; }
                .actions button { flex: 1 1 45%; }
                .event-grid { grid-template-columns: 1fr; }
            }
        </style>
    </head>
    <body>
        <header>
            <div>
                <h1>聲音偵測戰情室 V2.1</h1>
                <div class="subtitle">多節點聲音偵測、即時定位、遠端控制與事件追蹤</div>
            </div>
            <div class="header-actions">
                <a class="link-button" href="/events/export.csv">匯出事件 CSV</a>
            </div>
        </header>

        <section class="topbar">
            <div class="stat"><div class="label">在線節點</div><div class="value" id="onlineCount">0</div></div>
            <div class="stat"><div class="label">目前警示</div><div class="value" id="activeAlertCount">0</div></div>
            <div class="stat"><div class="label">今日目標聲</div><div class="value" id="todayDroneCount">0</div></div>
            <div class="stat"><div class="label">系統狀態</div><div class="value" id="systemStatus">載入中</div></div>
        </section>

        <main class="layout">
            <section class="panel">
                <h2>節點控制</h2>
                <div class="panel-body" id="nodeList"></div>
            </section>

            <section class="panel map-panel">
                <h2>即時地圖</h2>
                <div id="map"></div>
                <div class="map-note">只有 aircraft / drone 事件會觸發警示動畫；GPS 更新只用來維持節點位置。</div>
            </section>

            <aside class="side-stack">
                <section class="panel audio-panel">
                    <h2>音檔播放</h2>
                    <div class="audio-player" id="audioPlayerBox">
                        <div class="title" id="audioPlayerTitle">請選擇事件查看音檔</div>
                        <audio id="eventAudioPlayer" controls></audio>
                    </div>
                </section>

                <section class="panel alert-panel">
                    <h2>即時警示</h2>
                    <div class="panel-body right-scroll" id="alertList"></div>
                </section>

                <section class="panel event-groups-panel">
                    <h2>事件群組</h2>
                    <div class="panel-body right-scroll" id="eventGroupList">
                        <div class="subtitle">目前沒有事件群組</div>
                    </div>
                </section>

                <section class="panel target-panel">
                    <h2>聲源估測</h2>
                    <div class="panel-body right-scroll" id="targetEstimateList">
                        <div class="subtitle">目前沒有多節點融合估測</div>
                    </div>
                </section>
            </aside>

            <section class="panel timeline">
                <h2>事件時間軸</h2>
                <div class="panel-body">
                    <div class="filters">
                        <button data-filter="all" class="active" onclick="setFilter('all')">全部</button>
                        <button data-filter="drone" onclick="setFilter('drone')">只看目標聲</button>
                        <button data-filter="other" onclick="setFilter('other')">只看其他聲音</button>
                    </div>
                    <div id="timelineList"></div>
                </div>
            </section>
        </main>

        <script>
            let map;
            let infoWindow;
            let NodeOverlayMarker;
            let TargetEstimateOverlayMarker;
            const devices = new Map();
            const events = [];
            const markers = new Map();
            const targetEstimates = new Map();
            const eventGroups = new Map();
            const targetEstimateMarkers = new Map();
            const targetEstimateCircles = new Map();
            const alertUntil = new Map();
            const alertDurationMs = 15000;
            const targetEstimateAutoDisplayMs = 5000;
            const dismissedTargetEstimateIds = new Set();
            let selectedTargetEstimateId = null;
            let selectedEventGroupId = null;
            let currentFilter = 'all';

            function safe(value, fallback = '-') {
                return value === null || value === undefined || value === '' ? fallback : value;
            }

            function attrSafe(value) {
                return String(value ?? '')
                    .replaceAll('&', '&amp;')
                    .replaceAll('"', '&quot;')
                    .replaceAll('<', '&lt;')
                    .replaceAll('>', '&gt;');
            }

            function isDiagnosticDevice(deviceId) {
                return /COMMAND_TEST|ACK_FAILED_TEST|HEARTBEAT_CHECK|DEPLOY_CHECK|DEBUG_CHECK/i.test(String(deviceId || ''));
            }

            function visibleDeviceValues() {
                return Array.from(devices.values())
                    .filter(device => device && device.device_id && !isDiagnosticDevice(device.device_id))
                    .sort((a, b) => String(a.device_id).localeCompare(String(b.device_id)));
            }

            function isOnlineDevice(device) {
                return device.status === 'online' || device.status === 'event';
            }

            function displayStatus(status) {
                const value = String(status || '').toLowerCase();
                if (value === 'online') return '在線';
                if (value === 'event') return '警示中';
                if (value === 'offline') return '離線';
                return safe(status);
            }

            function displayMode(mode) {
                const value = String(mode || '').toLowerCase();
                if (value === 'detection') return '偵測模式';
                if (value === 'collection') return '蒐集模式';
                return safe(mode);
            }

            function displayEventLabel(label) {
                const value = String(label || '').toLowerCase();
                if (value === 'aircraft' || value === 'drone') return '目標聲';
                if (value === 'non_aircraft' || value === 'other') return '非目標聲';
                if (value === 'sound_event') return '聲音事件';
                return safe(label);
            }

            function displayGroupStatus(status) {
                const value = String(status || '').toUpperCase();
                if (value === 'ACTIVE') return '進行中';
                if (value === 'CLOSED') return '已結束';
                return safe(status);
            }

            function displayEstimateMethod(method) {
                const value = String(method || '').toLowerCase();
                if (value === 'tdoa_timestamp') return '粗略 TDOA';
                if (value === 'weighted_centroid_fallback') return 'TDOA 失敗，使用融合估計';
                if (value === 'weighted_centroid') return '多節點融合';
                return safe(method);
            }

            function displayResidual(value) {
                const number = Number(value);
                return Number.isFinite(number) ? `${number.toFixed(1)} m` : '--';
            }

            function displayTimeSyncQuality(value) {
                const text = String(value || '').toLowerCase();
                if (!text) return '--';
                if (text === 'good') return 'good';
                if (text === 'medium') return 'medium';
                if (text === 'poor') return 'poor';
                if (text.includes('insufficient')) return 'insufficient';
                if (text === 'missing') return 'missing';
                return safe(value);
            }

            function yesNo(value) {
                return value ? '是' : '否';
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

            function markerShapeClass(deviceId) {
                if (deviceId === 'node_A01') return 'circle';
                if (deviceId === 'node_A02') return 'square';
                if (deviceId === 'node_A03') return 'triangle';
                if (deviceId === 'node_A04') return 'diamond';
                return 'hexagon';
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
                ensureNodeOverlayMarkerClass();
                refreshAll();
            };

            function isAlertActive(deviceId) {
                const until = alertUntil.get(deviceId);
                return Boolean(until && Date.now() < until);
            }

            function parseDashboardTime(value) {
                if (!value) return NaN;
                const parsed = Date.parse(value);
                return Number.isFinite(parsed) ? parsed : NaN;
            }

            function isTargetEstimateActive(estimate) {
                const timeMs = parseDashboardTime(estimate?.updated_at || estimate?.created_at);
                return Number.isFinite(timeMs) && Date.now() - timeMs <= targetEstimateAutoDisplayMs;
            }

            function ensureNodeOverlayMarkerClass() {
                if (NodeOverlayMarker || !window.google) return;

                NodeOverlayMarker = class extends google.maps.OverlayView {
                    constructor(device) {
                        super();
                        this.device = device;
                        this.position = new google.maps.LatLng(Number(device.latitude), Number(device.longitude));
                        this.div = null;
                        this.setMap(map);
                    }

                    onAdd() {
                        this.div = document.createElement('div');
                        this.div.className = 'map-marker';
                        this.div.addEventListener('click', () => showDeviceInfo(this.device));
                        this.getPanes().overlayMouseTarget.appendChild(this.div);
                        this.render();
                    }

                    draw() {
                        if (!this.div) return;
                        const projection = this.getProjection();
                        if (!projection) return;
                        const point = projection.fromLatLngToDivPixel(this.position);
                        this.div.style.left = `${point.x}px`;
                        this.div.style.top = `${point.y}px`;
                    }

                    onRemove() {
                        if (this.div?.parentNode) {
                            this.div.parentNode.removeChild(this.div);
                        }
                        this.div = null;
                    }

                    update(device) {
                        this.device = { ...this.device, ...device };
                        this.position = new google.maps.LatLng(Number(this.device.latitude), Number(this.device.longitude));
                        this.render();
                        this.draw();
                    }

                    render() {
                        if (!this.div) return;
                        const shapeClass = markerShapeClass(this.device.device_id);
                        const active = isAlertActive(this.device.device_id);
                        const label = shortDeviceLabel(this.device.device_id);
                        this.div.innerHTML = `
                            <div class="node-marker ${shapeClass} ${active ? 'alert' : ''}" title="${safe(this.device.device_id)}">
                                <span class="shape" aria-hidden="true"></span>
                                <span>${label}</span>
                            </div>
                        `;
                    }
                };
            }

            function ensureTargetEstimateOverlayMarkerClass() {
                if (TargetEstimateOverlayMarker || !window.google) return;

                TargetEstimateOverlayMarker = class extends google.maps.OverlayView {
                    constructor(estimate) {
                        super();
                        this.estimate = estimate;
                        this.position = new google.maps.LatLng(
                            Number(estimate.estimated_lat),
                            Number(estimate.estimated_lng),
                        );
                        this.div = null;
                        this.setMap(map);
                    }

                    onAdd() {
                        this.div = document.createElement('div');
                        this.div.className = 'map-marker target-estimate-anchor';
                        this.div.addEventListener('click', () => showTargetEstimateInfo(this.estimate));
                        this.getPanes().overlayMouseTarget.appendChild(this.div);
                        this.render();
                    }

                    draw() {
                        if (!this.div) return;
                        const projection = this.getProjection();
                        if (!projection) return;
                        const point = projection.fromLatLngToDivPixel(this.position);
                        this.div.style.left = `${point.x}px`;
                        this.div.style.top = `${point.y}px`;
                    }

                    onRemove() {
                        if (this.div?.parentNode) {
                            this.div.parentNode.removeChild(this.div);
                        }
                        this.div = null;
                    }

                    update(estimate) {
                        this.estimate = { ...this.estimate, ...estimate };
                        this.position = new google.maps.LatLng(
                            Number(this.estimate.estimated_lat),
                            Number(this.estimate.estimated_lng),
                        );
                        this.render();
                        this.draw();
                    }

                    render() {
                        if (!this.div) return;
                        const confidence = Number(this.estimate.confidence || 0);
                        const confidenceText = Number.isFinite(confidence)
                            ? `${Math.round(confidence * 100)}%`
                            : '--';
                        const radius = Number(this.estimate.uncertainty_radius_m);
                        const radiusText = Number.isFinite(radius)
                            ? `${Math.round(radius)}m`
                            : '--';
                        const active = isTargetEstimateActive(this.estimate);
                        this.div.innerHTML = `
                            <div class="target-estimate-marker ${active ? 'active' : ''}" title="聲源估測">
                                <span class="target-corner tl"></span>
                                <span class="target-corner tr"></span>
                                <span class="target-corner bl"></span>
                                <span class="target-corner br"></span>
                                <span class="target-cross"></span>
                                <span class="target-tag">TARGET ${confidenceText}</span>
                                <span class="target-meta">radius ${radiusText}</span>
                            </div>
                        `;
                    }
                };
            }

            function showDeviceInfo(device) {
                const lat = Number(device.latitude);
                const lng = Number(device.longitude);
                if (!Number.isFinite(lat) || !Number.isFinite(lng)) return;

                infoWindow.setContent(`
                    <div class="map-info-card">
                        <strong>${safe(device.device_id)}</strong>
                        <div class="map-info-row"><span>緯度</span><span>${safe(device.latitude)}</span></div>
                        <div class="map-info-row"><span>經度</span><span>${safe(device.longitude)}</span></div>
                        <div class="map-info-row"><span>最後連線</span><span>${safe(device.last_seen)}</span></div>
                        <div class="map-info-row"><span>最後事件</span><span>${safe(device.last_event_id)}</span></div>
                        <div class="map-info-row"><span>事件時間</span><span>${safe(device.last_event_at)}</span></div>
                        <div class="map-info-row"><span>狀態</span><span>${displayStatus(device.status)}</span></div>
                        <div class="map-info-row"><span>模式</span><span>${displayMode(device.upload_mode)}</span></div>
                        <div class="map-info-row"><span>監聽中</span><span>${yesNo(device.is_listening)}</span></div>
                    </div>
                `);
                infoWindow.setPosition({ lat, lng });
                infoWindow.open(map);
            }

            function updateMapMarker(device) {
                if (!map || !window.google) return;
                const lat = Number(device.latitude);
                const lng = Number(device.longitude);
                if (!Number.isFinite(lat) || !Number.isFinite(lng)) return;
                ensureNodeOverlayMarkerClass();
                if (!NodeOverlayMarker) return;

                let marker = markers.get(device.device_id);
                if (!marker) {
                    marker = new NodeOverlayMarker(device);
                    markers.set(device.device_id, marker);
                } else {
                    marker.update(device);
                }
            }

            function cleanupHiddenMarkers() {
                const visibleIds = new Set(visibleDeviceValues().map(device => device.device_id));
                markers.forEach((marker, deviceId) => {
                    if (!visibleIds.has(deviceId)) {
                        marker.setMap(null);
                        markers.delete(deviceId);
                    }
                });
            }

            function cleanupTargetEstimateMarkers(activeGroupIds = new Set()) {
                targetEstimateMarkers.forEach((marker, groupId) => {
                    if (!activeGroupIds.has(groupId)) {
                        marker.setMap(null);
                        targetEstimateMarkers.delete(groupId);
                    }
                });
                targetEstimateCircles.forEach((circle, groupId) => {
                    if (!activeGroupIds.has(groupId)) {
                        circle.setMap(null);
                        targetEstimateCircles.delete(groupId);
                    }
                });
            }

            function targetEstimateValues() {
                return Array.from(targetEstimates.values())
                    .filter(estimate => Number.isFinite(Number(estimate.estimated_lat)) && Number.isFinite(Number(estimate.estimated_lng)))
                    .sort((a, b) => String(b.updated_at || '').localeCompare(String(a.updated_at || '')));
            }

            function targetEstimateId(estimate) {
                return estimate?.group_id || estimate?.id || '';
            }

            function showTargetEstimateInfo(estimate) {
                const lat = Number(estimate.estimated_lat);
                const lng = Number(estimate.estimated_lng);
                if (!Number.isFinite(lat) || !Number.isFinite(lng)) return;

                infoWindow.setContent(`
                    <div class="map-info-card">
                        <strong>聲源估測</strong>
                        <div class="map-info-row"><span>類別</span><span>${safe(estimate.label)}</span></div>
                        <div class="map-info-row"><span>信心值</span><span>${Number(estimate.confidence || 0).toFixed(2)}</span></div>
                        <div class="map-info-row"><span>位置</span><span>${lat.toFixed(6)}, ${lng.toFixed(6)}</span></div>
                        <div class="map-info-row"><span>估測範圍</span><span>${safe(estimate.uncertainty_radius_m)} m</span></div>
                        <div class="map-info-row"><span>節點數</span><span>${safe(estimate.node_count)}</span></div>
                        <div class="map-info-row"><span>參與節點</span><span>${(estimate.devices || []).join(', ') || '-'}</span></div>
                        <div class="map-info-row"><span>定位方法</span><span>${displayEstimateMethod(estimate.method)}</span></div>
                        <div class="map-info-row"><span>同步品質</span><span>${displayTimeSyncQuality(estimate.time_sync_quality)}</span></div>
                        <div class="map-info-row"><span>TDOA residual</span><span>${displayResidual(estimate.tdoa_residual_rmse_m)}</span></div>
                        <div class="map-info-row"><span>更新時間</span><span>${safe(estimate.updated_at)}</span></div>
                    </div>
                `);
                infoWindow.setPosition({ lat, lng });
                infoWindow.open(map);
            }

            function previewTargetEstimate(groupId) {
                if (selectedTargetEstimateId === groupId) {
                    clearTargetEstimatePreview();
                    return;
                }
                const estimate = targetEstimates.get(groupId);
                if (!estimate) return;
                const lat = Number(estimate.estimated_lat);
                const lng = Number(estimate.estimated_lng);
                if (!Number.isFinite(lat) || !Number.isFinite(lng)) return;

                selectedTargetEstimateId = groupId;
                dismissedTargetEstimateIds.delete(groupId);
                cleanupTargetEstimateMarkers(new Set([groupId]));
                updateTargetEstimateOnMap(estimate);
                showTargetEstimateInfo(estimate);
                map.panTo({ lat, lng });
                if ((map.getZoom() || 12) < 16) {
                    map.setZoom(16);
                }
                renderTargetEstimates();
            }

            function clearTargetEstimatePreview() {
                if (selectedTargetEstimateId) {
                    dismissedTargetEstimateIds.add(selectedTargetEstimateId);
                }
                selectedTargetEstimateId = null;
                cleanupTargetEstimateMarkers(new Set());
                if (infoWindow) {
                    infoWindow.close();
                }
                renderTargetEstimates();
            }

            function updateTargetEstimateOnMap(estimate) {
                if (!map || !window.google) return;
                const lat = Number(estimate.estimated_lat);
                const lng = Number(estimate.estimated_lng);
                if (!Number.isFinite(lat) || !Number.isFinite(lng)) return;
                const groupId = targetEstimateId(estimate);
                if (!groupId) return;

                ensureTargetEstimateOverlayMarkerClass();
                if (!TargetEstimateOverlayMarker) return;

                let marker = targetEstimateMarkers.get(groupId);
                if (!marker) {
                    marker = new TargetEstimateOverlayMarker(estimate);
                    targetEstimateMarkers.set(groupId, marker);
                } else {
                    marker.update(estimate);
                }

                let circle = targetEstimateCircles.get(groupId);
                const radius = Number(estimate.uncertainty_radius_m || 80);
                if (!circle) {
                    circle = new google.maps.Circle({
                        map,
                        center: { lat, lng },
                        radius,
                        strokeColor: '#f97316',
                        strokeOpacity: 0.72,
                        strokeWeight: 2,
                        fillColor: '#f97316',
                        fillOpacity: 0.16,
                    });
                    targetEstimateCircles.set(groupId, circle);
                } else {
                    circle.setCenter({ lat, lng });
                    circle.setRadius(radius);
                }
            }

            function renderTargetEstimates() {
                const list = document.getElementById('targetEstimateList');
                if (!list) return;
                const estimates = targetEstimateValues().slice(0, 8);
                if (!estimates.length) {
                    list.innerHTML = '<div class="subtitle">目前沒有多節點融合估測</div>';
                    return;
                }
                list.innerHTML = estimates.map(estimate => `
                    <div class="event-row target ${targetEstimateId(estimate) === selectedTargetEstimateId ? 'selected' : ''}" data-estimate-id="${attrSafe(targetEstimateId(estimate))}">
                        <div class="event-title"><span>聲源估測</span><span>${safe(estimate.label)}</span></div>
                        <div class="event-detail">節點 ${safe(estimate.node_count)} / 信心 ${Number(estimate.confidence || 0).toFixed(2)}</div>
                        <div class="event-detail">方法 ${displayEstimateMethod(estimate.method)} / 同步 ${displayTimeSyncQuality(estimate.time_sync_quality)}</div>
                        <div class="event-detail">TDOA residual ${displayResidual(estimate.tdoa_residual_rmse_m)}</div>
                        <div class="event-detail">位置 ${Number(estimate.estimated_lat).toFixed(6)}, ${Number(estimate.estimated_lng).toFixed(6)}</div>
                        <div class="event-detail">範圍 ${safe(estimate.uncertainty_radius_m)} m / ${(estimate.devices || []).join(', ')}</div>
                        ${targetEstimateId(estimate) === selectedTargetEstimateId
                            ? '<div class="preview-actions"><span class="preview-status">已在地圖預覽</span><button class="preview-close" type="button" data-close-preview="1">關閉預覽</button></div>'
                            : '<div class="event-detail">點選可在地圖預覽位置</div>'}
                    </div>
                `).join('');
                list.querySelectorAll('[data-estimate-id]').forEach(row => {
                    row.addEventListener('click', () => previewTargetEstimate(row.dataset.estimateId));
                });
                list.querySelectorAll('[data-close-preview]').forEach(button => {
                    button.addEventListener('click', event => {
                        event.stopPropagation();
                        clearTargetEstimatePreview();
                    });
                });
            }

            function eventGroupId(group) {
                return group?.id || '';
            }

            function shortGroupId(group) {
                const value = String(eventGroupId(group));
                return value ? value.slice(0, 8) : '-';
            }

            function eventGroupValues() {
                return Array.from(eventGroups.values()).sort((a, b) => {
                    const aTime = parseDashboardTime(a.last_event_time || a.updated_at);
                    const bTime = parseDashboardTime(b.last_event_time || b.updated_at);
                    return (bTime || 0) - (aTime || 0);
                });
            }

            function gpsLabel(observation) {
                const lat = Number(observation?.latitude);
                const lng = Number(observation?.longitude);
                return Number.isFinite(lat) && Number.isFinite(lng) ? 'GPS 有' : 'GPS 無';
            }

            function timingValue(value) {
                return value === null || value === undefined || value === '' ? '--' : safe(value);
            }

            function observationTimingHtml(item) {
                return `
                    <div class="timing-box">
                        <div class="timing-title">Timing Metadata</div>
                        <div class="timing-grid">
                            <span>Timing Source</span><strong>${timingValue(item.timing_source)}</strong>
                            <span>Device Event Time</span><strong>${timingValue(item.device_event_time_ms)}</strong>
                            <span>Event Start Sample</span><strong>${timingValue(item.event_start_sample)}</strong>
                            <span>RMS Peak Sample</span><strong>${timingValue(item.rms_peak_sample)}</strong>
                            <span>Sample Rate</span><strong>${timingValue(item.sample_rate_hz)}</strong>
                            <span>Audio Duration</span><strong>${timingValue(item.audio_duration_ms)}</strong>
                        </div>
                    </div>
                `;
            }

            async function selectEventGroup(groupId) {
                if (selectedEventGroupId === groupId) {
                    selectedEventGroupId = null;
                    renderEventGroups();
                    return;
                }
                try {
                    const response = await fetch(`/event-groups/${encodeURIComponent(groupId)}`);
                    if (!response.ok) throw new Error(`HTTP ${response.status}`);
                    const data = await response.json();
                    const group = data.group;
                    if (group && eventGroupId(group)) {
                        eventGroups.set(eventGroupId(group), group);
                        selectedEventGroupId = eventGroupId(group);
                    }
                } catch (error) {
                    document.getElementById('systemStatus').textContent = '事件群組讀取失敗';
                }
                renderEventGroups();
            }

            function renderEventGroups() {
                const list = document.getElementById('eventGroupList');
                if (!list) return;
                const groups = eventGroupValues().slice(0, 8);
                if (!groups.length) {
                    list.innerHTML = '<div class="subtitle">目前沒有事件群組</div>';
                    return;
                }
                list.innerHTML = groups.map(group => {
                    const groupId = eventGroupId(group);
                    const selected = groupId === selectedEventGroupId;
                    const observations = selected ? (group.observations || []) : [];
                    const observationHtml = observations.length
                        ? observations.map(item => `
                            <div class="event-detail">節點 ${safe(item.device_id)} / ${safe(item.event_timestamp)} / RMS ${safe(item.rms_peak)} / AI ${safe(item.ai_probability)} / ${gpsLabel(item)}</div>
                            ${observationTimingHtml(item)}
                        `).join('')
                        : selected ? '<div class="event-detail">尚無 observation 明細</div>' : '';
                    return `
                        <div class="event-row ${selected ? 'selected' : ''}" data-event-group-id="${attrSafe(groupId)}">
                            <div class="event-title"><span>Group ${shortGroupId(group)}</span><span>${displayGroupStatus(group.status)}</span></div>
                            <div class="event-detail">類別 ${displayEventLabel(group.label)} / 節點 ${safe(group.node_count)}</div>
                            <div class="event-detail">最後時間 ${safe(group.last_event_time)}</div>
                            <div class="event-detail">${(group.devices || []).join(', ') || '-'}</div>
                            ${observationHtml}
                        </div>
                    `;
                }).join('');
                list.querySelectorAll('[data-event-group-id]').forEach(row => {
                    row.addEventListener('click', () => selectEventGroup(row.dataset.eventGroupId));
                });
            }

            function setFilter(filter) {
                currentFilter = filter;
                updateFilterButtons();
                renderTimeline();
            }

            function updateFilterButtons() {
                document.querySelectorAll('[data-filter]').forEach(button => {
                    button.classList.toggle('active', button.dataset.filter === currentFilter);
                });
            }

            function eventById(eventId) {
                return events.find(event => event.event_id === eventId);
            }

            async function selectEventAudio(eventId) {
                const title = document.getElementById('audioPlayerTitle');
                const player = document.getElementById('eventAudioPlayer');
                const event = eventById(eventId);

                if (!event) {
                    title.textContent = '找不到此事件';
                    player.removeAttribute('src');
                    player.load();
                    return;
                }

                if (!event.audio_path) {
                    title.textContent = `${event.event_id} 尚無音檔`;
                    player.removeAttribute('src');
                    player.load();
                    return;
                }

                try {
                    title.textContent = `音檔載入中：${event.event_id}`;
                    const response = await fetch(`/events/${encodeURIComponent(eventId)}/audio-url`);
                    const body = await response.json();
                    if (!response.ok) throw new Error(body.detail || response.statusText);
                    player.onerror = () => {
                        title.textContent = '音檔載入失敗：請確認 GCS Object Viewer 權限或檔案是否存在。';
                    };
                    player.src = body.url;
                    title.textContent = `${displayEventLabel(event.label)} / ${safe(event.device_id)} / ${safe(event.timestamp)}`;
                    await player.play();
                } catch (error) {
                    title.textContent = `音檔播放失敗：${error}`;
                    player.removeAttribute('src');
                    player.load();
                }
            }

            async function playAudio(eventId) {
                await selectEventAudio(eventId);
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
                    document.getElementById('systemStatus').textContent = `指令 #${body.command_id} 已送出`;
                } catch (error) {
                    document.getElementById('systemStatus').textContent = '指令送出失敗';
                    alert(`指令送出失敗：${error}`);
                }
            }

            function simulateAlert(deviceId) {
                const device = devices.get(deviceId);
                if (!device) return;

                const now = new Date();
                alertUntil.set(deviceId, Date.now() + alertDurationMs);
                devices.set(deviceId, {
                    ...device,
                    status: 'event',
                    last_event_id: `simulated_${Date.now()}`,
                    last_event_at: now.toISOString(),
                });

                events.unshift({
                    event_id: `simulated_${Date.now()}`,
                    device_id: deviceId,
                    timestamp: now.toLocaleString('zh-TW', { hour12: false }),
                    created_at: now.toISOString(),
                    latitude: device.latitude,
                    longitude: device.longitude,
                    label: 'drone',
                    audio_path: null,
                    note: 'probability_aircraft=1.000000, confidence=1.000000, upload_mode=simulation',
                });

                if (events.length > 80) {
                    events.length = 80;
                }

                document.getElementById('systemStatus').textContent = `模擬警示：${deviceId}`;
                renderAll();
            }

            function renderNodes() {
                const list = document.getElementById('nodeList');
                const values = visibleDeviceValues();
                if (!values.length) {
                    list.innerHTML = '<div class="subtitle">目前沒有節點狀態</div>';
                    return;
                }
                list.innerHTML = values.map(device => `
                    <div class="node-card ${isOnlineDevice(device) ? 'online' : 'offline'}">
                        <div class="node-title">
                            <span>${safe(device.device_id)}</span>
                            <span class="pill ${isOnlineDevice(device) ? 'online' : 'offline'}">${displayStatus(device.status)}</span>
                        </div>
                        <div class="node-meta">
                            <span class="mini-chip ${device.is_listening ? 'good' : ''}">監聽 ${yesNo(device.is_listening)}</span>
                            <span class="mini-chip ${device.upload_mode ? 'good' : 'warn'}">${displayMode(device.upload_mode)}</span>
                            <span class="mini-chip ${device.latitude && device.longitude ? 'good' : 'warn'}">GPS ${device.latitude && device.longitude ? '正常' : '等待中'}</span>
                        </div>
                        <div class="kv">
                            <span>電量</span><strong>${safe(device.battery)}</strong>
                            <span>AI</span><strong>${safe(device.ai_status)}</strong>
                            <span>最後連線</span><strong>${safe(device.last_seen)}</strong>
                            <span>最後事件</span><strong>${safe(device.last_event_at)}</strong>
                        </div>
                        <div class="actions">
                            <button class="primary" onclick="sendCommand('${device.device_id}', 'start_listening')">開始</button>
                            <button class="danger" onclick="sendCommand('${device.device_id}', 'stop_listening')">停止</button>
                            <button class="${device.upload_mode === 'detection' ? 'active' : ''}" onclick="sendCommand('${device.device_id}', 'set_detection_mode')">偵測模式</button>
                            <button class="${device.upload_mode === 'collection' ? 'active' : ''}" onclick="sendCommand('${device.device_id}', 'set_collection_mode')">蒐集模式</button>
                            <button class="warn" onclick="simulateAlert('${device.device_id}')">模擬警示</button>
                        </div>
                    </div>
                `).join('');
            }

            function renderAlerts() {
                const targetEvents = events.filter(event => isTarget(event.label)).slice(0, 12);
                const list = document.getElementById('alertList');
                list.innerHTML = targetEvents.length ? targetEvents.map(event => `
                    <div class="event-row target" onclick="selectEventAudio('${event.event_id}')">
                        <div class="event-grid">
                            <div>
                                <div class="event-title"><span>${displayEventLabel(event.label)}</span><span>${safe(event.device_id)}</span></div>
                                <div class="event-detail">${safe(event.timestamp)}</div>
                                <div class="event-detail">目標機率 ${noteValue(event.note, 'probability_aircraft')} / 信心值 ${noteValue(event.note, 'confidence')}</div>
                                <div class="event-detail">${safe(event.latitude)}, ${safe(event.longitude)}</div>
                            </div>
                            <div>${event.audio_path ? '<span class="mini-chip good">可播放</span>' : '<span class="mini-chip warn">待上傳</span>'}</div>
                        </div>
                    </div>
                `).join('') : '<div class="subtitle">目前沒有目標聲警示</div>';
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
                    <div class="event-row ${isTarget(event.label) ? 'target' : ''}" onclick="selectEventAudio('${event.event_id}')">
                        <div class="event-grid">
                            <div>
                                <div class="event-title"><span>${displayEventLabel(event.label)}</span><span>${safe(event.device_id)}</span></div>
                                <div class="event-detail">${safe(event.timestamp)}</div>
                                <div class="event-detail">信心值 ${noteValue(event.note, 'confidence')} / 模式 ${noteValue(event.note, 'upload_mode')}</div>
                            </div>
                            <div>${event.audio_path ? '<span class="mini-chip good">可播放</span>' : '<span class="mini-chip warn">無音檔</span>'}</div>
                        </div>
                    </div>
                `).join('') : '<div class="subtitle">目前沒有事件</div>';
            }

            function renderSummary() {
                const values = visibleDeviceValues();
                const online = values.filter(isOnlineDevice).length;
                const active = values.filter(device => isAlertActive(device.device_id)).length;
                const todayEvents = events.filter(event => isToday(event.created_at || event.timestamp));
                const drone = todayEvents.filter(event => isTarget(event.label));
                document.getElementById('onlineCount').textContent = online;
                document.getElementById('activeAlertCount').textContent = active;
                document.getElementById('todayDroneCount').textContent = drone.length;
                document.getElementById('systemStatus').textContent = values.length ? '即時運作' : '等待資料';
            }

            function renderAll() {
                cleanupHiddenMarkers();
                visibleDeviceValues().forEach(updateMapMarker);
                const latestEstimate = targetEstimateValues()[0];
                const selectedEstimate = selectedTargetEstimateId
                    ? targetEstimates.get(selectedTargetEstimateId)
                    : null;
                if (selectedTargetEstimateId && !selectedEstimate) {
                    selectedTargetEstimateId = null;
                }
                const activeEstimateIds = new Set();
                if (selectedEstimate) {
                    activeEstimateIds.add(selectedTargetEstimateId);
                    updateTargetEstimateOnMap(selectedEstimate);
                } else if (latestEstimate && isTargetEstimateActive(latestEstimate)) {
                    const groupId = targetEstimateId(latestEstimate);
                    if (groupId && !dismissedTargetEstimateIds.has(groupId)) {
                        activeEstimateIds.add(groupId);
                        updateTargetEstimateOnMap(latestEstimate);
                    }
                }
                cleanupTargetEstimateMarkers(activeEstimateIds);
                renderNodes();
                renderAlerts();
                renderTargetEstimates();
                renderEventGroups();
                renderTimeline();
                renderSummary();
            }

            async function refreshAll() {
                try {
                    const [statusResponse, eventsResponse, estimatesResponse, groupsResponse] = await Promise.all([
                        fetch('/device-status'),
                        fetch('/events'),
                        fetch('/target-estimates?limit=10'),
                        fetch('/event-groups?limit=8'),
                    ]);
                    const statusData = await statusResponse.json();
                    const eventsData = await eventsResponse.json();
                    const estimatesData = await estimatesResponse.json();
                    const groupsData = await groupsResponse.json();
                    devices.clear();
                    (statusData.devices || [])
                        .filter(device => device && device.device_id && !isDiagnosticDevice(device.device_id))
                        .forEach(device => devices.set(device.device_id, device));
                    events.splice(0, events.length, ...(eventsData.events || []));
                    targetEstimates.clear();
                    (Array.isArray(estimatesData) ? estimatesData : (estimatesData.estimates || []))
                        .forEach(estimate => targetEstimates.set(estimate.group_id, estimate));
                    eventGroups.clear();
                    (groupsData.event_groups || [])
                        .forEach(group => eventGroups.set(eventGroupId(group), group));
                    renderAll();
                } catch (error) {
                    document.getElementById('systemStatus').textContent = '資料讀取失敗';
                }
            }

            function connectWebSocket() {
                const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
                const ws = new WebSocket(`${protocol}//${window.location.host}/ws/dashboard`);
                ws.onmessage = event => {
                    const data = JSON.parse(event.data);
                    if (data.device_id && isDiagnosticDevice(data.device_id)) return;
                    if (data.type === 'location_update') {
                        devices.set(data.device_id, { ...(devices.get(data.device_id) || {}), ...data });
                        renderAll();
                    }
                    if (data.type === 'event_trigger') {
                        alertUntil.set(data.device_id, Date.now() + alertDurationMs);
                        devices.set(data.device_id, { ...(devices.get(data.device_id) || {}), ...data, status: 'event' });
                        refreshAll();
                    }
                    if (data.type === 'target_estimate') {
                        targetEstimates.set(data.group_id, data);
                        selectedTargetEstimateId = null;
                        const groupId = targetEstimateId(data);
                        if (groupId) {
                            dismissedTargetEstimateIds.delete(groupId);
                            cleanupTargetEstimateMarkers(new Set([groupId]));
                            updateTargetEstimateOnMap(data);
                        }
                        renderTargetEstimates();
                    }
                    if (data.type === 'event_group') {
                        const group = data.group || data;
                        if (eventGroupId(group)) {
                            eventGroups.set(eventGroupId(group), group);
                            renderEventGroups();
                        }
                    }
                    if (data.type === 'device_command_ack') {
                        document.getElementById('systemStatus').textContent = `指令回報 ${data.status}`;
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
