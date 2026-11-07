import asyncio
import json
import struct
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.protocol import (
    AUDIO_FRAME_HEADER_LENGTH,
    AUDIO_FRAME_MAGIC,
    PROTOCOL_VERSION,
    ProtocolError,
    build_envelope,
    parse_audio_frame,
    parse_node_message,
)
from app.protocol.protocol_constants import AUDIO_FRAME_STRUCT_FORMAT, AUDIO_CODEC_OPUS
from services.realtime import AudioStreamManager, NodeManager


class FakeWebSocket:
    def __init__(self) -> None:
        self.sent = []
        self.closed = False

    async def send_json(self, message):
        self.sent.append(message)

    async def close(self, code=1000, reason=None):
        self.closed = True
        self.close_code = code
        self.close_reason = reason


def build_audio_frame(*, stream_id: uuid.UUID, sequence: int, payload: bytes) -> bytes:
    header = struct.pack(
        AUDIO_FRAME_STRUCT_FORMAT,
        AUDIO_FRAME_MAGIC,
        PROTOCOL_VERSION,
        0,
        AUDIO_FRAME_HEADER_LENGTH,
        stream_id.bytes,
        sequence,
        123456789,
        16000,
        1,
        AUDIO_CODEC_OPUS,
        20,
        len(payload),
    )
    return header + payload


def test_protocol_messages() -> None:
    envelope = build_envelope(
        message_type="hello_ack",
        device_id="node_A01",
        payload={"connection_id": "abc"},
    )
    assert envelope["protocol_version"] == PROTOCOL_VERSION

    node_hello = {
        "protocol_version": PROTOCOL_VERSION,
        "message_type": "hello",
        "device_id": "node_A01",
        "message_id": "m1",
        "sent_at_ms": 1,
        "payload": {"app_version": "test"},
    }
    parsed = parse_node_message(json.dumps(node_hello), expected_device_id="node_A01")
    assert parsed.message_type == "hello"

    try:
        parse_node_message({**node_hello, "message_type": "bad"}, "node_A01")
    except ProtocolError:
        pass
    else:
        raise AssertionError("invalid message_type should fail")


def test_audio_frame_and_manager() -> None:
    manager = AudioStreamManager(max_buffer_frames=2)
    stream_id = uuid.uuid4()
    manager.start_session(
        device_id="node_A01",
        stream_id=str(stream_id),
        stream_token="secret",
        subscriber_token="monitor-secret",
    )
    assert manager.validate_session_token(
        device_id="node_A01",
        stream_id=str(stream_id),
        stream_token="secret",
    )
    assert not manager.validate_session_token(
        device_id="node_A01",
        stream_id=str(stream_id),
        stream_token="wrong",
    )
    assert manager.validate_subscriber_token(
        stream_id=str(stream_id),
        subscriber_token="monitor-secret",
    )
    assert not manager.validate_subscriber_token(
        stream_id=str(stream_id),
        subscriber_token="wrong",
    )

    subscriber_id, queue, _ = manager.subscribe(
        stream_id=str(stream_id),
        subscriber_token="monitor-secret",
        max_queue_frames=1,
    )
    frame1 = build_audio_frame(stream_id=stream_id, sequence=1, payload=b"abc")
    frame2 = build_audio_frame(stream_id=stream_id, sequence=2, payload=b"def")
    frame4 = build_audio_frame(stream_id=stream_id, sequence=4, payload=b"ghi")

    parsed = parse_audio_frame(frame1)
    assert parsed.stream_id == str(stream_id)
    assert parsed.codec_name == "opus"

    result1 = manager.accept_frame(device_id="node_A01", raw_frame=frame1)
    result2 = manager.accept_frame(device_id="node_A01", raw_frame=frame2)
    result4 = manager.accept_frame(device_id="node_A01", raw_frame=frame4)
    assert result1["accepted"] is True
    assert result2["accepted"] is True
    assert result4["accepted"] is True

    session = manager.list_sessions()[0]
    assert session["received_frames"] == 3
    assert session["sequence_gaps"] == 1
    assert session["dropped_frames"] == 1
    assert session["buffer_depth"] == 2
    assert session["subscribers"] == 1
    assert session["subscriber_dropped_frames"] >= 2
    assert queue.get_nowait() == frame4
    manager.unsubscribe(stream_id=str(stream_id), subscriber_id=subscriber_id)
    assert manager.list_sessions()[0]["subscribers"] == 0

    rejected = manager.accept_frame(device_id="node_A01", raw_frame=b"bad")
    assert rejected["accepted"] is False


async def test_node_manager_async() -> None:
    manager = NodeManager(degraded_after_seconds=10, offline_after_seconds=20)
    ws1 = FakeWebSocket()
    state1 = await manager.register(
        device_id="node_A01",
        websocket=ws1,
        protocol_version=PROTOCOL_VERSION,
        hello_payload={"recording": True, "app_version": "test"},
    )
    assert state1.recording is True
    assert manager.is_connected("node_A01")

    ws2 = FakeWebSocket()
    state2 = await manager.register(
        device_id="node_A01",
        websocket=ws2,
        protocol_version=PROTOCOL_VERSION,
        hello_payload={"recording": False},
    )
    assert state2.generation == state1.generation + 1
    assert ws1.closed is True

    sent = await manager.send_protocol_message(
        device_id="node_A01",
        message_type="ping",
        payload={"ok": True},
    )
    assert sent is True
    assert ws2.sent[-1]["message_type"] == "ping"

    await manager.unregister(
        device_id="node_A01",
        connection_id=state2.connection_id,
        reason="test_done",
    )
    assert not manager.is_connected("node_A01")


def main() -> None:
    test_protocol_messages()
    test_audio_frame_and_manager()
    asyncio.run(test_node_manager_async())
    print("Realtime protocol tests passed")


if __name__ == "__main__":
    main()
