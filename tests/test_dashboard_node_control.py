from fastapi.testclient import TestClient

import main
from services.dashboard_v2_4 import render_dashboard_v2_4


def dashboard_html() -> str:
    return render_dashboard_v2_4(
        maps_api_key="",
        experimental_motion_enabled=False,
    )


def test_online_stopped_node_selects_start_command() -> None:
    html = dashboard_html()
    assert "selected.is_listening === true ? 'stop_listening' : 'start_listening'" in html
    assert "▶'} ${safe(commandCopy[startCommand].label)" in html


def test_online_listening_node_selects_stop_command() -> None:
    html = dashboard_html()
    assert "stop_listening" in html
    assert "■" in html
    assert "action-button ${startCommand === 'stop_listening' ? 'danger'" in html


def test_offline_node_disables_controls() -> None:
    html = dashboard_html()
    assert "節點離線，無法發送命令" in html
    assert "!state.devices.has(device.device_id) || !deviceOnline(device)" in html


def test_pending_command_disables_conflicting_controls() -> None:
    html = dashboard_html()
    assert "['sending','pending','delivered']" in html
    assert "目前命令尚未完成" in html


def test_node_status_has_bounded_refresh_for_missed_offline_transition() -> None:
    html = dashboard_html()
    assert "async function refreshDeviceSnapshot()" in html
    assert "fetchJson('/device-status', 5000)" in html
    assert "deviceSnapshotPollInFlight" in html
    assert "setInterval(() => { refreshDeviceSnapshot().catch(() => {}); }, 5000)" in html


def test_start_uses_themed_confirm_modal() -> None:
    html = dashboard_html()
    assert 'id="commandConfirmModal"' in html
    assert 'role="dialog"' in html
    assert "開始監聽？" in html
    assert "window.confirm(" not in html


def test_cancel_closes_modal_without_sending() -> None:
    html = dashboard_html()
    assert "commandConfirmCancel').addEventListener('click', closeCommandConfirm)" in html
    assert "state.confirmAction = null" in html


def test_confirm_posts_existing_command_schema() -> None:
    html = dashboard_html()
    assert "fetch('/device-command', {method:'POST'" in html
    assert "device_id:action.deviceId, command:action.command, value:null" in html
    assert "issued_by:'dashboard_v2_4_1'" in html


def test_stop_command_uses_existing_protocol_string() -> None:
    assert "stop_listening" in dashboard_html()


def test_detection_to_collection_uses_existing_protocol_string() -> None:
    assert 'data-command="set_collection_mode"' in dashboard_html()


def test_collection_to_detection_uses_existing_protocol_string() -> None:
    assert 'data-command="set_detection_mode"' in dashboard_html()


def test_ack_success_has_distinct_ui_state() -> None:
    html = dashboard_html()
    assert "ack_success" in html
    assert "命令執行成功" in html
    assert "refreshSnapshot(`command-${phase}`)" in html


def test_ack_failure_shows_backend_message() -> None:
    html = dashboard_html()
    assert "ack_failed" in html
    assert "data.message || data.ack_message" in html
    assert "命令執行失敗" in html


def test_timeout_is_bounded_and_retry_requires_confirmation() -> None:
    html = dashboard_html()
    assert "Date.now() + 30000" in html
    assert "setTimeout(() => pollCommandStatus" in html
    assert 'data-command-retry=' in html
    assert "openCommandConfirm(selected.device_id, button.dataset.commandRetry)" in html


def test_backend_error_has_user_safe_ui() -> None:
    html = dashboard_html()
    assert "命令建立失敗" in html
    assert "HTTP ${response.status}" in html


def test_home_control_entry_selects_node_and_opens_nodes_view() -> None:
    html = dashboard_html()
    assert 'data-node-control=' in html
    assert "openNodeControl(button.dataset.nodeControl)" in html
    assert "state.selectedNodeId = deviceId || 'node_A01'" in html


def test_modal_traps_focus_and_escape_cancels() -> None:
    html = dashboard_html()
    assert "event.key === 'Escape'" in html
    assert "event.key !== 'Tab'" in html
    assert "aria-modal=\"true\"" in html


def test_v2_4_does_not_restore_simulated_alert() -> None:
    html = dashboard_html()
    assert "simulateAlert" not in html
    assert "模擬警示" not in html


def test_legacy_dashboard_remains_available(monkeypatch) -> None:
    monkeypatch.setattr(main, "DASHBOARD_V2_ENABLED", True)
    response = TestClient(main.app).get("/dashboard/legacy")
    assert response.status_code == 200
    assert "節點控制" in response.text


def test_command_status_query_returns_terminal_status(monkeypatch) -> None:
    monkeypatch.setattr(
        main,
        "get_device_command_by_id",
        lambda device_id, command_id: {
            "id": command_id,
            "device_id": device_id,
            "command": "start_listening",
            "value": None,
            "status": "succeeded",
            "ack_message": "listening started",
            "created_at": "2026-09-01T10:00:00+00:00",
            "executed_at": "2026-09-01T10:00:01+00:00",
        },
    )
    response = TestClient(main.app).get(
        "/device-command/node_A01?command_id=142"
    )
    assert response.status_code == 200
    assert response.json() == {
        "has_command": True,
        "command_id": 142,
        "command": "start_listening",
        "value": None,
        "status": "succeeded",
        "ack_message": "listening started",
        "created_at": "2026-09-01T10:00:00+00:00",
        "executed_at": "2026-09-01T10:00:01+00:00",
    }


def test_legacy_flutter_pending_poll_shape_is_unchanged(monkeypatch) -> None:
    monkeypatch.setattr(
        main,
        "get_pending_device_command",
        lambda device_id: {
            "id": 143,
            "device_id": device_id,
            "command": "stop_listening",
            "value": None,
            "created_at": "2026-09-01T10:01:00+00:00",
        },
    )
    response = TestClient(main.app).get("/device-command/node_A01")
    assert response.status_code == 200
    assert response.json() == {
        "has_command": True,
        "command_id": 143,
        "command": "stop_listening",
        "value": None,
        "created_at": "2026-09-01T10:01:00+00:00",
    }
