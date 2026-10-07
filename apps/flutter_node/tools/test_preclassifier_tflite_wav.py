#!/usr/bin/env python3
"""Run a WAV file through preclassifier_mobile.tflite.

The preprocessing mirrors realtime_audio_preclassifier_gui_05s.py:

    WAV -> mono -> 16000 Hz -> 3 seconds -> MelSpectrogram
    -> AmplitudeToDB(top_db=80) -> target_frames=256
    -> per-sample mean/std normalization -> TFLite logits -> softmax
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
import wave
from pathlib import Path
from typing import Any


DEFAULT_MODEL = Path(
    r"C:\Users\vicku\sound_detector_clean\assets\models\preclassifier_mobile.tflite"
)
DEFAULT_LABELS = Path(
    r"C:\Users\vicku\sound_detector_clean\assets\models\preclassifier_labels.json"
)


def require_modules() -> dict[str, Any]:
    missing: list[str] = []
    modules: dict[str, Any] = {}

    for name in ("numpy",):
        try:
            modules[name] = __import__(name)
        except ModuleNotFoundError:
            missing.append(name)

    try:
        import tensorflow as tf  # type: ignore

        modules["interpreter_factory"] = lambda model_path: tf.lite.Interpreter(
            model_path=str(model_path)
        )
    except ModuleNotFoundError:
        try:
            from ai_edge_litert.interpreter import Interpreter  # type: ignore

            modules["interpreter_factory"] = lambda model_path: Interpreter(
                model_path=str(model_path)
            )
        except ModuleNotFoundError:
            try:
                from tflite_runtime.interpreter import Interpreter  # type: ignore

                modules["interpreter_factory"] = lambda model_path: Interpreter(
                    model_path=str(model_path)
                )
            except ModuleNotFoundError:
                missing.append("tensorflow, ai-edge-litert, or tflite-runtime")

    if missing:
        print("Missing Python packages:")
        for name in missing:
            print(f"  - {name}")
        print()
        print("Install test dependencies, for example:")
        print("  pip install numpy ai-edge-litert")
        sys.exit(1)

    return modules


def load_labels(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "class_values": [0, 1],
            "labels": {"0": "non_aircraft", "1": "aircraft"},
            "positive_class_value": 1,
            "positive_class_index": 1,
            "threshold": 0.60,
        }

    return json.loads(path.read_text(encoding="utf-8"))


def softmax(logits: np.ndarray) -> np.ndarray:
    import numpy as np

    values = logits.astype(np.float64)
    values = values - np.max(values)
    exp_values = np.exp(values)
    return exp_values / np.sum(exp_values)


def preprocess_wav(
    wav_path: Path,
    labels: dict[str, Any],
    modules: dict[str, Any],
) -> np.ndarray:
    import numpy as np

    params = labels.get("preprocessing", {})
    sample_rate = int(params.get("sample_rate", 16000))
    audio_sec = float(params.get("audio_sec", 3.0))
    target_samples = int(round(sample_rate * audio_sec))
    n_fft = int(params.get("n_fft", 1024))
    win_length = int(params.get("win_length", 1024))
    hop_length = int(params.get("hop_length", 320))
    n_mels = int(params.get("n_mels", 128))
    f_min = float(params.get("f_min", 20.0))
    f_max = params.get("f_max", None)
    target_frames = int(params.get("target_frames", 256))

    samples, source_sample_rate = read_wav_mono(wav_path)

    if int(source_sample_rate) != sample_rate:
        samples = resample_linear(samples, int(source_sample_rate), sample_rate)

    current_samples = len(samples)
    if current_samples < target_samples:
        padded = np.zeros(target_samples, dtype=np.float32)
        padded[:current_samples] = samples
        samples = padded
    elif current_samples > target_samples:
        start = (current_samples - target_samples) // 2
        samples = samples[start : start + target_samples]

    mel = mel_spectrogram(
        samples,
        sample_rate=sample_rate,
        n_fft=n_fft,
        win_length=win_length,
        hop_length=hop_length,
        n_mels=n_mels,
        f_min=f_min,
        f_max=float(f_max) if f_max is not None else sample_rate / 2,
    )
    mel = power_to_db(mel, top_db=80.0)
    mel = resize_time_frames(mel, target_frames)

    mean = float(np.mean(mel))
    std = max(float(np.std(mel)), 1e-5)
    mel = (mel - mean) / std

    return mel.astype(np.float32)


def read_wav_mono(wav_path: Path):
    import numpy as np

    with wave.open(str(wav_path), "rb") as wav:
        channels = wav.getnchannels()
        sample_rate = wav.getframerate()
        sample_width = wav.getsampwidth()
        frame_count = wav.getnframes()
        raw = wav.readframes(frame_count)

    if sample_width == 1:
        data = np.frombuffer(raw, dtype=np.uint8).astype(np.float32)
        data = (data - 128.0) / 128.0
    elif sample_width == 2:
        data = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    elif sample_width == 3:
        bytes_arr = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3)
        values = (
            bytes_arr[:, 0].astype(np.int32)
            | (bytes_arr[:, 1].astype(np.int32) << 8)
            | (bytes_arr[:, 2].astype(np.int32) << 16)
        )
        values = np.where(values & 0x800000, values | ~0xFFFFFF, values)
        data = values.astype(np.float32) / 8388608.0
    elif sample_width == 4:
        data = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
    else:
        raise ValueError(f"Unsupported WAV sample width: {sample_width}")

    if channels > 1:
        data = data.reshape(-1, channels).mean(axis=1)

    return data.astype(np.float32), sample_rate


def resample_linear(samples, source_rate: int, target_rate: int):
    import numpy as np

    if source_rate == target_rate:
        return samples.astype(np.float32)

    output_length = max(1, int(round(len(samples) * target_rate / source_rate)))
    source_positions = np.arange(output_length, dtype=np.float64) * source_rate / target_rate
    left = np.floor(source_positions).astype(np.int64)
    right = np.minimum(left + 1, len(samples) - 1)
    fraction = source_positions - left
    output = samples[left] * (1.0 - fraction) + samples[right] * fraction
    return output.astype(np.float32)


def reflect_pad(samples, pad: int):
    import numpy as np

    if pad <= 0:
        return samples
    if len(samples) <= 1:
        return np.pad(samples, (pad, pad), mode="constant")
    return np.pad(samples, (pad, pad), mode="reflect")


def hz_to_mel(hz: float) -> float:
    return 2595.0 * math.log10(1.0 + hz / 700.0)


def mel_to_hz(mel: float) -> float:
    return 700.0 * (10.0 ** (mel / 2595.0) - 1.0)


def mel_filter_bank(
    sample_rate: int,
    n_fft: int,
    n_mels: int,
    f_min: float,
    f_max: float,
):
    import numpy as np

    fft_bins = n_fft // 2 + 1
    mel_points = np.linspace(hz_to_mel(f_min), hz_to_mel(f_max), n_mels + 2)
    hz_points = np.array([mel_to_hz(value) for value in mel_points])
    bin_points = np.floor((n_fft + 1) * hz_points / sample_rate).astype(int)
    bin_points = np.clip(bin_points, 0, fft_bins - 1)
    filters = np.zeros((n_mels, fft_bins), dtype=np.float32)

    for mel in range(n_mels):
        left, center, right = bin_points[mel], bin_points[mel + 1], bin_points[mel + 2]
        if center > left:
            filters[mel, left:center] = (
                np.arange(left, center, dtype=np.float32) - left
            ) / max(1, center - left)
        if right > center:
            filters[mel, center:right] = (
                right - np.arange(center, right, dtype=np.float32)
            ) / max(1, right - center)

    return filters


def mel_spectrogram(
    samples,
    *,
    sample_rate: int,
    n_fft: int,
    win_length: int,
    hop_length: int,
    n_mels: int,
    f_min: float,
    f_max: float,
):
    import numpy as np

    window = np.hanning(win_length).astype(np.float32)
    if win_length < n_fft:
        full_window = np.zeros(n_fft, dtype=np.float32)
        full_window[:win_length] = window
        window = full_window

    padded = reflect_pad(samples.astype(np.float32), n_fft // 2)
    frame_count = max(1, 1 + (len(padded) - n_fft) // hop_length)
    filters = mel_filter_bank(sample_rate, n_fft, n_mels, f_min, f_max)
    mel = np.zeros((n_mels, frame_count), dtype=np.float32)

    for frame in range(frame_count):
        start = frame * hop_length
        chunk = padded[start : start + n_fft]
        if len(chunk) < n_fft:
            chunk = np.pad(chunk, (0, n_fft - len(chunk)))
        power = np.abs(np.fft.rfft(chunk * window, n=n_fft)) ** 2
        mel[:, frame] = filters @ power.astype(np.float32)

    return mel


def power_to_db(mel, top_db: float):
    import numpy as np

    db = 10.0 * np.log10(np.maximum(mel, 1e-10))
    max_db = float(np.max(db))
    return np.maximum(db, max_db - top_db).astype(np.float32)


def resize_time_frames(mel, target_frames: int):
    import numpy as np

    source_frames = mel.shape[1]
    if source_frames == target_frames:
        return mel.astype(np.float32)

    old_positions = np.arange(source_frames, dtype=np.float32)
    new_positions = np.linspace(0, source_frames - 1, target_frames, dtype=np.float32)
    resized = np.zeros((mel.shape[0], target_frames), dtype=np.float32)

    for row in range(mel.shape[0]):
        resized[row] = np.interp(new_positions, old_positions, mel[row])

    return resized


def make_input_tensor(mel: np.ndarray, input_shape: list[int]) -> np.ndarray:
    import numpy as np

    if len(input_shape) != 4:
        raise ValueError(f"Unsupported input rank: {input_shape}")

    if input_shape[1:] == [1, mel.shape[0], mel.shape[1]]:
        return mel[np.newaxis, np.newaxis, :, :].astype(np.float32)

    if input_shape[1:] == [mel.shape[0], mel.shape[1], 1]:
        return mel[np.newaxis, :, :, np.newaxis].astype(np.float32)

    raise ValueError(
        f"Unsupported input shape {input_shape}; expected NCHW [1,1,{mel.shape[0]},{mel.shape[1]}] "
        f"or NHWC [1,{mel.shape[0]},{mel.shape[1]},1]."
    )


def run_one(model_path: Path, labels_path: Path, wav_path: Path) -> dict[str, Any]:
    import numpy as np

    modules = require_modules()
    labels = load_labels(labels_path)

    interpreter = modules["interpreter_factory"](model_path)
    interpreter.allocate_tensors()
    input_details = interpreter.get_input_details()
    output_details = interpreter.get_output_details()

    mel = preprocess_wav(wav_path, labels, modules)
    input_shape = input_details[0]["shape"].tolist()
    input_tensor = make_input_tensor(mel, input_shape)

    start = time.perf_counter()
    interpreter.set_tensor(input_details[0]["index"], input_tensor)
    interpreter.invoke()
    raw_output = interpreter.get_tensor(output_details[0]["index"])
    elapsed_ms = (time.perf_counter() - start) * 1000.0

    logits = raw_output.reshape(-1).astype(np.float32)
    probabilities = softmax(logits)
    predicted_index = int(np.argmax(probabilities))

    class_values = [int(value) for value in labels.get("class_values", [0, 1])]
    class_value = class_values[predicted_index]
    label_map = labels.get("labels", {"0": "non_aircraft", "1": "aircraft"})
    predicted_label = label_map.get(str(class_value), f"class_{class_value}")

    positive_index = int(labels.get("positive_class_index", 1))
    threshold = float(labels.get("threshold", 0.60))
    aircraft_probability = float(probabilities[positive_index])
    label = "aircraft" if aircraft_probability > threshold else "non_aircraft"
    confidence = float(np.max(probabilities))

    return {
        "wav": str(wav_path),
        "input_shape": input_shape,
        "input_dtype": str(input_details[0]["dtype"]),
        "output_shape": output_details[0]["shape"].tolist(),
        "output_dtype": str(output_details[0]["dtype"]),
        "raw_logits": logits.tolist(),
        "softmax": probabilities.tolist(),
        "predicted_index": predicted_index,
        "predicted_class_value": class_value,
        "predicted_checkpoint_label": predicted_label,
        "label": label,
        "aircraft_probability": aircraft_probability,
        "confidence": confidence,
        "threshold": threshold,
        "inference_time_ms": elapsed_ms,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Test preclassifier_mobile.tflite with one WAV file."
    )
    parser.add_argument("wav", type=Path)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS)
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if not args.model.exists():
        print(f"TFLite model not found: {args.model}")
        return 2

    if not args.wav.exists():
        print(f"WAV file not found: {args.wav}")
        return 2

    result = run_one(args.model, args.labels, args.wav)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
