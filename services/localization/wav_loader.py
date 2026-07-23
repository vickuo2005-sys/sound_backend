import io
import wave
from dataclasses import dataclass

import numpy as np


@dataclass
class WavPcm:
    sample_rate_hz: int
    channel_count: int
    samples: np.ndarray


def load_pcm_wav_bytes(data: bytes) -> WavPcm:
    with wave.open(io.BytesIO(data), "rb") as reader:
        channel_count = reader.getnchannels()
        sample_width = reader.getsampwidth()
        sample_rate_hz = reader.getframerate()
        frame_count = reader.getnframes()
        raw = reader.readframes(frame_count)

    if sample_width != 2:
        raise ValueError("Only 16-bit PCM WAV is supported")
    if channel_count < 1:
        raise ValueError("WAV channel count must be positive")
    if sample_rate_hz <= 0:
        raise ValueError("WAV sample rate must be positive")

    samples = np.frombuffer(raw, dtype="<i2").astype(np.float32)
    if channel_count > 1:
        samples = samples.reshape(-1, channel_count).mean(axis=1)
    samples /= 32768.0
    return WavPcm(
        sample_rate_hz=sample_rate_hz,
        channel_count=channel_count,
        samples=samples,
    )
