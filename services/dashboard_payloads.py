from __future__ import annotations

import json
import math
from typing import Any, Mapping, Optional


CANONICAL_CLASS_LABELS = (
    "Airplane",
    "Car",
    "Drone",
    "Electric_saw",
    "Rainfall",
)

CLASS_PRESENTATION = {
    "Airplane": {"name_zh": "航空器聲音", "icon": "airplane"},
    "Car": {"name_zh": "車輛聲音", "icon": "car"},
    "Drone": {"name_zh": "無人機聲音", "icon": "drone"},
    "Electric_saw": {"name_zh": "電鋸聲音", "icon": "electric-saw"},
    "Rainfall": {"name_zh": "降雨聲音", "icon": "rainfall"},
}


def _finite_number(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _object(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str) and value.strip():
        try:
            decoded = json.loads(value)
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}
        return dict(decoded) if isinstance(decoded, Mapping) else {}
    return {}


def canonical_scores(value: Any) -> dict[str, float]:
    scores = _object(value)
    result: dict[str, float] = {}
    for label in CANONICAL_CLASS_LABELS:
        score = _finite_number(scores.get(label))
        if score is not None:
            result[label] = score
    return result


def classification_presentation(event: Mapping[str, Any]) -> dict[str, Any]:
    """Build additive UI metadata without changing classification policy."""

    classification = _object(event.get("classification"))
    if not classification:
        return {
            "classification_available": False,
            "transport_label": event.get("label"),
            "model_label": None,
            "name_zh": "舊版事件",
            "icon": "legacy",
            "model_score": None,
            "operational_class": None,
            "is_target": None,
            "class_scores": {},
        }

    model_label = str(classification.get("model_label") or "").strip()
    presentation = CLASS_PRESENTATION.get(
        model_label,
        {"name_zh": "未識別分類", "icon": "unknown"},
    )
    class_scores = canonical_scores(
        classification.get("class_scores") or event.get("class_scores_json")
    )
    is_target = classification.get("is_target")
    return {
        "classification_available": True,
        "transport_label": event.get("label"),
        "model_label": model_label or None,
        "name_zh": presentation["name_zh"],
        "icon": presentation["icon"],
        "model_score": _finite_number(classification.get("confidence")),
        "operational_class": classification.get("operational_class"),
        "is_target": is_target if isinstance(is_target, bool) else None,
        "class_scores": class_scores,
        "schema_version": classification.get("schema_version"),
        "model_id": classification.get("model_id"),
        "model_version": classification.get("model_version"),
    }


def serialize_event_for_dashboard(event: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(event)
    result["dashboard_presentation"] = {
        **classification_presentation(result),
        "audio_available": bool(result.get("audio_path")),
        "location_available": _finite_number(result.get("latitude")) is not None
        and _finite_number(result.get("longitude")) is not None,
    }
    return result


def serialize_node_for_dashboard(node: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(node)
    result["dashboard_presentation"] = {
        "queue_source": "node_reported",
        "queue_count": None,
        "last_upload_status": result.get("last_upload_status"),
        "metadata_upload_status": result.get("metadata_upload_status"),
        "audio_upload_status": result.get("audio_upload_status"),
        "gps_available": _finite_number(result.get("marker_latitude")) is not None
        and _finite_number(result.get("marker_longitude")) is not None,
    }
    return result


def serialize_track_for_dashboard(
    track: Mapping[str, Any],
    *,
    experimental_motion_enabled: bool,
) -> dict[str, Any]:
    result = dict(track)
    result["dashboard_presentation"] = {
        "experimental": True,
        "field_validated": False,
        "motion_enabled": bool(experimental_motion_enabled),
        "speed_mps": _finite_number(result.get("last_speed_mps")),
        "heading_deg": _finite_number(result.get("last_heading_deg")),
        "motion_quality": result.get("motion_quality"),
    }
    return result
