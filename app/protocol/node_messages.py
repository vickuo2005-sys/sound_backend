import time
import uuid
from typing import Any, Optional

from pydantic import BaseModel, Field

from .protocol_constants import (
    BACKEND_TO_NODE_MESSAGE_TYPES,
    COMMAND_TYPES,
    NODE_TO_BACKEND_MESSAGE_TYPES,
    PROTOCOL_VERSION,
)


class ProtocolError(ValueError):
    pass


def now_ms() -> int:
    return int(time.time() * 1000)


class NodeMessageEnvelope(BaseModel):
    protocol_version: int = PROTOCOL_VERSION
    message_type: str
    device_id: str
    message_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    sent_at_ms: int = Field(default_factory=now_ms)
    payload: dict[str, Any] = Field(default_factory=dict)


class NodeCommandEnvelope(BaseModel):
    command_id: str
    command_type: str
    args: dict[str, Any] = Field(default_factory=dict)
    issued_at_ms: int = Field(default_factory=now_ms)
    expires_at_ms: Optional[int] = None
    idempotency_key: str = Field(default_factory=lambda: str(uuid.uuid4()))


def build_envelope(
    *,
    message_type: str,
    device_id: str,
    payload: Optional[dict[str, Any]] = None,
    message_id: Optional[str] = None,
) -> dict[str, Any]:
    if message_type not in BACKEND_TO_NODE_MESSAGE_TYPES:
        raise ProtocolError(f"Unsupported backend message_type: {message_type}")
    envelope = NodeMessageEnvelope(
        message_type=message_type,
        device_id=device_id,
        message_id=message_id or str(uuid.uuid4()),
        payload=payload or {},
    )
    return envelope.dict()


def parse_node_message(raw: Any, expected_device_id: Optional[str] = None) -> NodeMessageEnvelope:
    if isinstance(raw, str):
        import json

        try:
            raw = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ProtocolError("Invalid JSON message") from exc

    if not isinstance(raw, dict):
        raise ProtocolError("Node message must be a JSON object")

    try:
        envelope = NodeMessageEnvelope(**raw)
    except Exception as exc:
        raise ProtocolError("Node message does not match protocol envelope") from exc

    if envelope.protocol_version != PROTOCOL_VERSION:
        raise ProtocolError(f"Unsupported protocol_version: {envelope.protocol_version}")
    if envelope.message_type not in NODE_TO_BACKEND_MESSAGE_TYPES:
        raise ProtocolError(f"Unsupported node message_type: {envelope.message_type}")
    if expected_device_id and envelope.device_id != expected_device_id:
        raise ProtocolError("device_id mismatch")

    if envelope.message_type in {"command_ack", "command_result"}:
        command_type = envelope.payload.get("command_type")
        if command_type is not None and str(command_type) not in COMMAND_TYPES:
            raise ProtocolError(f"Unsupported command_type: {command_type}")

    return envelope
