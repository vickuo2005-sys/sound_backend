from __future__ import annotations

from pathlib import Path
import os
from html import escape
from urllib.parse import quote


TEMPLATE_PATH = Path(__file__).resolve().parents[1] / "templates" / "dashboard_v2_4.html"
STATUS_SCRIPT_PATH = TEMPLATE_PATH.parents[1] / "static" / "dashboard_status.js"
EVENT_CONTEXT_SCRIPT_PATH = TEMPLATE_PATH.parents[1] / "static" / "dashboard_event_context.js"
AUDIO_EVIDENCE_SCRIPT_PATH = TEMPLATE_PATH.parents[1] / "static" / "dashboard_audio_evidence.js"
LIVE_MAP_PATCH_PATH = TEMPLATE_PATH.parents[1] / "static" / "dashboard_live_map_patch.js"
SIMULATION_PREDICTION_PATH = (
    Path(__file__).resolve().parents[1]
    / "static"
    / "dashboard_simulation_prediction.js"
)
SIMULATION_SCENARIO_PATH = (
    Path(__file__).resolve().parents[1]
    / "static"
    / "dashboard_simulation_scenarios.js"
)


def render_dashboard_v2_4(
    *,
    maps_api_key: str,
    experimental_motion_enabled: bool,
    simulation_enabled: bool = False,
    location_token_required: bool = True,
    demo_stable_mode: bool = False,
) -> str:
    html = TEMPLATE_PATH.read_text(encoding="utf-8")
    if demo_stable_mode:
        experimental_motion_enabled = False
    maps_script_tag = ""
    if maps_api_key:
        maps_url = (
            "https://maps.googleapis.com/maps/api/js?"
            f"key={quote(maps_api_key)}&callback=initOperationalMap"
        )
        maps_script_tag = f'<script async defer src="{maps_url}"></script>'
    simulation_controls = ""
    simulation_topbar_badge = ""
    simulation_map_legend = ""
    simulation_watermark = ""
    simulation_panel = ""
    simulation_scenario_script = ""
    if simulation_enabled:
        simulation_controls = """
        <button id="simulationOpenButton" class="ghost-button simulation-entry" type="button">
            情境模擬展示
        </button>
        """
        simulation_topbar_badge = """
        <span id="simulationTopbarBadge" class="simulation-topbar-badge" hidden>
            <strong>情境模擬</strong><span>模擬資料 · 非實地驗證</span>
            <button id="simulationQuickExitButton" class="action-button simulation-quick-exit" type="button">✕ 結束模擬</button>
        </span>
        """
        simulation_watermark = """
        <div id="simulationWatermark" class="simulation-watermark" hidden>
            <strong>情境模擬</strong>
            <span>模擬資料 · 非實地驗證</span>
        </div>
        """
        simulation_map_legend = """
        <span class="simulation-legend"><b class="legend-symbol simulation-history">━</b> Simulation history</span>
        <span class="simulation-legend"><b class="legend-symbol simulation-prediction">┄</b> Predicted path</span>
        <span class="simulation-legend"><b class="legend-symbol simulation-site">●</b> Fixed site / radius</span>
        """
        simulation_panel = """
        <section id="simulationPanel" class="simulation-panel" aria-label="動態軌跡模擬控制" hidden>
            <div class="simulation-banner">
                <div><strong>情境模擬展示</strong><span id="simulationScenarioName">無人機接近據點</span></div>
                <button id="simulationExitButton" class="ghost-button" type="button">結束模擬</button>
            </div>
            <p class="simulation-disclaimer">此區使用模擬資料示範系統流程，與即時監控資料完全分離。</p>
            <div class="simulation-controls">
                <button id="simulationPlayButton" class="action-button primary" type="button">開始播放</button>
                <button id="simulationRestartButton" class="action-button" type="button">重新開始</button>
                <label>情境
                    <select id="simulationScenario" class="select-control" aria-label="模擬情境">
                        <option value="approach_site_demo_v1">A · Direct Approach</option>
                        <option value="parallel_flyby_demo_v1">B · Parallel Fly-by</option>
                        <option value="departing_demo_v1">C · Departing</option>
                    </select>
                </label>
                <label>播放速度
                    <select id="simulationSpeed" class="select-control" aria-label="模擬播放速度">
                        <option value="0.5">0.5×</option><option value="1" selected>1×</option><option value="2">2×</option>
                    </select>
                </label>
                <label class="simulation-follow"><input id="simulationFollowTarget" type="checkbox" checked> 跟隨目標</label>
                <span id="simulationStateBadge" class="badge experimental">待命</span>
            </div>
            <div class="simulation-timeline">
                <input id="simulationSeek" type="range" min="0" max="90" value="0" step="0.1" list="simulationTimelineTicks" aria-label="模擬時間軸">
                <output id="simulationTime" for="simulationSeek">00:00 / 01:30</output>
            </div>
            <datalist id="simulationTimelineTicks"><option value="0" label="00:00"></option><option value="15" label="00:15"></option><option value="30" label="00:30"></option><option value="45" label="00:45"></option><option value="60" label="01:00"></option><option value="75" label="01:15"></option><option value="90" label="01:30"></option></datalist>
            <div class="simulation-ticks" aria-hidden="true"><span>00:00</span><span>00:15</span><span>00:30</span><span>00:45</span><span>01:00</span><span>01:15</span><span>01:30</span></div>
        </section>
        """
        simulation_scenario_script = (
            "<script>\n"
            + SIMULATION_PREDICTION_PATH.read_text(encoding="utf-8")
            + "\n</script>\n<script>\n"
            + SIMULATION_SCENARIO_PATH.read_text(encoding="utf-8")
            + "\n</script>"
        )
    demo_stable_style = (
        ".demo-experimental,.demo-diagnostics,.demo-validation-scope,.advanced-control,.slab-prediction-debug{display:none!important}"
        if demo_stable_mode
        else ""
    )
    sidebar_note = (
        "系統展示模式<br>即時監控與情境模擬資料分流顯示"
        if demo_stable_mode
        else "測試環境<br>軌跡與抵達時間仍待實地驗證"
    )
    system_description = (
        "連線、裝置與服務狀態"
        if demo_stable_mode
        else "連線、裝置與進階診斷"
    )

    return (
        html.replace("__MAPS_SCRIPT_TAG__", maps_script_tag)
        .replace("__DEMO_STABLE_STYLE__", demo_stable_style)
        .replace("__SIDEBAR_NOTE__", sidebar_note)
        .replace("__SYSTEM_DESCRIPTION__", system_description)
        .replace("__ENVIRONMENT_LABEL__", escape(os.getenv("APP_ENV", "staging").upper()))
        .replace("__OVERVIEW_SCRIPT__", "<script>" + (TEMPLATE_PATH.parents[1] / "static/dashboard_overview.js").read_text(encoding="utf-8") + "</script>")
        .replace("__MAP_VISUALS_SCRIPT__", "<script>" + (TEMPLATE_PATH.parents[1] / "static/dashboard_map_visuals.js").read_text(encoding="utf-8") + "</script>")
        .replace("__NODE_GEOMETRY_SCRIPT__", "<script>" + (TEMPLATE_PATH.parents[1] / "static/dashboard_node_geometry.js").read_text(encoding="utf-8") + "</script>")
        .replace("__DASHBOARD_REFINEMENT_STYLES__", "<style>" + (TEMPLATE_PATH.parents[1] / "static/dashboard_apk_theme.css").read_text(encoding="utf-8") + ((TEMPLATE_PATH.parents[1] / "static/dashboard_simulation_lab.css").read_text(encoding="utf-8") if simulation_enabled else "") + "</style>")
        .replace("__SIMULATION_LAB_SCRIPT__", ("<script>" + (TEMPLATE_PATH.parents[1] / "static/dashboard_simulation_kalman.js").read_text(encoding="utf-8") + "</script><script>" + (TEMPLATE_PATH.parents[1] / "static/dashboard_simulation_lab.js").read_text(encoding="utf-8") + "</script>") if simulation_enabled else "")
        .replace("__OPERATIONS_SCRIPT__", "".join("<script>" + (TEMPLATE_PATH.parents[1] / "static" / name).read_text(encoding="utf-8") + "</script>" for name in ("dashboard_simulation_eta.js", "dashboard_simulation_tracker.js", "dashboard_operations.js", "dashboard_live_prediction.js")))
        .replace(
            "__OPERATIONS_UI_SCRIPT__",
            "<script>"
            + (TEMPLATE_PATH.parents[1] / "static/dashboard_operations_ui.js").read_text(encoding="utf-8")
            + "</script><script>"
            + LIVE_MAP_PATCH_PATH.read_text(encoding="utf-8")
            + "</script><script>"
            + (TEMPLATE_PATH.parents[1] / "static/dashboard_phase3d.js").read_text(encoding="utf-8")
            + "</script>",
        )
        .replace("__AUDIO_EVIDENCE_SCRIPT__", "<script>" + AUDIO_EVIDENCE_SCRIPT_PATH.read_text(encoding="utf-8") + "</script>")
        .replace("__EVENT_CONTEXT_SCRIPT__", "<script>" + EVENT_CONTEXT_SCRIPT_PATH.read_text(encoding="utf-8") + "</script>")
        .replace("__LOCATION_TOKEN_REQUIRED__", "true" if location_token_required else "false")
        .replace("__LOCATION_TOKEN_HIDDEN__", "" if location_token_required else "hidden")
        .replace(
            "__STATUS_SCRIPT__",
            "<script>" + STATUS_SCRIPT_PATH.read_text(encoding="utf-8") + "</script>",
        )
        .replace("__SIMULATION_CONTROLS__", simulation_controls)
        .replace(
            "__SIMULATION_NAV__",
            '<button class="nav-button" data-view-target="simulation"><span class="nav-icon">▷</span>情境模擬</button>' if simulation_enabled else '',
        )
        .replace("__SIMULATION_TOPBAR_BADGE__", simulation_topbar_badge)
        .replace("__SIMULATION_WATERMARK__", simulation_watermark)
        .replace("__SIMULATION_MAP_LEGEND__", simulation_map_legend)
        .replace("__SIMULATION_PANEL__", simulation_panel)
        .replace("__SIMULATION_SCENARIO_SCRIPT__", simulation_scenario_script)
        .replace("__MAPS_CONFIGURED__", "true" if maps_api_key else "false")
        .replace(
            "__DASHBOARD_SIMULATION_ENABLED__",
            "true" if simulation_enabled else "false",
        )
        .replace(
            "__EXPERIMENTAL_MOTION_ENABLED__",
            "true" if experimental_motion_enabled else "false",
        )
    )