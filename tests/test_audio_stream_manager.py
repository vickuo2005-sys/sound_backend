import struct
import uuid

from app.protocol import (
    AUDIO_FRAME_HEADER_LENGTH,
    AUDIO_FRAME_MAGIC,
    PROTOCOL_VERSION,
)
from app.protocol.protocol_constants import AUDIO_CODEC_PCM16, AUDIO_FRAME_STRUCT_FORMAT
from services.realtime import AudioStreamManager


def build_pcm_frame(stream_id: uuid.UUID, sequence: int, payload: bytes) -> bytes:
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
        AUDIO_CODEC_PCM16,
        20,
        len(payload),
    )
    return header + payload


def test_live_audio_subscriber_receives_binary_frames() -> None:
    manager = AudioStreamManager(max_buffer_frames=5)
    stream_id = uuid.uuid4()
    manager.start_session(
        device_id="node_A01",
        stream_id=str(stream_id),
        stream_token="node-secret",
        subscriber_token="dashboard-secret",
    )

    subscriber_id, queue, session = manager.subscribe(
        stream_id=str(stream_id),
        subscriber_token="dashboard-secret",
        max_queue_frames=2,
    )

    assert session["subscribers"] == 1
    frame = build_pcm_frame(stream_id, 1, b"\x01\x00\x02\x00")
    result = manager.accept_frame(device_id="node_A01", raw_frame=frame)

    assert result["accepted"] is True
    assert queue.get_nowait() == frame

    manager.unsubscribe(stream_id=str(stream_id), subscriber_id=subscriber_id)
    assert manager.list_sessions()[0]["subscribers"] == 0
