from services.dashboard_v2_4 import render_dashboard_v2_4


def test_live_map_patch_is_rendered_after_operations_ui():
    html = render_dashboard_v2_4(
        maps_api_key="",
        experimental_motion_enabled=False,
        simulation_enabled=False,
        location_token_required=False,
    )

    assert "__OPERATIONS_UI_SCRIPT__" not in html
    operations_marker = "window.DashboardOperationsUI={render,start,group,pause,clear"
    patch_marker = "__dashboardLiveMapPatchInstalled"
    assert operations_marker in html
    assert patch_marker in html
    assert html.index(operations_marker) < html.index(patch_marker)
