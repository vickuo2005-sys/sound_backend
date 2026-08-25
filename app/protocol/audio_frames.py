import struct
import uuid
from dataclasses import dataclass

from .protocol_constants import (
    AUDIO_CODEC_NAMES,
    AUDIO_FRAME_HEADER_LENGTH,
    AUDIO_FRAME_MAGIC,
    AUDIO_FRAME_STRUCT_FORMAT,
    MAX_AUDIO_FRAME_BYTES,
    PROTOCOL_VERSION,
)


class AudioFrameParseError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedAudioFrame:
    stream_id: str
    sequence_number: int
    capture_timestamp_us: int
    sample_rate_hz: int
    channel_count: int
    codec_id: int
    codec_name: str
    frame_duration_ms: int
    flags: int
    payload: bytes


def parse_audio_frame(frame: bytes) -> ParsedAudioFrame:
    if not isinstance(frame, (bytes, bytearray)):
        raise AudioFrameParseError("Audio frame must be bytes")
    if len(frame) < AUDIO_FRAME_HEADER_LENGTH:
        raise AudioFrameParseError("Audio frame is shorter than header")
    if len(frame) > MAX_AUDIO_FRAME_BYTES:
        raise AudioFrameParseError("Audio frame exceeds maximum size")

    try:
        (
            magic,
            protocol_version,
            flags,
            header_length,
            stream_id_bytes,
            sequence_number,
            capture_timestamp_us,
            sample_rate_hz,
            channel_count,
            codec_id,
            frame_duration_ms,
            payload_length,
        ) = struct.unpack(
            AUDIO_FRAME_STRUCT_FORMAT,
            frame[:AUDIO_FRAME_HEADER_LENGTH],
        )
    except struct.error as exc:
        raise AudioFrameParseError("Audio frame header is malformed") from exc

    if magic != AUDIO_FRAME_MAGIC:
        raise AudioFrameParseError("Audio frame magic mismatch")
    if protocol_version != PROTOCOL_VERSION:
        raise AudioFrameParseError("Unsupported audio frame protocol version")
    if header_length != AUDIO_FRAME_HEADER_LENGTH:
        raise AudioFrameParseError("Unexpected audio frame header length")
    if codec_id not in AUDIO_CODEC_NAMES:
        raise AudioFrameParseError("Unsupported audio codec")
    if sample_rate_hz <= 0:
        raise AudioFrameParseError("Invalid sample rate")
    if channel_count not in {1, 2}:
        raise AudioFrameParseError("Invalid channel count")
    if frame_duration_ms <= 0 or frame_duration_ms > 1000:
        raise AudioFrameParseError("Invalid frame duration")

    expected_length = header_length + payload_length
    if expected_length != len(frame):
        raise AudioFrameParseError("Payload length does not match frame size")

    stream_id = str(uuid.UUID(bytes=bytes(stream_id_bytes)))
    payload = bytes(frame[header_length:])

    return ParsedAudioFrame(
        stream_id=stream_id,
        sequence_number=sequence_number,
        capture_timestamp_us=capture_timestamp_us,
        sample_rate_hz=sample_rate_hz,
        channel_count=channel_count,
        codec_id=codec_id,
        codec_name=AUDIO_CODEC_NAMES[codec_id],
        frame_duration_ms=frame_duration_ms,
        flags=flags,
        payload=payload,
    )
