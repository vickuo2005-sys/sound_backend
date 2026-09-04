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
    assert "const visiblePoints = points.slice(0, pointIndex + 1)" in html
    assert "replayLine.setPath(visiblePoints)" in html
    assert "interpolateTrack" not in html


def test_events_page_restores_csv_export() -> None:
    html = dashboard_html()
    assert 'href="/events/export.csv"' in html
    assert "download>Export CSV" in html


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
    assert "localStorage." not in html
    assert "sessionStorage." not in html
    assert "document.getElementById('locationWriteToken').value = ''" in html
    assert "location_source:" in html


def test_unsafe_v2_2_fake_alert_is_not_restored() -> None:
    html = dashboard_html()
    assert "simulateAlert" not in html
    assert "const eventId = `simulated_" not in html


def test_parity_plan_pins_the_exact_v2_2_baseline_and_exclusions() -> None:
    plan = (ROOT / "docs" / "dashboard" / "DASHBOARD_V2_2_PARITY_PLAN.md").read_text(
        encoding="utf-8"
    )
    assert "`2b29da3`" in plan
    assert "Never restore" in plan
    assert "Live audio is not enabled" in plan
    assert "No migration" in plan
