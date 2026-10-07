"""Run a WAV file through the Sound Detector TensorFlow Lite model.

This mirrors the training preprocessing:
WAV -> 16 kHz mono -> mel spectrogram -> magma RGB image -> 224x224 -> /255.
"""

from __future__ import annotations

import argparse
import os
import sys
from io import BytesIO
from pathlib import Path


DEFAULT_MODEL_PATH = Path(
    r"C:\Users\vicku\sound_detector_clean\assets\models\best_model.tflite"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Test a WAV file with the TensorFlow Lite sound model."
    )
    parser.add_argument(
        "--wav",
        required=True,
        help="Path to the WAV file to test.",
    )
    parser.add_argument(
        "--model",
        default=str(DEFAULT_MODEL_PATH),
        help=f"Path to .tflite model. Default: {DEFAULT_MODEL_PATH}",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.5,
        help="Sigmoid threshold for class 1. Default: 0.5",
    )
    parser.add_argument(
        "--save-spectrogram",
        default="",
        help="Optional path to save the generated 224x224 spectrogram PNG.",
    )
    return parser.parse_args()


def load_dependencies():
    try:
        import librosa  # type: ignore
        import librosa.display  # type: ignore
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt  # type: ignore
        import numpy as np  # type: ignore
        import tensorflow as tf  # type: ignore
        from PIL import Image  # type: ignore
    except ImportError as error:
        print(f"Missing Python package: {error.name}")
        print("Please install required packages:")
        print("pip install tensorflow librosa matplotlib pillow soundfile")
        sys.exit(1)

    return librosa, plt, np, tf, Image


def wav_to_model_input(wav_path: Path, save_spectrogram_path: Path | None):
    librosa, plt, np, _tf, Image = load_dependencies()

    waveform, sample_rate = librosa.load(
        str(wav_path),
        sr=16000,
        mono=True,
    )

    mel_spec = librosa.feature.melspectrogram(
        y=waveform,
        sr=sample_rate,
        n_mels=128,
    )
    mel_spec_db = librosa.power_to_db(
        mel_spec,
        ref=np.max,
    )

    figure = plt.figure(figsize=(2.24, 2.24), dpi=100)
    librosa.display.specshow(
        mel_spec_db,
        sr=sample_rate,
        cmap="magma",
    )
    plt.axis("off")
    plt.tight_layout(pad=0)

    image_buffer = BytesIO()
    figure.savefig(
        image_buffer,
        format="png",
        bbox_inches="tight",
        pad_inches=0,
    )
    plt.close(figure)
    image_buffer.seek(0)

    image = Image.open(image_buffer).convert("RGB").resize((224, 224))
    if save_spectrogram_path is not None:
        save_spectrogram_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(save_spectrogram_path)

    image_array = np.asarray(image, dtype=np.float32) / 255.0
    model_input = np.expand_dims(image_array, axis=0)
    return model_input, len(waveform), sample_rate


def run_tflite(model_path: Path, model_input):
    _librosa, _plt, _np, tf, _Image = load_dependencies()

    interpreter = tf.lite.Interpreter(model_path=str(model_path))
    interpreter.allocate_tensors()

    input_details = interpreter.get_input_details()
    output_details = interpreter.get_output_details()

    interpreter.set_tensor(input_details[0]["index"], model_input)
    interpreter.invoke()

    output = interpreter.get_tensor(output_details[0]["index"])
    return input_details, output_details, output


def main() -> None:
    args = parse_args()
    wav_path = Path(args.wav)
    model_path = Path(args.model)
    save_spectrogram_path = (
        Path(args.save_spectrogram) if args.save_spectrogram else None
    )

    if not wav_path.exists():
        print(f"WAV file not found: {wav_path}")
        sys.exit(1)

    if not model_path.exists():
        print(f"TFLite model not found: {model_path}")
        sys.exit(1)

    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

    model_input, waveform_length, sample_rate = wav_to_model_input(
        wav_path=wav_path,
        save_spectrogram_path=save_spectrogram_path,
    )
    input_details, output_details, output = run_tflite(
        model_path=model_path,
        model_input=model_input,
    )

    score = float(output.flatten()[0])
    predicted_class = 1 if score > args.threshold else 0

    print(f"wav path: {wav_path}")
    print(f"model path: {model_path}")
    print(f"sample rate: {sample_rate}")
    print(f"waveform samples: {waveform_length}")
    print(f"model input shape: {model_input.shape}")
    print(f"tflite input: {input_details[0]['shape']} {input_details[0]['dtype']}")
    print(f"tflite output: {output_details[0]['shape']} {output_details[0]['dtype']}")
    print(f"score: {score:.6f}")
    print(f"threshold: {args.threshold}")
    print(f"predicted class: {predicted_class}")
    print(f"label hint: {'class_1 / aircraft' if predicted_class == 1 else 'class_0'}")

    if save_spectrogram_path is not None:
        print(f"spectrogram image: {save_spectrogram_path}")


if __name__ == "__main__":
    main()
