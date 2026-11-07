import time
import uuid
from typing import Any, Callable, Optional

from app.protocol import NodeCommandEnvelope, build_envelope
from app.protocol.protocol_constants import LEGACY_COMMAND_MAP
from .node_manager import NodeManager


class RealtimeCommandService:
    def __init__(
        self,
        *,
        node_manager: NodeManager,
        status_updater: Callable[[int, str, str, Optional[str]], Optional[dict]],
    ) -> None:
        self.node_manager = node_manager
        self.status_updater = status_updater

    @staticmethod
    def legacy_to_protocol_command(command: str, value: Any = None) -> tuple[str, dict[str, Any]]:
        normalized = command.strip().lower()
        command_type = LEGACY_COMMAND_MAP.get(normalized, normalized.upper())
        args: dict[str, Any] = {}
        if normalized == "set_detection_mode":
            args["upload_mode"] = "detection_only"
        elif normalized == "set_collection_mode":
            args["upload_mode"] = "collect_all"
        elif normalized == "start_live_audio":
            if isinstance(value, dict):
                args.update(value)
        elif normalized == "stop_live_audio":
            if isinstance(value, dict):
                args.update(value)
        elif value is not None:
            args["value"] = value
        return command_type, args

    async def push_command(
        self,
        *,
        device_id: str,
        command_id: int,
        command: str,
        value: Any = None,
        timeout_seconds: float = 30,
    ) -> bool:
        if not self.node_manager.is_connected(device_id):
            return False

        command_type, args = self.legacy_to_protocol_command(command, value)
        issued_at_ms = int(time.time() * 1000)
        envelope = NodeCommandEnvelope(
            command_id=str(command_id),
            command_type=command_type,
            args=args,
            issued_at_ms=issued_at_ms,
            expires_at_ms=issued_at_ms + int(timeout_seconds * 1000),
            idempotency_key=f"{device_id}:{command_id}:{uuid.uuid4()}",
        )
        message = build_envelope(
            message_type="command",
            device_id=device_id,
            payload=envelope.dict(),
        )
        delivered = await self.node_manager.send_json(device_id, message)
        if delivered:
            self.status_updater(
                command_id,
                device_id,
                "sent",
                "delivered over node websocket",
            )
        return delivered
