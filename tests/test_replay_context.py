from datetime import datetime, timedelta, timezone

import main
from services.event_fusion import process_event
from tools.test_event_fusion import make_connection
from tests.test_event_fusion_region import event_record


def test_fusion_coordinates_survive_tracking_diagnostics(monkeypatch):
    connection = make_connection()
    base = datetime(2026, 9, 22, tzinfo=timezone.utc)
    process_event(connection, event_record('a', 'A', 'aircraft', base, 25, 121), False, 3)
    group = process_event(connection, event_record('b', 'B', 'aircraft', base + timedelta(seconds=1), 25.1, 121.1), False, 3)
    assert group['reporting_nodes'] == [
        {'device_id': 'A', 'lat': 25, 'lng': 121},
        {'device_id': 'B', 'lat': 25.1, 'lng': 121.1},
    ]
    monkeypatch.setattr(main, 'TRACKING_ENABLED', True)
    monkeypatch.setattr(main, 'TRACK_MIN_REGION_NODES', 2)
    monkeypatch.setattr(main, 'process_tracking_measurement', lambda measurement, **kwargs: measurement)
    measurement = main.process_tracking_for_event_group_region(group)
    diagnostics = main.tracking_point_diagnostics(measurement)
    assert diagnostics['reporting_nodes'] == group['reporting_nodes']
    assert diagnostics['region_geojson'] == group['region_geojson']
    assert diagnostics['source'] == 'event_group_region'
    connection.close()
