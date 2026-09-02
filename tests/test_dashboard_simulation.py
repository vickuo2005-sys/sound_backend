from pathlib import Path

from fastapi.testclient import TestClient

import main
from services.dashboard_v2_4 import render_dashboard_v2_4


SCENARIO_PATH = (
    Path(__file__).resolve().parents[1]
    / "static"
    / "dashboard_simulation_scenarios.js"
)


def simulation_html() -> str:
    return render_dashboard_v2_4(
        maps_api_key="test key",
        experimental_motion_enabled=True,
        simulation_enabled=True,
    )


def production_safe_html() -> str:
    return render_dashboard_v2_4(
        maps_api_key="",
        experimental_motion_enabled=False,
        simulation_enabled=False,
    )


def test_simulation_feature_flag_defaults_off() -> None:
    source = (Path(__file__).resolve().parents[1] / "main.py").read_text(
        encoding="utf-8"
    )
    assert 'os.getenv("DASHBOARD_SIMULATION_ENABLED", "false")' in source


def test_flag_off_omits_entry_panel_and_scenario_payload() -> None:
    html = production_safe_html()
    assert 'id="simulationOpenButton"' not in html
    assert 'id="simulationPanel"' not in html
    assert "approach_site_demo_v1: Object.freeze" not in html
    assert "const dashboardSimulationEnabled = false" in html


def test_flag_on_renders_explicit_demo_only_labels() -> None:
    html = simulation_html()
    assert 'id="simulationOpenButton"' in html
    assert "SIMULATION / 模擬展示" in html
    assert "NOT FIELD VALIDATED" in html
    assert "approach_site_demo_v1" in html
    assert "不代表目前實際偵測結果或已驗證預測能力" in html


def test_runtime_status_exposes_additive_flag(monkeypatch) -> None:
    monkeypatch.setattr(main, "DASHBOARD_SIMULATION_ENABLED", True)
    response = TestClient(main.app).get("/runtime-status")
    assert response.status_code == 200
    assert response.json()["dashboard_simulation_enabled"] is True


def test_dashboard_route_passes_runtime_flag(monkeypatch) -> None:
    monkeypatch.setattr(main, "DASHBOARD_V2_ENABLED", True)
    monkeypatch.setattr(main, "DASHBOARD_SIMULATION_ENABLED", True)
    response = TestClient(main.app).get("/dashboard")
    assert response.status_code == 200
    assert 'id="simulationOpenButton"' in response.text


def test_scenario_is_static_demo_data_with_75_second_duration() -> None:
    source = SCENARIO_PATH.read_text(encoding="utf-8")
    assert "duration_seconds: 75" in source
    assert "source: 'static_demo_scenario'" in source
    assert "field_validated: false" in source
    assert source.count("simulation:true") >= 8
    assert "Object.freeze" in source


def test_scenario_contains_a_turn_and_no_private_identifiers() -> None:
    source = SCENARIO_PATH.read_text(encoding="utf-8")
    assert "t:60" in source and "t:66" in source and "t:75" in source
    assert "demo_site_alpha" in source
    assert "node_A01" not in source
    assert "device_id" not in source


def test_state_machine_has_all_required_states() -> None:
    html = simulation_html()
    for phase in ("inactive", "ready", "playing", "paused", "completed"):
        assert f"'{phase}'" in html


def test_query_parameter_opens_ready_without_autoplay() -> None:
    html = simulation_html()
    assert "new URLSearchParams(location.search).get('simulation') === '1'" in html
    assert "Object.assign(simulationPlayback, {phase:'ready'" in html


def test_animation_uses_request_animation_frame_and_interpolation() -> None:
    html = simulation_html()
    assert "requestAnimationFrame(simulationAnimationFrame)" in html
    assert "function interpolatePosition" in html
    assert "Math.min(.25" in html


def test_history_current_and_prediction_styles_are_distinct() -> None:
    html = simulation_html()
    assert "strokeColor:'#f59e0b'" in html
    assert "fillColor:'#22d3ee'" in html
    assert "strokeOpacity:0" in html
    assert "repeat:'12px'" in html


def test_constant_velocity_prediction_has_required_horizons() -> None:
    html = simulation_html()
    assert "const predictionOffsets = [5, 10, 15, 30]" in html
    assert "latPerSecond * offset" in html
    assert "lngPerSecond * offset" in html
    assert "Kalman" not in html


def test_demo_site_and_uncertainty_are_simulation_overlays() -> None:
    html = simulation_html()
    assert "fillColor:'#a855f7'" in html
    assert "SIMULATION demo site" in html
    assert "uncertaintyM" in html
    assert "simulationMapObjects.uncertaintyCircle" in html


