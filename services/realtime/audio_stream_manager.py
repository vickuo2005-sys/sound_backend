import asyncio
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from app.protocol import AudioFrameParseError, ParsedAudioFrame, parse_audio_frame


@dataclass
class AudioStreamSession:
    stream_id: str
    device_id: str
    codec: str
    sample_rate_hz: int
    channel_count: int
    frame_duration_ms: int
    stream_token: Optional[str] = None
    subscriber_token: Optional[str] = None
    started_at: float = field(default_factory=time.time)
    last_frame_at: float = field(default_factory=time.time)
    expected_sequence: Optional[int] = None
    received_frames: int = 0
    dropped_frames: int = 0
    sequence_gaps: int = 0
    out_of_order_frames: int = 0
    malformed_frames: int = 0
    bytes_received: int = 0
    subscriber_dropped_frames: int = 0
    subscriber_queues: dict[str, asyncio.Queue[bytes]] = field(default_factory=dict)
    ring_buffer: deque[ParsedAudioFrame] = field(default_factory=deque)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stream_id": self.stream_id,
            "device_id": self.device_id,
            "codec": self.codec,
            "sample_rate_hz": self.sample_rate_hz,
            "channel_count": self.channel_count,
            "frame_duration_ms": self.frame_duration_ms,
            "started_at": datetime.fromtimestamp(
                self.started_at,
                tz=timezone.utc,
            ).isoformat(),
            "last_frame_at": datetime.fromtimestamp(
                self.last_frame_at,
                tz=timezone.utc,
            ).isoformat(),
            "expected_sequence": self.expected_sequence,
            "received_frames": self.received_frames,
            "dropped_frames": self.dropped_frames,
            "sequence_gaps": self.sequence_gaps,
            "out_of_order_frames": self.out_of_order_frames,
            "malformed_frames": self.malformed_frames,
            "bytes_received": self.bytes_received,
            "subscribers": len(self.subscriber_queues),
            "subscriber_dropped_frames": self.subscriber_dropped_frames,
            "buffer_depth": len(self.ring_buffer),
            "age_seconds": round(max(0.0, time.time() - self.started_at), 3),
        }


class AudioStreamManager:
    def __init__(self, *, max_buffer_frames: int = 500) -> None:
        self.max_buffer_frames = max_buffer_frames
        self.sessions: dict[str, AudioStreamSession] = {}
        self.malformed_frame_count = 0

    def start_session(
        self,
        *,
        device_id: str,
        stream_id: Optional[str] = None,
        stream_token: Optional[str] = None,
        subscriber_token: Optional[str] = None,
    ) -> str:
        stream_id = stream_id or str(uuid.uuid4())
        if stream_id not in self.sessions:
            self.sessions[stream_id] = AudioStreamSession(
                stream_id=stream_id,
                device_id=device_id,
                stream_token=stream_token,
                subscriber_token=subscriber_token,
                codec="unknown",
                sample_rate_hz=0,
                channel_count=0,
                frame_duration_ms=0,
            )
        elif stream_token:
            self.sessions[stream_id].stream_token = stream_token
        if subscriber_token:
            self.sessions[stream_id].subscriber_token = subscriber_token
        return stream_id

    def validate_session_token(
        self,
        *,
        stream_id: str,
        device_id: str,
        stream_token: Optional[str],
    ) -> bool:
        session = self.sessions.get(stream_id)
        if session is None:
            return False
        if session.device_id != device_id:
            return False
        if session.stream_token is None:
            return True
        return bool(stream_token) and stream_token == session.stream_token

    def validate_subscriber_token(
        self,
        *,
        stream_id: str,
        subscriber_token: Optional[str],
    ) -> bool:
        session = self.sessions.get(stream_id)
        if session is None:
            return False
        if session.subscriber_token is None:
            return True
        return bool(subscriber_token) and subscriber_token == session.subscriber_token

    def subscribe(
        self,
        *,
        stream_id: str,
        subscriber_token: Optional[str],
        max_queue_frames: int = 100,
    ) -> tuple[str, asyncio.Queue[bytes], dict[str, Any]]:
        if not self.validate_subscriber_token(
            stream_id=stream_id,
            subscriber_token=subscriber_token,
        ):
            raise ValueError("invalid live audio subscriber token")

        session = self.sessions.get(stream_id)
        if session is None:
            raise ValueError("stream session not found")

        subscriber_id = str(uuid.uuid4())
        queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=max(1, max_queue_frames))
        session.subscriber_queues[subscriber_id] = queue
        return subscriber_id, queue, session.to_dict()

    def unsubscribe(self, *, stream_id: str, subscriber_id: str) -> None:
        session = self.sessions.get(stream_id)
        if session is None:
            return
        session.subscriber_queues.pop(subscriber_id, None)

    def stop_session(self, stream_id: str) -> Optional[dict[str, Any]]:
        session = self.sessions.pop(stream_id, None)
        return session.to_dict() if session else None

    def accept_frame(self, *, device_id: str, raw_frame: bytes) -> dict[str, Any]:
        try:
            frame = parse_audio_frame(raw_frame)
        except AudioFrameParseError as exc:
            self.malformed_frame_count += 1
            return {
                "accepted": False,
                "reason": str(exc),
                "malformed_frame_count": self.malformed_frame_count,
            }

        session = self.sessions.get(frame.stream_id)
        if session is None:
            session = AudioStreamSession(
                stream_id=frame.stream_id,
                device_id=device_id,
                codec=frame.codec_name,
                sample_rate_hz=frame.sample_rate_hz,
                channel_count=frame.channel_count,
                frame_duration_ms=frame.frame_duration_ms,
            )
            self.sessions[frame.stream_id] = session

        session.codec = frame.codec_name
        session.sample_rate_hz = frame.sample_rate_hz
        session.channel_count = frame.channel_count
        session.frame_duration_ms = frame.frame_duration_ms
        session.last_frame_at = time.time()
        session.received_frames += 1
        session.bytes_received += len(frame.payload)

        if session.expected_sequence is None:
            session.expected_sequence = frame.sequence_number + 1
        elif frame.sequence_number == session.expected_sequence:
            session.expected_sequence += 1
        elif frame.sequence_number > session.expected_sequence:
            session.sequence_gaps += frame.sequence_number - session.expected_sequence
            session.expected_sequence = frame.sequence_number + 1
        else:
            session.out_of_order_frames += 1

        if len(session.ring_buffer) >= self.max_buffer_frames:
            session.ring_buffer.popleft()
            session.dropped_frames += 1
        session.ring_buffer.append(frame)

        for queue in list(session.subscriber_queues.values()):
            try:
                queue.put_nowait(bytes(raw_frame))
            except asyncio.QueueFull:
                session.subscriber_dropped_frames += 1
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                try:
                    queue.put_nowait(bytes(raw_frame))
                except asyncio.QueueFull:
                    session.subscriber_dropped_frames += 1

        return {
            "accepted": True,
            "frame": {
                "stream_id": frame.stream_id,
                "sequence_number": frame.sequence_number,
                "capture_timestamp_us": frame.capture_timestamp_us,
                "codec": frame.codec_name,
                "payload_length": len(frame.payload),
            },
            "session": session.to_dict(),
        }

    def list_sessions(self) -> list[dict[str, Any]]:
        return [
            session.to_dict()
            for session in sorted(
                self.sessions.values(),
                key=lambda item: item.started_at,
                reverse=True,
            )
        ]
