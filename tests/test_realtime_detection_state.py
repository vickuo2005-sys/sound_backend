from services.realtime.node_manager import NodeConnectionState, NodeManager


class DummyWebSocket:
    async def send_json(self, _message):
        return None



def make_state() -> NodeConnectionState:
    return NodeConnectionState(
        device_id="node_A01",
        websocket=DummyWebSocket(),
        connection_id="test-connection",
        generation=1,
        protocol_version=1,
    )


def test_detection_state_tracks_positive_and_negative_inference_windows():
    manager = NodeManager()
    state = make_state()

    changed = manager.apply_detection_state_payload(
        state,
        {
            "detection_state": {
                "active": True,
                "sequence": 10,
                "observed_at_ms": 1_791_219_439_551,
                "label": "Drone",
                "confidence": 0.87,
            }
        },
    )

    assert changed is True
    assert state.detection_active is True
    assert state.detection_sequence == 10
    assert state.detection_label == "Drone"
    assert state.detection_confidence == 0.87
    assert state.detection_state_received_at_ms is not None

    positive_receipt = state.detection_state_received_at_ms
    public = state.to_public_dict(10.0, 20.0)
    assert public["detection_state"]["active"] is True
    assert public["detection_active"] is True
    assert public["detection_state"]["received_at_ms"] == positive_receipt

    changed = manager.apply_detection_state_payload(
        state,
        {
            "detection_state": {
                "active": False,
                "sequence": 11,
                "observed_at": "2026-10-07T01:58:00+08:00",
                "label": "Car",
                "confidence": 0.72,
            }
        },
    )

    assert changed is True
    assert state.detection_active is False
    assert state.detection_sequence == 11
    assert state.detection_label == "Car"
    assert state.detection_observed_at_ms is not None
    assert state.detection_state_received_at_ms >= positive_receipt


def test_detection_state_ignores_duplicate_or_out_of_order_sequence():
    manager = NodeManager()
    state = make_state()

    assert manager.apply_detection_state_payload(
        state,
        {"detection_state": {"active": True, "sequence": 20, "label": "Drone"}},
    )
    receipt = state.detection_state_received_at_ms

    assert manager.apply_detection_state_payload(
        state,
        {"detection_state": {"active": False, "sequence": 20, "label": "Car"}},
    ) is False
    assert manager.apply_detection_state_payload(
        state,
        {"detection_state": {"active": False, "sequence": 19, "label": "Car"}},
    ) is False

    assert state.detection_active is True
    assert state.detection_sequence == 20
    assert state.detection_label == "Drone"
    assert state.detection_state_received_at_ms == receipt


def test_plain_heartbeat_preserves_latest_detection_state():
    manager = NodeManager()
    state = make_state()

    manager.apply_status_payload(
        state,
        {"detection_state": {"active": True, "sequence": 3, "label": "Drone"}},
    )
    receipt = state.detection_state_received_at_ms

    manager.apply_status_payload(
        state,
        {"battery_percent": 75, "recording": False, "detection_enabled": False},
    )

    assert state.battery_percent == 75
    assert state.detection_active is True
    assert state.detection_sequence == 3
    assert state.detection_state_received_at_ms == receipt


def test_flat_detection_aliases_are_backward_compatible():
    manager = NodeManager()
    state = make_state()

    changed = manager.apply_detection_state_payload(
        state,
        {
            "detection_active": True,
            "detection_sequence": "7",
            "detection_observed_at_ms": "1791219439551",
            "detection_label": "Airplane",
            "detection_confidence": "0.66",
        },
    )

    assert changed is True
    assert state.detection_active is True
    assert state.detection_sequence == 7
    assert state.detection_observed_at_ms == 1_791_219_439_551.0
    assert state.detection_label == "Airplane"
    assert state.detection_confidence == 0.66


def test_payload_without_detection_state_does_not_create_realtime_state():
    manager = NodeManager()
    state = make_state()

    manager.apply_status_payload(state, {"last_ai_label": "Drone", "recording": True})

    assert state.detection_active is None
    assert state.detection_sequence is None
    assert state.detection_state_received_at_ms is None
    assert state.detection_state_dict() is None
