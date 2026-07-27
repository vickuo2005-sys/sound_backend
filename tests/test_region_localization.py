from services.region_localization import estimate_region


def test_single_node_region_center_equals_node_gps() -> None:
    region = estimate_region(
        [
            {
                "device_id": "node_A01",
                "latitude": 25.033,
                "longitude": 121.565,
            }
        ]
    )

    assert region["region_type"] == "single_node"
    assert region["region_center_lat"] == 25.033
    assert region["region_center_lng"] == 121.565
    assert region["region_geojson"] == {
        "type": "Point",
        "coordinates": [121.565, 25.033],
    }
    assert region["reporting_node_count"] == 1
    assert region["reporting_device_ids"] == ["node_A01"]


def test_two_node_region_is_midpoint_line_string() -> None:
    region = estimate_region(
        [
            {"device_id": "node_A01", "latitude": 25.0, "longitude": 121.0},
            {"device_id": "node_A02", "latitude": 25.2, "longitude": 121.4},
        ]
    )

    assert region["region_type"] == "segment"
    assert region["region_center_lat"] == 25.1
    assert region["region_center_lng"] == 121.2
    assert region["region_geojson"]["type"] == "LineString"
    assert region["region_geojson"]["coordinates"] == [[121.0, 25.0], [121.4, 25.2]]
    assert region["reporting_node_count"] == 2


def test_three_node_region_produces_polygon() -> None:
    region = estimate_region(
        [
            {"device_id": "node_A01", "latitude": 25.0, "longitude": 121.0},
            {"device_id": "node_A02", "latitude": 25.0, "longitude": 121.2},
            {"device_id": "node_A03", "latitude": 25.2, "longitude": 121.0},
        ]
    )

    assert region["region_type"] == "polygon"
    assert region["region_geojson"]["type"] == "Polygon"
    assert len(region["region_geojson"]["coordinates"][0]) == 4
    assert 25.0 <= region["region_center_lat"] <= 25.2
    assert 121.0 <= region["region_center_lng"] <= 121.2
    assert region["reporting_node_count"] == 3


def test_convex_hull_excludes_internal_points() -> None:
    region = estimate_region(
        [
            {"device_id": "node_A01", "latitude": 0.0, "longitude": 0.0},
            {"device_id": "node_A02", "latitude": 0.0, "longitude": 2.0},
            {"device_id": "node_A03", "latitude": 2.0, "longitude": 2.0},
            {"device_id": "node_A04", "latitude": 2.0, "longitude": 0.0},
            {"device_id": "node_A05", "latitude": 1.0, "longitude": 1.0},
        ]
    )

    assert region["region_type"] == "polygon"
    coordinates = region["region_geojson"]["coordinates"][0]
    assert [1.0, 1.0] not in coordinates
    assert len(coordinates) == 5
    assert region["reporting_node_count"] == 5


def test_duplicate_device_counts_once_with_latest_valid_gps() -> None:
    region = estimate_region(
        [
            {"device_id": "node_A01", "latitude": 25.0, "longitude": 121.0},
            {"device_id": "node_A01", "latitude": 26.0, "longitude": 122.0},
            {"device_id": "node_A02", "latitude": 26.0, "longitude": 124.0},
        ]
    )

    assert region["region_type"] == "segment"
    assert region["reporting_node_count"] == 2
    assert region["reporting_device_ids"] == ["node_A01", "node_A02"]
    assert region["region_center_lat"] == 26.0
    assert region["region_center_lng"] == 123.0


def test_missing_or_invalid_gps_is_ignored() -> None:
    region = estimate_region(
        [
            {"device_id": "node_A01", "latitude": None, "longitude": 121.0},
            {"device_id": "node_A02", "latitude": 25.0, "longitude": "bad"},
            {"device_id": "node_A03", "latitude": 25.5, "longitude": 121.5},
        ]
    )

    assert region["region_type"] == "single_node"
    assert region["reporting_device_ids"] == ["node_A03"]
    assert region["region_center_lat"] == 25.5


def test_no_valid_gps_is_unknown() -> None:
    region = estimate_region(
        [
            {"device_id": "node_A01", "latitude": None, "longitude": None},
            {"device_id": "node_A02", "latitude": 95.0, "longitude": 121.0},
        ]
    )

    assert region["region_type"] == "unknown"
    assert region["region_center_lat"] is None
    assert region["region_geojson"] is None
    assert region["reporting_node_count"] == 0


def test_collinear_three_node_region_falls_back_to_segment() -> None:
    region = estimate_region(
        [
            {"device_id": "node_A01", "latitude": 25.0, "longitude": 121.0},
            {"device_id": "node_A02", "latitude": 25.1, "longitude": 121.1},
            {"device_id": "node_A03", "latitude": 25.2, "longitude": 121.2},
        ]
    )

    assert region["region_type"] == "segment"
    assert region["region_geojson"]["type"] == "LineString"
    assert region["reporting_node_count"] == 3
