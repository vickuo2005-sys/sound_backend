import asyncio
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import WebSocket

from app.protocol import build_envelope


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class NodeConnectionState:
    device_id: str
    websocket: WebSocket
    connection_id: str
    generation: int
    protocol_version: int
    connected_at: float = field(default_factory=time.time)
    last_heartbeat_at: float = field(default_factory=time.time)
    recording: bool = False
    detection_enabled: bool = False
    streaming: bool = False
    battery_percent: Optional[int] = None
    gps_available: Optional[bool] = None
    network_type: Optional[str] = None
    app_version: Optional[str] = None
    upload_mode: Optional[str] = None
    ai_status: Optional[str] = None
    backend_status: Optional[str] = None
    app_status: Optional[str] = None
    last_ai_label: Optional[str] = None
    last_upload_status: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    gps_speed_mps: Optional[float] = None
    gps_heading_deg: Optional[float] = None
    gps_accuracy_m: Optional[float] = None
    time_sync_offset_ms: Optional[float] = None
    time_sync_rtt_ms: Optional[float] = None
    time_sync_quality: Optional[str] = None
    time_sync_at: Optional[str] = None
    last_time_sync_at: Optional[str] = None
    reconnect_count: int = 0
    last_disconnect_at: Optional[float] = None
    last_disconnect_reason: Optional[str] = None
    send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def heartbeat_age_seconds(self) -> float:
        return max(0.0, time.time() - self.last_heartbeat_at)

    def availability_status(self, degraded_after: float, offline_after: float) -> str:
        age = self.heartbeat_age_seconds()
        if age <= degraded_after:
            return "ONLINE"
        if age <= offline_after:
            return "DEGRADED"
        return "OFFLINE"

    def to_public_dict(self, degraded_after: float, offline_after: float) -> dict[str, Any]:
        return {
            "device_id": self.device_id,
            "connection_id": self.connection_id,
            "protocol_version": self.protocol_version,
            "connected_at": datetime.fromtimestamp(
                self.connected_at, tz=timezone.utc
            ).isoformat(),
            "last_heartbeat_at": datetime.fromtimestamp(
                self.last_heartbeat_at, tz=timezone.utc
            ).isoformat(),
            "heartbeat_age_seconds": round(self.heartbeat_age_seconds(), 3),
            "websocket_connected": True,
            "availability_status": self.availability_status(
                degraded_after,
                offline_after,
            ),
            "recording": self.recording,
            "detection_enabled": self.detection_enabled,
            "streaming": self.streaming,
            "battery_percent": self.battery_percent,
            "gps_available": self.gps_available,
            "network_type": self.network_type,
            "app_version": self.app_version,
            "upload_mode": self.upload_mode,
            "ai_status": self.ai_status,
            "backend_status": self.backend_status,
            "app_status": self.app_status,
            "last_ai_label": self.last_ai_label,
            "last_upload_status": self.last_upload_status,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "gps_speed_mps": self.gps_speed_mps,
            "gps_heading_deg": self.gps_heading_deg,
            "gps_accuracy_m": self.gps_accuracy_m,
            "time_sync_offset_ms": self.time_sync_offset_ms,
            "time_sync_rtt_ms": self.time_sync_rtt_ms,
            "time_sync_quality": self.time_sync_quality,
            "time_sync_at": self.time_sync_at,
            "last_time_sync_at": self.last_time_sync_at,
            "reconnect_count": self.reconnect_count,
            "last_disconnect_at": (
                datetime.fromtimestamp(
                    self.last_disconnect_at,
                    tz=timezone.utc,
                ).isoformat()
                if self.last_disconnect_at
                else None
            ),
            "last_disconnect_reason": self.last_disconnect_reason,
            "generation": self.generation,
        }


