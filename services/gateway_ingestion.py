from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class GatewayEventV1(BaseModel):
    """Transport-neutral event contract for Pi/Wi-SUN gateways.

    The contract deliberately stops at the ingestion boundary. Downstream
    persistence, Fusion, Tracking and Dashboard code continue to consume the
    existing SoundEvent model after normalization.
    """

    schema_version: Literal["gateway.event.v1"] = "gateway.event.v1"
    gateway_id: str = Field(min_length=1, max_length=128)
    node_id: str = Field(min_length=1, max_length=128)
    event_id: str = Field(min_length=1, max_length=160)
    sequence: Optional[int] = Field(default=None, ge=0)
    detected_at_ms: int = Field(ge=0)
    gateway_received_at_ms: Optional[int] = Field(default=None, ge=0)

    label: str = Field(min_length=1, max_length=128)
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)

    latitude: Optional[float] = Field(default=None, ge=-90.0, le=90.0)
    longitude: Optional[float] = Field(default=None, ge=-180.0, le=180.0)
    gps_accuracy_m: Optional[float] = Field(default=None, ge=0.0)

    trace_id: Optional[str] = Field(default=None, min_length=1, max_length=160)
    classification: Optional[dict[str, Any]] = None
    audio_ref: Optional[str] = Field(default=None, max_length=2048)
    metadata: dict[str, Any] = Field(default_factory=dict)


def normalize_gateway_event(
    event: GatewayEventV1,
    *,
    normalized_at_ms: int,
) -> dict[str, Any]:
    """Map a gateway event into the existing SoundEvent input shape.

    MQTT, HTTP and future transports should all call this same function. This
    keeps transport concerns outside persistence/Fusion/Tracking.
    """

    detected_at = datetime.fromtimestamp(
        event.detected_at_ms / 1000.0,
        tz=timezone.utc,
    ).isoformat()

    trace_id = event.trace_id or f"gw:{event.gateway_id}:{event.event_id}"
    latency_trace: dict[str, Any] = {
        "device_event_time_ms": event.detected_at_ms,
        "gateway_normalized_at": normalized_at_ms,
    }
    if event.gateway_received_at_ms is not None:
        latency_trace["gateway_received_at"] = event.gateway_received_at_ms

    normalized: dict[str, Any] = {
        "event_id": event.event_id,
        "device_id": event.node_id,
        "timestamp": detected_at,
        "latitude": event.latitude,
        "longitude": event.longitude,
        "gps_accuracy_m": event.gps_accuracy_m,
        "label": event.label,
        "trace_id": trace_id,
        "latency_trace": latency_trace,
    }

    if event.classification is not None:
        normalized["classification"] = event.classification
    if event.audio_ref:
        normalized["audio_path"] = event.audio_ref

    return normalized


def gateway_transport_latency_ms(event: GatewayEventV1) -> Optional[int]:
    if event.gateway_received_at_ms is None:
        return None
    return event.gateway_received_at_ms - event.detected_at_ms
