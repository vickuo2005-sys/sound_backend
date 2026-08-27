from __future__ import annotations

import math
from typing import Annotated, Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


CLASSIFICATION_SCHEMA_VERSION = "classification.v1"
CANONICAL_LABELS = (
    "Airplane",
    "Car",
    "Drone",
    "Electric_saw",
    "Rainfall",
)
LEGACY_TARGET_THRESHOLD = 0.5
CanonicalLabel = Literal[
    "Airplane",
    "Car",
    "Drone",
    "Electric_saw",
    "Rainfall",
]
OperationalClass = Literal["aircraft", "drone", "non_aircraft"]
Score = Annotated[float, Field(ge=0.0, le=1.0)]


class ClassificationMetadata(BaseModel):
    """Versioned five-class transport contract.

    App-supplied operational fields are accepted for compatibility diagnostics.
    `normalize_classification` is the server trust boundary that rebuilds them.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["classification.v1"] = CLASSIFICATION_SCHEMA_VERSION
    model_id: str = Field(min_length=1, max_length=128)
    model_version: str = Field(min_length=1, max_length=64)
    model_label: CanonicalLabel
    confidence: Score
    class_scores: dict[str, Score]
    operational_class: OperationalClass
    aircraft_probability: Score
    is_target: bool
    drone_subtype: None = None

    @model_validator(mode="after")
    def validate_score_contract(self) -> "ClassificationMetadata":
        if set(self.class_scores) != set(CANONICAL_LABELS):
            raise ValueError(
                "class_scores must contain exactly the five canonical labels"
            )
        top_label = max(CANONICAL_LABELS, key=self.class_scores.__getitem__)
        top_score = self.class_scores[top_label]
        if self.model_label != top_label:
            raise ValueError("model_label must match the top class score")
        if not math.isclose(self.confidence, top_score, rel_tol=0.0, abs_tol=1e-6):
            raise ValueError("confidence must equal the top class score")
        return self


def normalize_classification(
    classification: Optional[ClassificationMetadata],
) -> Optional[ClassificationMetadata]:
    """Return a canonical server-derived decision without trusting App policy fields."""

    if classification is None:
        return None
    airplane_score = classification.class_scores["Airplane"]
    drone_score = classification.class_scores["Drone"]
    aircraft_probability = min(1.0, max(0.0, airplane_score + drone_score))
    is_target = aircraft_probability > LEGACY_TARGET_THRESHOLD
    operational_class: OperationalClass
    if not is_target:
        operational_class = "non_aircraft"
    elif drone_score > airplane_score:
        operational_class = "drone"
    else:
        operational_class = "aircraft"
    return classification.model_copy(
        update={
            "operational_class": operational_class,
            "aircraft_probability": aircraft_probability,
            "is_target": is_target,
            "drone_subtype": None,
        }
    )


def classification_storage_values(
    classification: Optional[ClassificationMetadata],
) -> dict[str, Any]:
    normalized = normalize_classification(classification)
    if normalized is None:
        return {
            "classification_schema_version": None,
            "model_id": None,
            "model_version": None,
            "model_label": None,
            "model_confidence": None,
            "operational_class": None,
            "aircraft_probability": None,
            "drone_subtype": None,
            "class_scores_json": None,
        }
    return {
        "classification_schema_version": normalized.schema_version,
        "model_id": normalized.model_id,
        "model_version": normalized.model_version,
        "model_label": normalized.model_label,
        "model_confidence": normalized.confidence,
        "operational_class": normalized.operational_class,
        "aircraft_probability": normalized.aircraft_probability,
        "drone_subtype": normalized.drone_subtype,
        "class_scores_json": dict(normalized.class_scores),
    }


def classification_transport_dict(
    classification: Optional[ClassificationMetadata],
) -> Optional[dict[str, Any]]:
    normalized = normalize_classification(classification)
    return normalized.model_dump() if normalized is not None else None
