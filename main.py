import json
import os
import re
import sqlite3
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import quote

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile, status
from fastapi.responses import HTMLResponse
from google.cloud import storage
from google.oauth2 import service_account
from pydantic import BaseModel


app = FastAPI()

DB_NAME = "sound_events.db"
DEFAULT_UPLOAD_TOKEN = "test-token-123"


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


def verify_upload_token(upload_token: Optional[str]) -> None:
    expected_token = os.getenv("UPLOAD_TOKEN", DEFAULT_UPLOAD_TOKEN)
    if upload_token != expected_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid upload token",
        )


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


def build_audio_path(device_id: str, event_id: str) -> str:
    safe_device_id = safe_path_part(device_id)
    safe_event_id = safe_path_part(event_id)
    return f"audio/{safe_device_id}/{current_date_yyyymmdd()}/{safe_event_id}.wav"


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
def create_event(
    event: SoundEvent,
    upload_token: Optional[str] = Header(default=None, alias="x-upload-token"),
):
    verify_upload_token(upload_token)
    created_at = current_time_iso()
    db_id = save_event(event, created_at)

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
                <title>\u8072\u97f3\u4e8b\u4ef6\u5730\u5716 Dashboard</title>
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
                <header>\u8072\u97f3\u4e8b\u4ef6\u5730\u5716 Dashboard</header>
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
        <title>\u8072\u97f3\u4e8b\u4ef6\u5730\u5716 Dashboard</title>
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
                gap: 12px;
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

            .legend-dot {
                width: 12px;
                height: 12px;
                border-radius: 50%;
                border: 1px solid rgba(0, 0, 0, 0.25);
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
        </style>
    </head>
    <body>
        <header>\u8072\u97f3\u4e8b\u4ef6\u5730\u5716 Dashboard</header>
        <div id="legend">
            <span class="legend-item">
                <span class="legend-dot" style="background: #d93025;"></span>
                \u7d05\u8272\uff1anode_A01
            </span>
            <span class="legend-item">
                <span class="legend-dot" style="background: #1a73e8;"></span>
                \u85cd\u8272\uff1anode_A02
            </span>
            <span class="legend-item">
                <span class="legend-dot" style="background: #188038;"></span>
                \u7da0\u8272\uff1anode_A03
            </span>
            <span class="legend-item">
                <span class="legend-dot" style="background: #f29900;"></span>
                \u6a58\u8272\uff1anode_A04
            </span>
            <span class="legend-item">
                <span class="legend-dot" style="background: #80868b;"></span>
                \u7070\u8272\uff1a\u5176\u4ed6
            </span>
        </div>
        <div id="status-message"></div>
        <div id="map"></div>

        <script>
            let map;
            let infoWindow;

            function showStatusMessage(message) {
                const element = document.getElementById("status-message");
                element.textContent = message;
                element.style.display = "block";
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

            function buildInfoContent(event) {
                const audioPathValue = event.audio_path || event.local_audio_path || "";
                return `
                    <div class="info-window">
                        <div><strong>event_id</strong>${formatValue(event.event_id)}</div>
                        <div><strong>device_id</strong>${formatValue(event.device_id)}</div>
                        <div><strong>timestamp</strong>${formatValue(event.timestamp)}</div>
                        <div><strong>latitude</strong>${formatValue(event.latitude)}</div>
                        <div><strong>longitude</strong>${formatValue(event.longitude)}</div>
                        <div><strong>rms_peak</strong>${formatValue(event.rms_peak)}</div>
                        <div><strong>label</strong>${formatValue(event.label)}</div>
                        <div><strong>audio_file_name</strong>${formatValue(event.audio_file_name)}</div>
                        <div><strong>audio_path</strong>${formatValue(audioPathValue)}</div>
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

            async function loadEvents() {
                const response = await fetch("/events");
                if (!response.ok) {
                    throw new Error("Failed to load events");
                }
                const data = await response.json();
                return data.events || [];
            }

            function getDeviceMarkerColor(deviceId) {
                const colorMap = {
                    node_A01: "#d93025",
                    node_A02: "#1a73e8",
                    node_A03: "#188038",
                    node_A04: "#f29900",
                };
                return colorMap[deviceId] || "#80868b";
            }

            function buildMarkerIcon(deviceId) {
                const color = getDeviceMarkerColor(deviceId);
                const svg = `
                    <svg xmlns="http://www.w3.org/2000/svg" width="32" height="44" viewBox="0 0 32 44">
                        <path fill="${color}" stroke="white" stroke-width="2" d="M16 2C8.3 2 2 8.3 2 16c0 10.5 14 26 14 26s14-15.5 14-26C30 8.3 23.7 2 16 2z"/>
                        <circle cx="16" cy="16" r="5" fill="white"/>
                    </svg>
                `;
                return {
                    url: `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg)}`,
                    scaledSize: new google.maps.Size(32, 44),
                    anchor: new google.maps.Point(16, 44),
                };
            }

            window.initMap = async function initMap() {
                const defaultCenter = { lat: 25.033, lng: 121.565 };
                map = new google.maps.Map(document.getElementById("map"), {
                    center: defaultCenter,
                    zoom: 12,
                    mapTypeControl: false,
                    streetViewControl: false,
                });
                infoWindow = new google.maps.InfoWindow();

                try {
                    const events = await loadEvents();
                    const bounds = new google.maps.LatLngBounds();
                    let markerCount = 0;

                    events.forEach((event) => {
                        if (
                            !hasCoordinate(event.latitude) ||
                            !hasCoordinate(event.longitude)
                        ) {
                            return;
                        }

                        const position = {
                            lat: Number(event.latitude),
                            lng: Number(event.longitude),
                        };
                        const marker = new google.maps.Marker({
                            position,
                            map,
                            icon: buildMarkerIcon(event.device_id),
                            title: `${event.device_id || "unknown_device"} - ${event.event_id || "unknown_event"}`,
                        });

                        marker.addListener("click", () => {
                            infoWindow.setContent(buildInfoContent(event));
                            infoWindow.open({ anchor: marker, map });
                        });

                        bounds.extend(position);
                        markerCount += 1;
                    });

                    if (markerCount === 0) {
                        showStatusMessage(
                            "\u76ee\u524d\u6c92\u6709\u53ef\u986f\u793a\u65bc\u5730\u5716\u4e0a\u7684\u4e8b\u4ef6\u8cc7\u6599"
                        );
                    } else if (markerCount === 1) {
                        map.setCenter(bounds.getCenter());
                        map.setZoom(15);
                    } else {
                        map.fitBounds(bounds);
                    }
                } catch (error) {
                    console.error(error);
                    showStatusMessage("\u4e8b\u4ef6\u8cc7\u6599\u8f09\u5165\u5931\u6557");
                }
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
    file: UploadFile = File(...),
    upload_token: Optional[str] = Header(default=None, alias="x-upload-token"),
):
    verify_upload_token(upload_token)

    if not file.filename or not file.filename.lower().endswith(".wav"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only .wav files are allowed",
        )

    audio_path = build_audio_path(device_id=device_id, event_id=event_id)
    bucket = get_gcs_bucket()
    blob = bucket.blob(audio_path)

    try:
        file.file.seek(0)
        blob.upload_from_file(
            file.file,
            content_type=file.content_type or "audio/wav",
        )
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
        "audio_path": audio_path,
    }
