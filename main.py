import json
import os
import re
import sqlite3
from datetime import datetime, timezone
from typing import Optional
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
from fastapi.responses import HTMLResponse
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


def current_time_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def current_date_yyyymmdd() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d")


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
    "last_event_id",
    "last_event_at",
    "status",
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
                last_event_id TEXT,
                last_event_at TEXT,
                status TEXT DEFAULT 'online'
            )
            """
        )
        add_sqlite_column_if_missing(
            connection=connection,
            table_name="device_status",
            column_name="latitude",
            column_definition="REAL",
        )
        add_sqlite_column_if_missing(
            connection=connection,
            table_name="device_status",
            column_name="longitude",
            column_definition="REAL",
        )
        add_sqlite_column_if_missing(
            connection=connection,
            table_name="device_status",
            column_name="last_seen",
            column_definition="TEXT",
        )
        add_sqlite_column_if_missing(
            connection=connection,
            table_name="device_status",
            column_name="last_event_id",
            column_definition="TEXT",
        )
        add_sqlite_column_if_missing(
            connection=connection,
            table_name="device_status",
            column_name="last_event_at",
            column_definition="TEXT",
        )
        add_sqlite_column_if_missing(
            connection=connection,
            table_name="device_status",
            column_name="status",
            column_definition="TEXT DEFAULT 'online'",
        )
        connection.commit()


def init_postgres_db() -> None:
    connection = get_postgres_connection()
    try:
        with connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
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
                        last_event_id TEXT,
                        last_event_at TIMESTAMPTZ,
                        status TEXT DEFAULT 'online'
                    )
                    """
                )
                cursor.execute(
                    "ALTER TABLE device_status ADD COLUMN IF NOT EXISTS latitude DOUBLE PRECISION"
                )
                cursor.execute(
                    "ALTER TABLE device_status ADD COLUMN IF NOT EXISTS longitude DOUBLE PRECISION"
                )
                cursor.execute(
                    "ALTER TABLE device_status ADD COLUMN IF NOT EXISTS last_seen TIMESTAMPTZ DEFAULT now()"
                )
                cursor.execute(
                    "ALTER TABLE device_status ADD COLUMN IF NOT EXISTS last_event_id TEXT"
                )
                cursor.execute(
                    "ALTER TABLE device_status ADD COLUMN IF NOT EXISTS last_event_at TIMESTAMPTZ"
                )
                cursor.execute(
                    "ALTER TABLE device_status ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'online'"
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
    return serialized


def upsert_device_location(
    device_id: str,
    latitude: float,
    longitude: float,
) -> dict:
    if not use_postgres():
        last_seen = current_time_iso()
        with get_sqlite_connection() as connection:
            connection.execute(
                """
                INSERT INTO device_status (
                    device_id,
                    latitude,
                    longitude,
                    last_seen,
                    status
                )
                VALUES (?, ?, ?, ?, 'online')
                ON CONFLICT(device_id) DO UPDATE SET
                    latitude = excluded.latitude,
                    longitude = excluded.longitude,
                    last_seen = excluded.last_seen,
                    status = 'online'
                """,
                (device_id, latitude, longitude, last_seen),
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
            return dict(row)

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
                        status
                    )
                    VALUES (%s, %s, %s, now(), 'online')
                    ON CONFLICT (device_id) DO UPDATE SET
                        latitude = EXCLUDED.latitude,
                        longitude = EXCLUDED.longitude,
                        last_seen = now(),
                        status = 'online'
                    RETURNING
                        device_id,
                        latitude,
                        longitude,
                        last_seen,
                        last_event_id,
                        last_event_at,
                        status
                    """,
                    (device_id, latitude, longitude),
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
                    status
                )
                VALUES (?, ?, ?, ?, ?, ?, 'event')
                ON CONFLICT(device_id) DO UPDATE SET
                    latitude = excluded.latitude,
                    longitude = excluded.longitude,
                    last_seen = excluded.last_seen,
                    last_event_id = excluded.last_event_id,
                    last_event_at = excluded.last_event_at,
                    status = 'event'
                """,
                (
                    event.device_id,
                    event.latitude,
                    event.longitude,
                    now,
                    event.event_id,
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
            return dict(row)

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
                        last_event_id,
                        last_event_at,
                        status
                    )
                    VALUES (%s, %s, %s, now(), %s, now(), 'event')
                    ON CONFLICT (device_id) DO UPDATE SET
                        latitude = EXCLUDED.latitude,
                        longitude = EXCLUDED.longitude,
                        last_seen = now(),
                        last_event_id = EXCLUDED.last_event_id,
                        last_event_at = now(),
                        status = 'event'
                    RETURNING
                        device_id,
                        latitude,
                        longitude,
                        last_seen,
                        last_event_id,
                        last_event_at,
                        status
                    """,
                    (
                        event.device_id,
                        event.latitude,
                        event.longitude,
                        event.event_id,
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
            return [dict(row) for row in rows]

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
    )

    await dashboard_manager.broadcast(
        {
            "type": "location_update",
            "device_id": device_row.get("device_id"),
            "latitude": device_row.get("latitude"),
            "longitude": device_row.get("longitude"),
            "last_seen": device_row.get("last_seen"),
            "last_event_id": device_row.get("last_event_id"),
            "last_event_at": device_row.get("last_event_at"),
            "status": device_row.get("status"),
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

    if not maps_api_key:
        return HTMLResponse(
            content="""
            <!doctype html>
            <html lang="zh-Hant">
            <head>
                <meta charset="utf-8">
                <meta name="viewport" content="width=device-width, initial-scale=1">
                <title>\u624b\u6a5f\u5373\u6642\u5b9a\u4f4d Dashboard</title>
                <style>
                    body {
                        margin: 0;
                        font-family: Arial, "Noto Sans TC", sans-serif;
                        background: #f6f7f9;
                        color: #202124;
                    }
                    header {
                        padding: 16px 20px;
                        background: #ffffff;
                        border-bottom: 1px solid #dfe3e8;
                        font-size: 22px;
                        font-weight: 700;
                    }
                    main {
                        padding: 20px;
                    }
                    .message {
                        max-width: 720px;
                        padding: 16px;
                        background: #ffffff;
                        border: 1px solid #dfe3e8;
                        border-radius: 8px;
                    }
                </style>
            </head>
            <body>
                <header>\u624b\u6a5f\u5373\u6642\u5b9a\u4f4d Dashboard</header>
                <main>
                    <div class="message">
                        GOOGLE_MAPS_API_KEY \u5c1a\u672a\u8a2d\u5b9a\uff0c\u8acb\u5148\u5728 Render Environment Variables \u65b0\u589e\u9019\u500b\u74b0\u5883\u8b8a\u6578\u3002
                    </div>
                </main>
            </body>
            </html>
            """,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    maps_script_url = (
        "https://maps.googleapis.com/maps/api/js"
        f"?key={quote(maps_api_key, safe='')}&callback=initMap"
    )

    html = """
    <!doctype html>
    <html lang="zh-Hant">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>\u624b\u6a5f\u5373\u6642\u5b9a\u4f4d Dashboard</title>
        <style>
            html,
            body {
                height: 100%;
                margin: 0;
                font-family: Arial, "Noto Sans TC", sans-serif;
                background: #f6f7f9;
                color: #202124;
            }

            body {
                display: flex;
                flex-direction: column;
            }

            header {
                padding: 16px 20px;
                background: #ffffff;
                border-bottom: 1px solid #dfe3e8;
                font-size: 22px;
                font-weight: 700;
            }

            #legend {
                display: flex;
                flex-wrap: wrap;
                gap: 14px;
                padding: 10px 20px;
                background: #ffffff;
                border-bottom: 1px solid #dfe3e8;
                font-size: 14px;
            }

            .legend-item {
                display: inline-flex;
                align-items: center;
                gap: 6px;
                white-space: nowrap;
            }

            .legend-shape {
                display: inline-block;
                min-width: 18px;
                text-align: center;
                font-size: 18px;
                line-height: 1;
            }

            #status-message {
                display: none;
                padding: 12px 20px;
                background: #fff7d6;
                border-bottom: 1px solid #ead48a;
                color: #4d3b00;
                font-size: 15px;
            }

            #map {
                flex: 1;
                min-height: 480px;
            }

            .info-window {
                min-width: 280px;
                line-height: 1.5;
                font-size: 14px;
            }

            .info-window strong {
                display: inline-block;
                min-width: 112px;
            }

            .device-marker {
                position: absolute;
                transform: translate(-50%, -50%);
                cursor: pointer;
                display: flex;
                flex-direction: column;
                align-items: center;
                pointer-events: auto;
                user-select: none;
            }

            .marker-visual {
                width: 38px;
                height: 38px;
                background: #ffffff;
                border: 3px solid #202124;
                box-shadow: 0 2px 8px rgba(0, 0, 0, 0.35);
                display: flex;
                align-items: center;
                justify-content: center;
                box-sizing: border-box;
            }

            .marker-label {
                color: #202124;
                font-size: 11px;
                font-weight: 800;
                line-height: 1;
                text-align: center;
            }

            .shape-circle .marker-visual {
                border-radius: 50%;
            }

            .shape-square .marker-visual {
                border-radius: 4px;
            }

            .shape-triangle .marker-visual {
                clip-path: polygon(50% 0%, 100% 100%, 0% 100%);
                padding-top: 10px;
            }

            .shape-diamond .marker-visual {
                clip-path: polygon(50% 0%, 100% 50%, 50% 100%, 0% 50%);
            }

            .shape-diamond .marker-label {
                transform: rotate(-45deg);
            }

            .shape-diamond .marker-visual {
                transform: rotate(45deg);
            }

            .shape-hexagon .marker-visual {
                clip-path: polygon(25% 0%, 75% 0%, 100% 50%, 75% 100%, 25% 100%, 0% 50%);
            }

            .recent-event::before {
                content: "";
                position: absolute;
                top: -9px;
                left: 50%;
                width: 54px;
                height: 54px;
                border: 3px solid #202124;
                border-radius: 50%;
                transform: translateX(-50%);
                animation: pulse-ring 1.25s ease-out infinite;
                z-index: -1;
            }

            .recent-event .marker-visual {
                animation: marker-pop 0.7s ease-in-out infinite alternate;
            }

            @keyframes pulse-ring {
                0% {
                    opacity: 0.85;
                    transform: translateX(-50%) scale(0.55);
                }
                100% {
                    opacity: 0;
                    transform: translateX(-50%) scale(1.35);
                }
            }

            @keyframes marker-pop {
                0% {
                    transform: scale(1);
                }
                100% {
                    transform: scale(1.16);
                }
            }

            .shape-diamond.recent-event .marker-visual {
                animation: marker-pop-diamond 0.7s ease-in-out infinite alternate;
            }

            @keyframes marker-pop-diamond {
                0% {
                    transform: rotate(45deg) scale(1);
                }
                100% {
                    transform: rotate(45deg) scale(1.16);
                }
            }
        </style>
    </head>
    <body>
        <header>\u624b\u6a5f\u5373\u6642\u5b9a\u4f4d Dashboard</header>
        <div id="legend">
            <span class="legend-item">
                <span class="legend-shape">\u25cb</span>
                node_A01
            </span>
            <span class="legend-item">
                <span class="legend-shape">\u25a1</span>
                node_A02
            </span>
            <span class="legend-item">
                <span class="legend-shape">\u25b3</span>
                node_A03
            </span>
            <span class="legend-item">
                <span class="legend-shape">\u25c7</span>
                node_A04
            </span>
            <span class="legend-item">
                <span class="legend-shape">\u2b21</span>
                \u5176\u4ed6
            </span>
        </div>
        <div id="status-message"></div>
        <div id="map"></div>

        <script>
            let map;
            let infoWindow;
            let DeviceMarker;
            let hasFitInitialBounds = false;
            const deviceMarkers = new Map();
            const ACTIVE_ALERT_WINDOW_MS = 3000;

            function showStatusMessage(message) {
                const element = document.getElementById("status-message");
                element.textContent = message;
                element.style.display = "block";
            }

            function hideStatusMessage() {
                const element = document.getElementById("status-message");
                element.textContent = "";
                element.style.display = "none";
            }

            function formatValue(value) {
                if (value === null || value === undefined || value === "") {
                    return "\u7121\u8cc7\u6599";
                }
                return String(value).replace(/[&<>"']/g, (char) => ({
                    "&": "&amp;",
                    "<": "&lt;",
                    ">": "&gt;",
                    '"': "&quot;",
                    "'": "&#39;",
                }[char]));
            }

            function buildInfoContent(device) {
                return `
                    <div class="info-window">
                        <div><strong>device_id</strong>${formatValue(device.device_id)}</div>
                        <div><strong>latitude</strong>${formatValue(device.latitude)}</div>
                        <div><strong>longitude</strong>${formatValue(device.longitude)}</div>
                        <div><strong>last_seen</strong>${formatValue(device.last_seen)}</div>
                        <div><strong>last_event_id</strong>${formatValue(device.last_event_id)}</div>
                        <div><strong>last_event_at</strong>${formatValue(device.last_event_at)}</div>
                        <div><strong>status</strong>${formatValue(device.status)}</div>
                    </div>
                `;
            }

            function hasCoordinate(value) {
                return (
                    value !== null &&
                    value !== undefined &&
                    value !== "" &&
                    Number.isFinite(Number(value))
                );
            }

            async function loadDeviceStatus() {
                const response = await fetch("/device-status");
                if (!response.ok) {
                    throw new Error("Failed to load device status");
                }
                const data = await response.json();
                return data.devices || [];
            }

            function getDeviceShape(deviceId) {
                const shapeMap = {
                    node_A01: "circle",
                    node_A02: "square",
                    node_A03: "triangle",
                    node_A04: "diamond",
                };
                return shapeMap[deviceId] || "hexagon";
            }

            function getDeviceLabel(deviceId) {
                const labelMap = {
                    node_A01: "A01",
                    node_A02: "A02",
                    node_A03: "A03",
                    node_A04: "A04",
                };
                if (labelMap[deviceId]) {
                    return labelMap[deviceId];
                }
                if (!deviceId) {
                    return "?";
                }
                return String(deviceId).replace(/^node_/, "").slice(0, 8);
            }

            function isRecentEvent(lastEventAt) {
                if (!lastEventAt) {
                    return false;
                }
                const eventTime = new Date(lastEventAt).getTime();
                if (!Number.isFinite(eventTime)) {
                    return false;
                }
                return Date.now() - eventTime <= ACTIVE_ALERT_WINDOW_MS;
            }

            function createDeviceMarkerClass() {
                return class extends google.maps.OverlayView {
                    constructor(device) {
                        super();
                        this.device = device;
                        this.position = new google.maps.LatLng(
                            Number(device.latitude),
                            Number(device.longitude)
                        );
                        this.div = null;
                    }

                    onAdd() {
                        this.div = document.createElement("div");
                        this.div.addEventListener("click", () => {
                            infoWindow.setContent(buildInfoContent(this.device));
                            infoWindow.setPosition(this.position);
                            infoWindow.open(map);
                        });
                        this.render();
                        this.getPanes().overlayMouseTarget.appendChild(this.div);
                    }

                    draw() {
                        if (!this.div) {
                            return;
                        }

                        const point = this.getProjection().fromLatLngToDivPixel(this.position);
                        if (!point) {
                            return;
                        }

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
                        this.device = device;
                        this.position = new google.maps.LatLng(
                            Number(device.latitude),
                            Number(device.longitude)
                        );
                        this.render();
                        this.draw();
                    }

                    render() {
                        if (!this.div) {
                            return;
                        }

                        const shape = getDeviceShape(this.device.device_id);
                        const label = getDeviceLabel(this.device.device_id);
                        const recentClass = isRecentEvent(this.device.last_event_at)
                            ? "recent-event"
                            : "";

                        this.div.className = `device-marker shape-${shape} ${recentClass}`;
                        this.div.title = this.device.device_id || "unknown_device";
                        this.div.innerHTML = `
                            <div class="marker-visual">
                                <span class="marker-label">${formatValue(label)}</span>
                            </div>
                        `;
                    }
                };
            }

            function upsertDeviceMarker(device) {
                if (
                    !device.device_id ||
                    !hasCoordinate(device.latitude) ||
                    !hasCoordinate(device.longitude)
                ) {
                    return false;
                }

                if (deviceMarkers.has(device.device_id)) {
                    const existingDevice = deviceMarkers.get(device.device_id).device || {};
                    const mergedDevice = { ...existingDevice, ...device };
                    deviceMarkers.get(device.device_id).update(mergedDevice);
                } else {
                    const marker = new DeviceMarker(device);
                    marker.setMap(map);
                    deviceMarkers.set(device.device_id, marker);
                }

                return true;
            }

            async function loadInitialDeviceMarkers() {
                try {
                    const devices = await loadDeviceStatus();
                    const bounds = new google.maps.LatLngBounds();
                    let markerCount = 0;

                    devices.forEach((device) => {
                        if (!upsertDeviceMarker(device)) return;

                        bounds.extend({
                            lat: Number(device.latitude),
                            lng: Number(device.longitude),
                        });
                        markerCount += 1;
                    });

                    if (markerCount === 0) {
                        showStatusMessage(
                            "\u76ee\u524d\u6c92\u6709\u53ef\u986f\u793a\u65bc\u5730\u5716\u4e0a\u7684\u624b\u6a5f\u4f4d\u7f6e"
                        );
                        return;
                    }

                    hideStatusMessage();

                    if (!hasFitInitialBounds) {
                        if (markerCount === 1) {
                            map.setCenter(bounds.getCenter());
                            map.setZoom(16);
                        } else {
                            map.fitBounds(bounds);
                        }
                        hasFitInitialBounds = true;
                    }
                } catch (error) {
                    console.error(error);
                    showStatusMessage("\u88dd\u7f6e\u4f4d\u7f6e\u8cc7\u6599\u8f09\u5165\u5931\u6557");
                }
            }

            function handleDashboardMessage(message) {
                if (message.type === "location_update") {
                    upsertDeviceMarker({
                        device_id: message.device_id,
                        latitude: message.latitude,
                        longitude: message.longitude,
                        last_seen: message.last_seen,
                        last_event_id: message.last_event_id,
                        last_event_at: message.last_event_at,
                        status: message.status,
                    });
                    hideStatusMessage();
                    return;
                }

                if (message.type === "event_trigger") {
                    upsertDeviceMarker({
                        device_id: message.device_id,
                        latitude: message.latitude,
                        longitude: message.longitude,
                        last_event_id: message.event_id,
                        last_event_at: message.last_event_at,
                        status: message.status,
                    });
                    hideStatusMessage();
                }
            }

            function connectDashboardWebSocket() {
                const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
                const wsUrl = `${protocol}//${window.location.host}/ws/dashboard`;
                const socket = new WebSocket(wsUrl);

                socket.addEventListener("open", () => {
                    hideStatusMessage();
                });

                socket.addEventListener("message", (event) => {
                    try {
                        handleDashboardMessage(JSON.parse(event.data));
                    } catch (error) {
                        console.error(error);
                    }
                });

                socket.addEventListener("close", () => {
                    showStatusMessage("\u5373\u6642\u9023\u7dda\u4e2d\u65b7\uff0c\u6b63\u5728\u91cd\u65b0\u9023\u7dda");
                    window.setTimeout(connectDashboardWebSocket, 3000);
                });

                socket.addEventListener("error", () => {
                    socket.close();
                });
            }

            function refreshMarkerAnimations() {
                deviceMarkers.forEach((marker) => {
                    marker.render();
                });
            }

            window.initMap = function initMap() {
                const defaultCenter = { lat: 25.033, lng: 121.565 };
                map = new google.maps.Map(document.getElementById("map"), {
                    center: defaultCenter,
                    zoom: 12,
                    mapTypeControl: false,
                    streetViewControl: false,
                });
                infoWindow = new google.maps.InfoWindow();
                DeviceMarker = createDeviceMarkerClass();

                loadInitialDeviceMarkers();
                connectDashboardWebSocket();
                window.setInterval(refreshMarkerAnimations, 1000);
            };
        </script>
        <script async defer src="__MAPS_SCRIPT_URL__"></script>
    </body>
    </html>
    """
    html = html.replace("__MAPS_SCRIPT_URL__", maps_script_url)
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
