from services.dashboard_v2_4 import render_dashboard_v2_4


def test_shared_prediction_loads_before_live_ui_even_without_simulation():
    for simulation in (False, True):
        html = render_dashboard_v2_4(maps_api_key='', experimental_motion_enabled=True, simulation_enabled=simulation)
        assert html.count('class EtaStabilizer') == 1
        assert html.count('class AlphaBetaTracker') == 1
        assert html.index('class EtaStabilizer') < html.index('class LiveEstimator')
        assert html.index('class AlphaBetaTracker') < html.index('class LiveEstimator')
        assert html.index('class LiveEstimator') < html.index('new DashboardLivePrediction.LiveEstimator()')
        assert ('class LabModel' in html) == simulation
