import os
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, status
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