def test_dynamic_motion_metrics_are_present() -> None:
    html = simulation_html()
    for label in (
        "Simulated speed",
        "Simulated heading",
        "Relative motion",
        "Demo site distance",
        "Predicted closest distance",
        "Estimated arrival in simulation",
        "Simulated quality",
    ):
        assert label in html
    assert "APPROACHING" in html and "DEPARTING" in html and "STATIONARY" in html


def test_controls_cover_play_pause_restart_exit_speed_seek_and_follow() -> None:
    html = simulation_html()
    for element_id in (
        "simulationPlayButton",
        "simulationRestartButton",
        "simulationExitButton",
        "simulationSpeed",
        "simulationSeek",
        "simulationFollowTarget",
        "simulationScenario",
    ):
        assert f'id="{element_id}"' in html
    assert '<option value="0.5">0.5×</option>' in html
    assert '<option value="2">2×</option>' in html


def test_exit_clears_only_overlay_objects_without_reload() -> None:
    html = simulation_html()
    exit_body = html.split("function exitSimulationMode()", 1)[1].split("function safe", 1)[0]
    assert "clearSimulationMap()" in exit_body
    assert "renderMap()" in exit_body
    assert "reload" not in exit_body


def test_simulation_never_enters_real_event_or_track_state() -> None:
    html = simulation_html()
    simulation_code = html.split("function simulationIsVisible()", 1)[1].split("function safe", 1)[0]
    assert "state.events" not in simulation_code
    assert "state.tracks" not in simulation_code
    assert "upsertEvent" not in simulation_code
    assert "upsertDevice" not in simulation_code


def test_simulation_code_has_no_network_or_persistence_write() -> None:
    html = simulation_html()
    simulation_code = html.split("function simulationIsVisible()", 1)[1].split("function safe", 1)[0]
    for forbidden in ("fetch(", "WebSocket(", "/events", "/device-command", "localStorage", "sessionStorage"):
        assert forbidden not in simulation_code


def test_real_websocket_and_node_controls_remain_in_page() -> None:
    html = simulation_html()
    assert "new WebSocket(`${protocol}//${location.host}/ws/dashboard`)" in html
    assert "fetch('/device-command'" in html
    assert "event_trigger" in html
    assert "node_heartbeat" in html


def test_operational_overlays_are_dimmed_not_removed_during_simulation() -> None:
    html = simulation_html()
    assert "simulationIsVisible() ? .28 : 1" in html
    assert "simulationIsVisible() ? .22 : .85" in html
    assert "nodeMarkers" in html and "trackLines" in html and "detectionMarker" in html


def test_follow_target_is_user_controlled() -> None:
    html = simulation_html()
    assert "simulationTargetNearViewportEdge(metrics.position)" in html
    assert "map.panTo(metrics.position)" in html
    assert "const latPadding" in html
    assert "simulationPlayback.followTarget = event.target.checked" in html


def test_simulation_panel_has_responsive_overflow_guards() -> None:
    html = simulation_html()
    assert ".simulation-controls { margin-top: 10px; flex-wrap: wrap; }" in html
    assert ".simulation-timeline input { flex: 1; min-width: 100px;" in html
    assert "overflow-x: hidden" in html


def test_simulation_controller_snapshot_is_explicitly_tagged() -> None:
    html = simulation_html()
    assert "snapshot: () => ({simulation:true" in html


def test_metrics_are_throttled_while_map_animation_remains_frame_driven() -> None:
    html = simulation_html()
    assert "frameTime - simulationPlayback.lastDomUpdateAt >= 125" in html
    assert "updateSimulationFrame(false, now)" in html
    assert "renderSimulationMap(simulationPlayback.metrics)" in html


def test_watermark_is_fixed_and_timeline_has_ticks() -> None:
    html = simulation_html()
    assert "position: fixed; z-index: 90" in html
    assert 'id="simulationTimelineTicks"' in html
    assert "00:15" in html and "01:15" in html
    assert "模擬 CV 預測" in html


def test_isolated_staging_manifests_enable_the_flag() -> None:
    root = Path(__file__).resolve().parents[1]
    assert 'key: DASHBOARD_SIMULATION_ENABLED\n        value: "true"' in (
        root / "render.staging.yaml"
    ).read_text(encoding="utf-8")
    assert "DASHBOARD_SIMULATION_ENABLED=true" in (
        root / ".env.staging.example"
    ).read_text(encoding="utf-8")
