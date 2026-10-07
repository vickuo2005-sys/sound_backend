#!/usr/bin/env python3
"""Convert the PyTorch audio preclassifier checkpoint to TensorFlow Lite.

Default input:
    C:\\Users\\vicku\\Downloads\\preclassifier_best.pt

Default output:
    C:\\Users\\vicku\\sound_detector_clean\\assets\\models\\preclassifier_mobile.tflite

This script mirrors the model architecture in
`realtime_audio_preclassifier_gui_05s.py`:

    input  : [1, 1, 128, 256] float32 mel spectrogram
    output : [1, 2] float32 logits

It exports PyTorch -> ONNX -> TensorFlow SavedModel -> TFLite.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


DEFAULT_CHECKPOINT = Path(r"C:\Users\vicku\Downloads\preclassifier_best.pt")
DEFAULT_OUTPUT = Path(
    r"C:\Users\vicku\sound_detector_clean\assets\models\preclassifier_mobile.tflite"
)
DEFAULT_LABELS = Path(
    r"C:\Users\vicku\sound_detector_clean\assets\models\preclassifier_labels.json"
)
DEFAULT_REPORT = Path(
    r"C:\Users\vicku\sound_detector_clean\outputs\model_check\preclassifier_tflite_report.md"
)


def require_modules() -> dict[str, Any]:
    missing: list[str] = []
    modules: dict[str, Any] = {}

    for name in ("torch", "torchvision", "onnx", "tensorflow"):
        try:
            modules[name] = __import__(name)
        except ModuleNotFoundError:
            missing.append(name)

    try:
        import onnx_tf.backend as onnx_tf_backend  # type: ignore

        modules["onnx_tf_backend"] = onnx_tf_backend
    except ModuleNotFoundError:
        missing.append("onnx-tf")

    if missing:
        print("Missing Python packages:")
        for name in missing:
            print(f"  - {name}")
        print()
        print("Install the conversion dependencies, for example:")
        print(
            "  pip install torch torchvision onnx onnx-tf tensorflow"
        )
        print()
        print(
            "Note: if TensorFlow is not available for your Python version on "
            "Windows, use a Python version supported by TensorFlow."
        )
        sys.exit(1)

    return modules


def build_model_classes(torch: Any, torchvision: Any):
    nn = torch.nn
    mobilenet_v2 = torchvision.models.mobilenet_v2

    class AudioMobileNetV2(nn.Module):
        def __init__(self, embedding_dim: int = 128):
            super().__init__()
            net = mobilenet_v2(weights=None)

            first = net.features[0][0]
            net.features[0][0] = nn.Conv2d(
                in_channels=1,
                out_channels=first.out_channels,
                kernel_size=first.kernel_size,
                stride=first.stride,
                padding=first.padding,
                bias=False,
            )

            self.features = net.features
            self.pool = nn.AdaptiveAvgPool2d((1, 1))
            self.embedding_dim = int(embedding_dim)
            self.embedding = nn.Sequential(
                nn.Linear(1280, embedding_dim, bias=False),
                nn.BatchNorm1d(embedding_dim),
            )

        def forward(self, x):
            x = self.features(x)
            x = self.pool(x).flatten(1)
            return self.embedding(x)

    class AudioClassifier(nn.Module):
        def __init__(self, backbone: AudioMobileNetV2, num_classes: int):
            super().__init__()
            self.backbone = backbone
            self.classifier = nn.Linear(backbone.embedding_dim, num_classes)

        def forward(self, x):
            return self.classifier(self.backbone(x))

    return AudioMobileNetV2, AudioClassifier


def as_serializable_args(args: Any) -> dict[str, Any]:
    if args is None:
        return {}
    if isinstance(args, dict):
        return dict(args)
    if hasattr(args, "__dict__"):
        return dict(vars(args))
    return {}


def load_checkpoint_model(checkpoint_path: Path, modules: dict[str, Any]):
    torch = modules["torch"]
    torchvision = modules["torchvision"]
    AudioMobileNetV2, AudioClassifier = build_model_classes(torch, torchvision)

    checkpoint = torch.load(
        checkpoint_path,
        map_location="cpu",
        weights_only=False,
    )

    if "model" not in checkpoint:
        raise RuntimeError(
            "Checkpoint does not contain key 'model'. "
            "Please use preclassifier_best.pt."
        )

    saved_args = as_serializable_args(checkpoint.get("args", {}))
    class_values = checkpoint.get("class_values", [0, 1])
    class_values = [int(value) for value in class_values]

    embedding_dim = int(saved_args.get("embedding_dim", 128))
    backbone = AudioMobileNetV2(embedding_dim=embedding_dim)
    model = AudioClassifier(backbone=backbone, num_classes=len(class_values))
    model.load_state_dict(checkpoint["model"])
    model.eval()

    return model, class_values, saved_args


def write_labels(labels_path: Path, class_values: list[int], saved_args: dict[str, Any]):
    labels_path.parent.mkdir(parents=True, exist_ok=True)

    positive_class_value = 1 if 1 in class_values else class_values[-1]
    positive_class_index = class_values.index(positive_class_value)

    labels = {
        "class_values": class_values,
        "labels": {
            str(value): "aircraft" if value == positive_class_value else "non_aircraft"
            for value in class_values
        },
        "positive_class_value": positive_class_value,
        "positive_class_index": positive_class_index,
        "threshold": 0.60,
        "note": (
            "Class mapping is inferred from class_values. Confirm with the "
            "training dataset before formal deployment."
        ),
        "preprocessing": {
            "sample_rate": int(saved_args.get("sample_rate", 16000)),
            "audio_sec": float(saved_args.get("audio_sec", 3.0)),
            "n_fft": int(saved_args.get("n_fft", 1024)),
            "win_length": int(saved_args.get("win_length", 1024)),
            "hop_length": int(saved_args.get("hop_length", 320)),
            "n_mels": int(saved_args.get("n_mels", 128)),
            "f_min": float(saved_args.get("f_min", 20.0)),
            "f_max": saved_args.get("f_max", None),
            "target_frames": int(saved_args.get("target_frames", 256)),
            "top_db": 80,
            "normalize": "per_sample_mean_std",
        },
    }

    labels_path.write_text(
        json.dumps(labels, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return labels


def inspect_tflite(tflite_path: Path, modules: dict[str, Any]) -> dict[str, Any]:
    tf = modules["tensorflow"]
    interpreter = tf.lite.Interpreter(model_path=str(tflite_path))
    interpreter.allocate_tensors()
    input_details = interpreter.get_input_details()
    output_details = interpreter.get_output_details()

    return {
        "inputs": [
            {
                "name": item.get("name"),
                "shape": item.get("shape").tolist(),
                "dtype": str(item.get("dtype")),
            }
            for item in input_details
        ],
        "outputs": [
            {
                "name": item.get("name"),
                "shape": item.get("shape").tolist(),
                "dtype": str(item.get("dtype")),
            }
            for item in output_details
        ],
    }


def write_report(
    report_path: Path,
    checkpoint_path: Path,
    output_path: Path,
    labels_path: Path,
    labels: dict[str, Any],
    tflite_info: dict[str, Any],
):
    report_path.parent.mkdir(parents=True, exist_ok=True)
    size_bytes = output_path.stat().st_size if output_path.exists() else 0

    lines = [
        "# Preclassifier TFLite Report",
        "",
        f"- checkpoint: `{checkpoint_path}`",
        f"- tflite: `{output_path}`",
        f"- labels: `{labels_path}`",
        f"- output size: `{size_bytes}` bytes",
        "",
        "## Label Mapping",
        "",
        f"- class_values: `{labels['class_values']}`",
        f"- positive_class_value: `{labels['positive_class_value']}`",
        f"- positive_class_index: `{labels['positive_class_index']}`",
        f"- threshold: `{labels['threshold']}`",
        "",
        "## TFLite Inputs",
        "",
    ]

    for item in tflite_info["inputs"]:
        lines.append(
            f"- name `{item['name']}`, shape `{item['shape']}`, dtype `{item['dtype']}`"
        )

    lines += ["", "## TFLite Outputs", ""]
    for item in tflite_info["outputs"]:
        lines.append(
            f"- name `{item['name']}`, shape `{item['shape']}`, dtype `{item['dtype']}`"
        )

    lines += [
        "",
        "## Notes",
        "",
        "- Output is treated as logits and must be passed through softmax.",
        "- Confirm class mapping with the training dataset before formal deployment.",
    ]

    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert preclassifier_best.pt to preclassifier_mobile.tflite"
    )
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--keep-workdir", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if not args.checkpoint.exists():
        print(f"Checkpoint not found: {args.checkpoint}")
        print()
        print("Put preclassifier_best.pt at the default path or pass:")
        print("  python tools/convert_preclassifier_to_tflite.py --checkpoint C:\\path\\preclassifier_best.pt")
        return 2

    modules = require_modules()
    torch = modules["torch"]
    onnx = modules["onnx"]
    onnx_tf_backend = modules["onnx_tf_backend"]
    tf = modules["tensorflow"]

    model, class_values, saved_args = load_checkpoint_model(args.checkpoint, modules)

    n_mels = int(saved_args.get("n_mels", 128))
    target_frames = int(saved_args.get("target_frames", 256))
    dummy = torch.randn(1, 1, n_mels, target_frames, dtype=torch.float32)

    if args.keep_workdir:
        workdir = Path("outputs/model_check/preclassifier_conversion_work")
        workdir.mkdir(parents=True, exist_ok=True)
        cleanup = False
    else:
        workdir = Path(tempfile.mkdtemp(prefix="preclassifier_convert_"))
        cleanup = True

    onnx_path = workdir / "preclassifier_mobile.onnx"
    saved_model_path = workdir / "saved_model"

    try:
        print(f"Input checkpoint: {args.checkpoint}")
        print(f"Exporting ONNX: {onnx_path}")

        torch.onnx.export(
            model,
            dummy,
            str(onnx_path),
            input_names=["mel"],
            output_names=["logits"],
            opset_version=17,
            do_constant_folding=True,
        )

        print(f"Converting ONNX to TensorFlow SavedModel: {saved_model_path}")
        onnx_model = onnx.load(str(onnx_path))
        tf_rep = onnx_tf_backend.prepare(onnx_model)
        tf_rep.export_graph(str(saved_model_path))

        print(f"Converting SavedModel to TFLite: {args.output}")
        converter = tf.lite.TFLiteConverter.from_saved_model(str(saved_model_path))
        converter.optimizations = []
        tflite_model = converter.convert()

        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(tflite_model)

        labels = write_labels(args.labels, class_values, saved_args)
        tflite_info = inspect_tflite(args.output, modules)
        write_report(
            args.report,
            args.checkpoint,
            args.output,
            args.labels,
            labels,
            tflite_info,
        )

        print()
        print("Conversion finished.")
        print(f"Output TFLite: {args.output}")
        print(f"Output labels: {args.labels}")
        print(f"Report: {args.report}")
        print(f"Output size: {args.output.stat().st_size} bytes")
        print(f"TFLite input: {tflite_info['inputs']}")
        print(f"TFLite output: {tflite_info['outputs']}")
        return 0
    finally:
        if cleanup and workdir.exists():
            shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())

