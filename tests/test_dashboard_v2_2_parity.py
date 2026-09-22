from pathlib import Path

from fastapi.testclient import TestClient

import main
from services.dashboard_v2_4 import render_dashboard_v2_4


ROOT = Path(__file__).resolve().parents[1]


def dashboard_html() -> str:
    return render_dashboard_v2_4(
        maps_api_key="test-key",
        experimental_motion_enabled=True,
        simulation_enabled=True,
    )


def test_tracks_workspace_restores_existing_backend_data_paths() -> None:
    html = dashboard_html()
    assert 'data-view-target="tracks"' in html
    assert 'id="view-tracks"' in html
    assert 'id="targetEstimateList"' in html
    assert 'id="historyTrackList"' in html
    assert "fetchJson('/event-groups?limit=20')" in html
    assert "fetchJson('/tracks?limit=20&points_limit=100'" in html
    assert "function renderTracksView()" in html


def test_region_preview_uses_backend_coordinates_and_optional_uncertainty() -> None:
    html = dashboard_html()
    assert "group?.region_center_lat ?? group?.estimated_lat" in html
    assert "group?.region_center_lng ?? group?.estimated_lng" in html
    assert "finite(estimate.uncertainty_radius_m)" in html
    assert "estimateMarker = new google.maps.Marker" in html
    assert "estimateCircle = new google.maps.Circle" in html
    assert "now - time <= 15000" in html
    assert "!['closed','expired'].includes(status)" in html


def test_historical_replay_reveals_recorded_points_without_interpolation() -> None:
    html = dashboard_html()
    assert "function startTrackReplay(id)" in html
    assert "path:path.slice(0,i+1)" in html
    assert "historyLine.setPath(f.path)" in html
    assert "interpolateTrack" not in html


def test_events_page_restores_csv_export() -> None:
    html = dashboard_html()
    assert 'href="/events/export.csv"' in html
    assert "download>匯出 CSV" in html


