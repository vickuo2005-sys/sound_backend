from __future__ import annotations

from pathlib import Path
from urllib.parse import quote


TEMPLATE_PATH = Path(__file__).resolve().parents[1] / "templates" / "dashboard_v2_4.html"
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
) -> str:
    html = TEMPLATE_PATH.read_text(encoding="utf-8")
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
            Simulation / 模擬展示
        </button>
        """
        simulation_topbar_badge = """
        <span id="simulationTopbarBadge" class="simulation-topbar-badge" hidden>
            <strong>SIMULATION / 模擬展示</strong><span>NOT FIELD VALIDATED</span>
        </span>
        """
        simulation_watermark = """
        <div id="simulationWatermark" class="simulation-watermark" hidden>
            <strong>SIMULATION / 模擬展示</strong>
            <span>NOT FIELD VALIDATED</span>
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
                <div><strong>SIMULATION / 模擬展示</strong><span id="simulationScenarioName">approach_site_demo_v1 · NOT FIELD VALIDATED</span></div>
                <button id="simulationExitButton" class="ghost-button" type="button">Exit simulation</button>
            </div>
            <p class="simulation-disclaimer">此畫面為展示用模擬資料，不代表目前實際偵測結果或已驗證預測能力。</p>
            <div class="simulation-controls">
                <button id="simulationPlayButton" class="action-button primary" type="button">Play</button>
                <button id="simulationRestartButton" class="action-button" type="button">Restart</button>
                <label>Scenario
                    <select id="simulationScenario" class="select-control" aria-label="模擬情境">
                        <option value="approach_site_demo_v1">A · Direct Approach</option>
                        <option value="parallel_flyby_demo_v1">B · Parallel Fly-by</option>
                        <option value="departing_demo_v1">C · Departing</option>
                    </select>
                </label>
                <label>Speed
                    <select id="simulationSpeed" class="select-control" aria-label="模擬播放速度">
                        <option value="0.5">0.5×</option><option value="1" selected>1×</option><option value="2">2×</option>
                    </select>
                </label>
                <label class="simulation-follow"><input id="simulationFollowTarget" type="checkbox" checked> Follow target</label>
                <span id="simulationStateBadge" class="badge experimental">READY</span>
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
    return (
        html.replace("__MAPS_SCRIPT_TAG__", maps_script_tag)
        .replace("__SIMULATION_CONTROLS__", simulation_controls)
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