class NodeManager:
    def __init__(
        self,
        *,
        degraded_after_seconds: float = 10.0,
        offline_after_seconds: float = 20.0,
    ) -> None:
        self.degraded_after_seconds = degraded_after_seconds
        self.offline_after_seconds = offline_after_seconds
        self._connections: dict[str, NodeConnectionState] = {}
        self._last_disconnects: dict[str, dict[str, Any]] = {}
        self._generations: dict[str, int] = {}
        self._lock = asyncio.Lock()

    async def register(
        self,
        *,
        device_id: str,
        websocket: WebSocket,
        protocol_version: int,
        hello_payload: Optional[dict[str, Any]] = None,
    ) -> NodeConnectionState:
        hello_payload = hello_payload or {}
        async with self._lock:
            old = self._connections.get(device_id)
            if old is not None:
                old.last_disconnect_at = time.time()
                old.last_disconnect_reason = "replaced_by_new_connection"
                self._last_disconnects[device_id] = {
                    "at": old.last_disconnect_at,
                    "reason": old.last_disconnect_reason,
                }
                try:
                    await old.websocket.close(code=4000, reason="duplicate connection")
                except Exception:
                    pass

            generation = self._generations.get(device_id, 0) + 1
            self._generations[device_id] = generation
            connection_id = str(uuid.uuid4())
            prior_disconnect = self._last_disconnects.get(device_id, {})
            state = NodeConnectionState(
                device_id=device_id,
                websocket=websocket,
                connection_id=connection_id,
                generation=generation,
                protocol_version=protocol_version,
                app_version=hello_payload.get("app_version"),
                reconnect_count=int(hello_payload.get("reconnect_count") or 0),
                last_disconnect_at=prior_disconnect.get("at"),
                last_disconnect_reason=prior_disconnect.get("reason"),
            )
            self.apply_status_payload(state, hello_payload)
            self._connections[device_id] = state
            return state

    async def unregister(
        self,
        *,
        device_id: str,
        connection_id: str,
        reason: str,
    ) -> None:
        async with self._lock:
            current = self._connections.get(device_id)
            if current is None or current.connection_id != connection_id:
                return
            current.last_disconnect_at = time.time()
            current.last_disconnect_reason = reason
            self._last_disconnects[device_id] = {
                "at": current.last_disconnect_at,
                "reason": reason,
            }
            self._connections.pop(device_id, None)

    def apply_status_payload(
        self,
        state: NodeConnectionState,
        payload: dict[str, Any],
    ) -> None:
        if "recording" in payload:
            parsed = self._optional_bool(payload.get("recording"))
            if parsed is not None:
                state.recording = parsed
        if "detection_enabled" in payload:
            parsed = self._optional_bool(payload.get("detection_enabled"))
            if parsed is not None:
                state.detection_enabled = parsed
        if "streaming" in payload:
            parsed = self._optional_bool(payload.get("streaming"))
            if parsed is not None:
                state.streaming = parsed
        if "battery_percent" in payload and payload.get("battery_percent") is not None:
            try:
                state.battery_percent = int(payload.get("battery_percent"))
            except (TypeError, ValueError):
                state.battery_percent = None
        if "gps_available" in payload:
            state.gps_available = self._optional_bool(payload.get("gps_available"))
        for key in (
            "network_type",
            "app_version",
            "upload_mode",
            "ai_status",
            "backend_status",
            "app_status",
            "last_ai_label",
            "last_upload_status",
            "time_sync_quality",
            "time_sync_at",
            "last_time_sync_at",
        ):
            if key in payload:
                value = payload.get(key)
                setattr(state, key, str(value) if value is not None else None)
        for key in (
            "latitude",
            "longitude",
            "gps_speed_mps",
            "gps_heading_deg",
            "gps_accuracy_m",
            "time_sync_offset_ms",
            "time_sync_rtt_ms",
        ):
            if key in payload:
                setattr(state, key, self._optional_float(payload.get(key)))
        if "reconnect_count" in payload and payload.get("reconnect_count") is not None:
            try:
                state.reconnect_count = int(payload.get("reconnect_count"))
            except (TypeError, ValueError):
                pass

    @staticmethod
    def _optional_bool(value: Any) -> Optional[bool]:
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "1", "yes", "y", "on"}:
                return True
            if normalized in {"false", "0", "no", "n", "off"}:
                return False
        return None

    @staticmethod
    def _optional_float(value: Any) -> Optional[float]:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    async def update_heartbeat(
        self,
        *,
        device_id: str,
        connection_id: str,
        payload: Optional[dict[str, Any]] = None,
    ) -> Optional[dict[str, Any]]:
        state = self._connections.get(device_id)
        if state is None or state.connection_id != connection_id:
            return None
        state.last_heartbeat_at = time.time()
        if payload:
            self.apply_status_payload(state, payload)
        return state.to_public_dict(
            self.degraded_after_seconds,
            self.offline_after_seconds,
        )

    def get(self, device_id: str) -> Optional[NodeConnectionState]:
        return self._connections.get(device_id)

    def is_connected(self, device_id: str) -> bool:
        state = self.get(device_id)
        return state is not None and (
            state.availability_status(
                self.degraded_after_seconds,
                self.offline_after_seconds,
            )
            != "OFFLINE"
        )

    def live_states(self) -> list[dict[str, Any]]:
        return [
            state.to_public_dict(
                self.degraded_after_seconds,
                self.offline_after_seconds,
            )
            for state in sorted(
                self._connections.values(),
                key=lambda item: item.device_id,
            )
        ]

    async def send_json(self, device_id: str, message: dict[str, Any]) -> bool:
        state = self._connections.get(device_id)
        if state is None:
            return False
        async with state.send_lock:
            await state.websocket.send_json(message)
        return True

    async def send_protocol_message(
        self,
        *,
        device_id: str,
        message_type: str,
        payload: Optional[dict[str, Any]] = None,
    ) -> bool:
        return await self.send_json(
            device_id,
            build_envelope(
                message_type=message_type,
                device_id=device_id,
                payload=payload or {},
            ),
        )

    def disconnected_state(self, device_id: str) -> dict[str, Any]:
        prior_disconnect = self._last_disconnects.get(device_id, {})
        return {
            "device_id": device_id,
            "websocket_connected": False,
            "availability_status": "OFFLINE",
            "heartbeat_age_seconds": None,
            "last_disconnect_at": (
                datetime.fromtimestamp(
                    prior_disconnect["at"],
                    tz=timezone.utc,
                ).isoformat()
                if prior_disconnect.get("at")
                else None
            ),
            "last_disconnect_reason": prior_disconnect.get("reason"),
        }