def test_csv_export_works_on_sqlite_fallback(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(main, "DB_NAME", str(tmp_path / "export.db"))
    main.init_sqlite_db()

    response = TestClient(main.app).get("/events/export.csv")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "sound_events_export.csv" in response.headers["content-disposition"]
    assert response.text.startswith("event_id,device_id,timestamp,label")


def test_fixed_location_editor_is_authenticated_and_does_not_persist_token() -> None:
    html = dashboard_html()
    assert 'id="locationEditorModal"' in html
    assert "method:'PUT'" in html
    assert "method:'DELETE'" in html
    assert "'x-upload-token':document.getElementById('locationWriteToken').value.trim()" in html
    assert "localStorage.setItem('sound-dashboard-site-v1',JSON.stringify(next))" in html
    assert "name:data.name.trim(),lat:Number(data.lat),lng:Number(data.lng),radius:Number(data.radius),arrivalRadius:Number(data.arrivalRadius)" in html
    assert "sessionStorage." not in html
    assert "document.getElementById('locationWriteToken').value = ''" in html
    assert "location_source:" in html


def test_unsafe_v2_2_fake_alert_is_not_restored() -> None:
    html = dashboard_html()
    assert "simulateAlert" not in html
    assert "const eventId = `simulated_" not in html


def test_node_markers_reuse_v2_2_shapes_and_reporting_animation() -> None:
    html = dashboard_html()
    assert "function nodeMarkerIcon(device, online, active=false, pulse=.5)" in html
    assert "path:google.maps.SymbolPath.CIRCLE" in html
    assert "fillColor:reporting?'#f97316':online?'#f8fafc':'#475569'" in html
    assert "strokeColor:reporting?'#ffb86b':online?'#111827':'#f8fafc'" in html
    assert "strokeWeight:reporting?4:3" in html
    assert "scale:reporting?14+Math.max(0,Math.min(1,pulse))*6:14" in html
    assert "text:`${shortNodeId(device.device_id)}${online?'':'×'}`" in html
    assert "固定節點離線後仍保留在地圖" in html
    assert "activeReportingNodeIds.has(device.device_id)" in html
    assert "onPulse:updateNodeMarkerPulse" in html


def test_parity_plan_pins_the_exact_v2_2_baseline_and_exclusions() -> None:
    plan = (ROOT / "docs" / "dashboard" / "DASHBOARD_V2_2_PARITY_PLAN.md").read_text(
        encoding="utf-8"
    )
    assert "`2b29da3`" in plan
    assert "Never restore" in plan
    assert "Live audio is not enabled" in plan
    assert "No migration" in plan



def test_live_map_restores_v2_2_sensor_region_and_track_presence() -> None:
    html = dashboard_html()
    # V2.2-style immediate visualization is presentation-only: it groups fresh
    # alerting sensor nodes while Backend fusion/TDOA is still pending.
    assert "function liveSensorFallbackEstimate(now=Date.now())" in html
    assert "sensor_region_fallback:true" in html
    assert "此中心只供 V2.2 live-map parity 顯示，不送入 TDOA、Track 或 ETA。" in html
    assert "function selectedOrLatestMapEstimate()" in html
    assert "function freshBackendMultiNodeEvidence(now=Date.now())" in html
    assert "function freshBackendLocatedGroup(now=Date.now())" in html
    assert "const liveGroups=geometryFallback?[...state.groups.values(),geometryFallback]:[...state.groups.values()]" in html
    assert "const current = selectedOrLatestMapEstimate()" in html

    # Preserve the current Dashboard icon language while restoring V2.2 behavior.
    assert "return {...common, path:google.maps.SymbolPath.CIRCLE};" in html
    assert "id.endsWith('A01')" not in html
    assert "id.endsWith('A02')" not in html
    assert "activeReportingNodeIds.has(device.device_id)" in html
    assert "onPulse:updateNodeMarkerPulse" in html

    # Fresh Backend localization/track gets the V2.2 UAV marker and direction.
    assert "let trackMarkers = new Map()" in html
    assert "let trackDirectionLines = new Map()" in html
    assert "function isFreshLiveTrack(track,now=Date.now())" in html
    assert "LIVE TRACK ·" in html
    assert "FORWARD_CLOSED_ARROW" in html
    assert "function v22DroneTargetIcon(heading=0)" in html
    assert "icon:v22DroneTargetIcon(heading??0)" in html
    assert "function liveDroneMapIcon" not in html


def test_live_map_rejected_track_points_do_not_reappear_on_map() -> None:
    html = dashboard_html()
    assert "point?.rejected_as_outlier" in html
    assert "point?.is_outlier" in html
    assert "point?.is_rejected" in html
    assert "point?.accepted !== false" in html



def test_live_map_backend_handoff_avoids_duplicate_synthetic_geometry() -> None:
    html = dashboard_html()
    assert "geometryFallback=!freshBackendMultiNodeEvidence(now)?sensorFallback:null" in html
    assert "if(freshBackendLocatedGroup(now))return null;" in html
    assert "fallbackGeometry=!freshBackendMultiNodeEvidence(fallbackNow)?fallbackSensor:null" in html
    assert "groups:fallbackGroups" in html



def test_live_map_visual_hierarchy_keeps_node_identity_separate_from_state() -> None:
    html = dashboard_html()
    # Node identity is always circular; reporting state changes border/pulse only.
    marker_start = html.index("function nodeMarkerIcon(device, online, active=false, pulse=.5)")
    marker_end = html.index("window.initOperationalMap", marker_start)
    marker_block = html[marker_start:marker_end]
    assert "SymbolPath.CIRCLE" in marker_block
    assert "scale:14" in marker_block
    assert "id.endsWith('A01')" not in marker_block
    assert "id.endsWith('A02')" not in marker_block
    assert "id.endsWith('A03')" not in marker_block
    assert "id.endsWith('A04')" not in marker_block

    # Raw event is visually subordinate; sensor-only center is hollow; formal
    # estimate keeps EST; Backend track uses the existing drone icon.
    assert "原始事件回報 ·" in html
    assert "fillOpacity:.72" in html
    assert "即時感測區域參考中心（非定位）" in html
    assert "fillOpacity:.08" in html
    assert "label:{text:'EST'" in html
    assert "droneMapIcon('#f97316',heading??0)" in html



def test_operational_target_reuses_v2_2_uav_icon() -> None:
    operations = (ROOT / "static" / "dashboard_operations_ui.js").read_text(encoding="utf-8")
    assert "window.v22DroneTargetIcon?window.v22DroneTargetIcon(target.heading??0)" in operations
    assert "label:{text:'UAV'" in operations



def test_live_warning_region_accepts_aircraft_backend_groups() -> None:
    html = dashboard_html()
    geometry_js = (ROOT / "static" / "dashboard_node_geometry.js").read_text(encoding="utf-8")
    assert "function isLiveTargetLabel(value)" in html
    assert "['drone','uav','aircraft','plane','airplane']" in html
    assert "isLiveTargetGroup(group) && groupDeviceIds(group).length>=2" in html
    assert "isLiveTargetLabel(track?.label)" in html
    assert "function isTargetGroup(group)" in geometry_js
    assert "source:reports.length?'event_evidence':'backend_group_membership'" in geometry_js
    assert "Frontend event-cache completeness must not decide" in geometry_js
