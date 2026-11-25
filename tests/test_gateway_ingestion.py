from services.gateway_ingestion import (
    GatewayEventV1,
    gateway_transport_latency_ms,
    normalize_gateway_event,
)


def test_gateway_event_normalizes_to_existing_sound_event_shape():
    event = GatewayEventV1(
        gateway_id="pi-gw-01",
        node_id="A01",
        event_id="evt-123",
        sequence=42,
        detected_at_ms=1_700_000_000_000,
        gateway_received_at_ms=1_700_000_000_075,
        label="drone",
        confidence=0.91,
        latitude=25.0478,
        longitude=121.5319,
        gps_accuracy_m=4.0,
    )

    result = normalize_gateway_event(event, normalized_at_ms=1_700_000_000_100)

    assert result["event_id"] == "evt-123"
    assert result["device_id"] == "A01"
    assert result["label"] == "drone"
    assert result["trace_id"] == "gw:pi-gw-01:evt-123"
    assert result["latency_trace"]["device_event_time_ms"] == 1_700_000_000_000
    assert result["latency_trace"]["gateway_received_at"] == 1_700_000_000_075
    assert result["latency_trace"]["gateway_normalized_at"] == 1_700_000_000_100


def test_gateway_transport_latency_is_explicit_and_optional():
    event = GatewayEventV1(
        gateway_id="gw",
        node_id="node",
        event_id="evt",
        detected_at_ms=1000,
        gateway_received_at_ms=1125,
        label="drone",
    )
    assert gateway_transport_latency_ms(event) == 125

    no_gateway_timestamp = GatewayEventV1(
        gateway_id="gw",
        node_id="node",
        event_id="evt-2",
        detected_at_ms=1000,
        label="drone",
    )
    assert gateway_transport_latency_ms(no_gateway_timestamp) is None
