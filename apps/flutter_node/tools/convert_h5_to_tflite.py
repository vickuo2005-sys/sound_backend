"""Convert a Keras .h5 model to TensorFlow Lite.

Default input:
    C:\\Users\\vicku\\Downloads\\best_model.h5

Default output:
    C:\\Users\\vicku\\sound_detector_clean\\assets\\models\\best_model.tflite
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path


DEFAULT_INPUT_MODEL = Path(r"C:\Users\vicku\Downloads\best_model.h5")
DEFAULT_OUTPUT_MODEL = Path(
    r"C:\Users\vicku\sound_detector_clean\assets\models\best_model.tflite"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert a Keras .h5 model to TensorFlow Lite."
    )
    parser.add_argument(
        "--input",
        default=str(DEFAULT_INPUT_MODEL),
        help=f"Input .h5 model path. Default: {DEFAULT_INPUT_MODEL}",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT_MODEL),
        help=f"Output .tflite model path. Default: {DEFAULT_OUTPUT_MODEL}",
    )
    return parser.parse_args()


def load_tensorflow():
    os.environ.setdefault("TF_USE_LEGACY_KERAS", "1")

    try:
        import tensorflow as tf  # type: ignore
    except ImportError:
        print("TensorFlow is not installed.")
        print("Please install it first:")
        print("pip install tensorflow")
        sys.exit(1)

    return tf


def patch_legacy_keras_config(config: object) -> dict[str, int]:
    patched_counts = {
        "batchnorm_axis": 0,
        "depthwise_groups": 0,
    }

    if isinstance(config, dict):
        layer_config = config.get("config")
        if (
            config.get("class_name") == "BatchNormalization"
            and isinstance(layer_config, dict)
            and isinstance(layer_config.get("axis"), list)
            and len(layer_config["axis"]) == 1
        ):
            layer_config["axis"] = layer_config["axis"][0]
            patched_counts["batchnorm_axis"] += 1

        if (
            config.get("class_name") == "DepthwiseConv2D"
            and isinstance(layer_config, dict)
            and "groups" in layer_config
        ):
            del layer_config["groups"]
            patched_counts["depthwise_groups"] += 1

        for value in config.values():
            child_counts = patch_legacy_keras_config(value)
            patched_counts["batchnorm_axis"] += child_counts["batchnorm_axis"]
            patched_counts["depthwise_groups"] += child_counts["depthwise_groups"]

    if isinstance(config, list):
        for item in config:
            child_counts = patch_legacy_keras_config(item)
            patched_counts["batchnorm_axis"] += child_counts["batchnorm_axis"]
            patched_counts["depthwise_groups"] += child_counts["depthwise_groups"]

    return patched_counts


def make_legacy_compatible_h5_copy(input_path: Path) -> Path:
    try:
        import h5py  # type: ignore
    except ImportError:
        print("h5py is required to patch legacy Keras .h5 model configs.")
        print("Please install it first:")
        print("pip install h5py")
        sys.exit(1)

    temp_file = tempfile.NamedTemporaryFile(
        delete=False,
        suffix=".h5",
        prefix="best_model_legacy_compatible_",
    )
    temp_file.close()
    patched_path = Path(temp_file.name)
    shutil.copy2(input_path, patched_path)

    with h5py.File(patched_path, "r+") as h5_file:
        raw_config = h5_file.attrs.get("model_config")
        if raw_config is None:
            print("The .h5 file does not contain a model_config attribute.")
            sys.exit(1)

        if isinstance(raw_config, bytes):
            config_text = raw_config.decode("utf-8")
        elif hasattr(raw_config, "decode"):
            config_text = raw_config.decode("utf-8")
        else:
            config_text = str(raw_config)

        model_config = json.loads(config_text)
        patched_counts = patch_legacy_keras_config(model_config)

        print(
            "patched legacy BatchNormalization axis count: "
            f"{patched_counts['batchnorm_axis']}"
        )
        print(
            "patched legacy DepthwiseConv2D groups count: "
            f"{patched_counts['depthwise_groups']}"
        )

        h5_file.attrs.modify("model_config", json.dumps(model_config))

    return patched_path


def load_keras_model(tf, input_path: Path):
    try:
        return tf.keras.models.load_model(str(input_path), compile=False)
    except TypeError as error:
        error_text = str(error)
        if "BatchNormalization" not in error_text or "axis" not in error_text:
            raise

        print("Detected legacy Keras BatchNormalization axis format.")
        print("Creating a temporary compatible .h5 copy and retrying...")
        patched_path = make_legacy_compatible_h5_copy(input_path)
        try:
            return tf.keras.models.load_model(str(patched_path), compile=False)
        finally:
            patched_path.unlink(missing_ok=True)


def convert_h5_to_tflite(input_path: Path, output_path: Path) -> None:
    if not input_path.exists():
        print(f"Input model not found: {input_path}")
        sys.exit(1)

    tf = load_tensorflow()

    output_path.parent.mkdir(parents=True, exist_ok=True)

    model = load_keras_model(tf, input_path)
    converter = tf.lite.TFLiteConverter.from_keras_model(model)
    tflite_model = converter.convert()

    output_path.write_bytes(tflite_model)

    print(f"input model path: {input_path}")
    print(f"output tflite path: {output_path}")
    print(f"output file size: {output_path.stat().st_size} bytes")


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)

    convert_h5_to_tflite(input_path=input_path, output_path=output_path)


if __name__ == "__main__":
    main()
