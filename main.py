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
    note: Optional[str] = None


def current_time_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def current_date_yyyymmdd() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d")


def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_NAME)
    connection.row_factory = sqlite3.Row
    return connection


def init_db() -> None:
    with get_connection() as connection:
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
                note TEXT,
                created_at TEXT
            )
            """
        )
        connection.commit()


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

    with get_connection() as connection:
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
                note,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
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
                event.note,
                created_at,
            ),
        )
        connection.commit()
        db_id = cursor.lastrowid

    return {
        "status": "success",
        "message": "Event received",
        "event_id": event.event_id,
        "db_id": db_id,
    }


@app.get("/events")
def list_events():
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                id,
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
                note,
                created_at
            FROM events
            ORDER BY id DESC
            LIMIT 50
            """
        ).fetchall()

    return {
        "status": "success",
        "count": len(rows),
        "events": [dict(row) for row in rows],
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
                <title>聲音事件地圖 Dashboard</title>
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
                <header>聲音事件地圖 Dashboard</header>
                <main>
                    <div class="message">
                        GOOGLE_MAPS_API_KEY 尚未設定，請先到 Render Environment Variables 新增這個環境變數。
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

    html = f"""
    <!doctype html>
    <html lang="zh-Hant">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>聲音事件地圖 Dashboard</title>
        <style>
            html,
            body {{
                height: 100%;
                margin: 0;
                font-family: Arial, "Noto Sans TC", sans-serif;
                background: #f6f7f9;
                color: #202124;
            }}

            body {{
                display: flex;
                flex-direction: column;
            }}

            header {{
                padding: 16px 20px;
                background: #ffffff;
                border-bottom: 1px solid #dfe3e8;
                font-size: 22px;
                font-weight: 700;
            }}

            #map {{
                flex: 1;
                min-height: 480px;
            }}

            .info-window {{
                min-width: 240px;
                line-height: 1.5;
                font-size: 14px;
            }}

            .info-window strong {{
                display: inline-block;
                min-width: 92px;
            }}
        </style>
    </head>
    <body>
        <header>聲音事件地圖 Dashboard</header>
        <div id="map"></div>

        <script>
            let map;
            let infoWindow;

            function formatValue(value) {{
                if (value === null || value === undefined || value === "") {{
                    return "無資料";
                }}
                return String(value).replace(/[&<>"']/g, (char) => ({{
                    "&": "&amp;",
                    "<": "&lt;",
                    ">": "&gt;",
                    '"': "&quot;",
                    "'": "&#39;",
                }}[char]));
            }}

            function buildInfoContent(event) {{
                const audioValue = event.audio_path || event.audio_file_name || "";
                return `
                    <div class="info-window">
                        <div><strong>event_id</strong>${{formatValue(event.event_id)}}</div>
                        <div><strong>device_id</strong>${{formatValue(event.device_id)}}</div>
                        <div><strong>timestamp</strong>${{formatValue(event.timestamp)}}</div>
                        <div><strong>rms_peak</strong>${{formatValue(event.rms_peak)}}</div>
                        <div><strong>label</strong>${{formatValue(event.label)}}</div>
                        <div><strong>audio</strong>${{formatValue(audioValue)}}</div>
                    </div>
                `;
            }}

            async function loadEvents() {{
                const response = await fetch("/events");
                if (!response.ok) {{
                    throw new Error("Failed to load events");
                }}
                const data = await response.json();
                return data.events || [];
            }}

            window.initMap = async function initMap() {{
                const defaultCenter = {{ lat: 23.6978, lng: 120.9605 }};
                map = new google.maps.Map(document.getElementById("map"), {{
                    center: defaultCenter,
                    zoom: 7,
                    mapTypeControl: false,
                    streetViewControl: false,
                }});
                infoWindow = new google.maps.InfoWindow();

                try {{
                    const events = await loadEvents();
                    const bounds = new google.maps.LatLngBounds();
                    let markerCount = 0;

                    events.forEach((event) => {{
                        const hasLatitude = (
                            event.latitude !== null &&
                            event.latitude !== undefined &&
                            event.latitude !== ""
                        );
                        const hasLongitude = (
                            event.longitude !== null &&
                            event.longitude !== undefined &&
                            event.longitude !== ""
                        );
                        const lat = Number(event.latitude);
                        const lng = Number(event.longitude);

                        if (
                            !hasLatitude ||
                            !hasLongitude ||
                            !Number.isFinite(lat) ||
                            !Number.isFinite(lng)
                        ) {{
                            return;
                        }}

                        const position = {{ lat, lng }};
                        const marker = new google.maps.Marker({{
                            position,
                            map,
                            title: event.event_id || event.device_id || "sound event",
                        }});

                        marker.addListener("click", () => {{
                            infoWindow.setContent(buildInfoContent(event));
                            infoWindow.open({{ anchor: marker, map }});
                        }});

                        bounds.extend(position);
                        markerCount += 1;
                    }});

                    if (markerCount === 1) {{
                        map.setCenter(bounds.getCenter());
                        map.setZoom(15);
                    }} else if (markerCount > 1) {{
                        map.fitBounds(bounds);
                    }}
                }} catch (error) {{
                    console.error(error);
                }}
            }};
        </script>
        <script async defer src="{maps_script_url}"></script>
    </body>
    </html>
    """
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
