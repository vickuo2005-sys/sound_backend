from html.parser import HTMLParser
from services.dashboard_v2_4 import render_dashboard_v2_4

class Elements(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
    def handle_starttag(self, tag, attrs):
        value = dict(attrs).get('id')
        if value:
            self.ids.append(value)

def test_page_split_keeps_unique_control_ids():
    html = render_dashboard_v2_4(maps_api_key='', experimental_motion_enabled=False, simulation_enabled=True)
    parser = Elements()
    parser.feed(html)
    assert len(parser.ids) == len(set(parser.ids))
    for name in ['view-dashboard', 'view-detections', 'view-simulation',
                 'overviewMapSlot', 'simulationMapSlot', 'motionHome',
                 'simulationQuickExitButton', 'simulationExitButton']:
        assert name in parser.ids

def test_simulation_flag_omits_navigation_and_exit_controls():
    html = render_dashboard_v2_4(maps_api_key='', experimental_motion_enabled=False, simulation_enabled=False)
    assert 'data-view-target="simulation"' not in html
    assert 'id="simulationQuickExitButton"' not in html

def test_maps_authentication_failure_has_coordinate_fallback():
    html = render_dashboard_v2_4(maps_api_key='test-key', experimental_motion_enabled=False)
    assert 'window.gm_authFailure' in html
    assert 'Google 地圖授權失敗' in html
