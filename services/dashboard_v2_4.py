from __future__ import annotations

from pathlib import Path
from urllib.parse import quote


TEMPLATE_PATH = Path(__file__).resolve().parents[1] / "templates" / "dashboard_v2_4.html"


def render_dashboard_v2_4(
    *,
    maps_api_key: str,
    experimental_motion_enabled: bool,
) -> str:
    html = TEMPLATE_PATH.read_text(encoding="utf-8")
    maps_script_tag = ""
    if maps_api_key:
        maps_url = (
            "https://maps.googleapis.com/maps/api/js?"
            f"key={quote(maps_api_key)}&callback=initOperationalMap"
        )
        maps_script_tag = f'<script async defer src="{maps_url}"></script>'
    return (
        html.replace("__MAPS_SCRIPT_TAG__", maps_script_tag)
        .replace("__MAPS_CONFIGURED__", "true" if maps_api_key else "false")
        .replace(
            "__EXPERIMENTAL_MOTION_ENABLED__",
            "true" if experimental_motion_enabled else "false",
        )
    )
