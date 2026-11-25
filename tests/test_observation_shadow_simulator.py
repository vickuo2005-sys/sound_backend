from tools.simulate_observation_shadow import ordering_experiment, scenario_matrix


def test_sustained_30_and_60_second_shadow_density() -> None:
    scenarios = scenario_matrix()

    for name, expected_raw, expected_control, expected_shadow in [
        ("sustained_drone_30s", 20, 3, 20),
        ("sustained_drone_60s", 40, 6, 40),
    ]:
        result = scenarios[name]
        assert result["control"]["raw_ai_observation_count"] == expected_raw
        assert result["control"]["track_point_count"] == expected_control
        assert result["shadow"]["track_point_count"] == expected_shadow
        assert result["improvement"]["point_density_multiplier"] == 6.67
        assert result["control"]["maximum_track_gap_ms"] == 10500
        assert result["shadow"]["maximum_track_gap_ms"] == 1500


def test_duplicate_missing_and_two_region_scenarios() -> None:
    scenarios = scenario_matrix()

    assert scenarios["duplicate_upload"]["shadow"]["duplicate_discard_count"] == 1
    assert scenarios["duplicate_upload"]["shadow"]["track_point_count"] == 20
    assert scenarios["missing_observation"]["shadow"]["track_point_count"] == 19
    assert scenarios["missing_observation"]["shadow"]["maximum_track_gap_ms"] == 3000
    assert scenarios["two_simultaneous_independent_regions"]["shadow"]["track_count"] == 2
    assert (
        scenarios["two_simultaneous_independent_regions"]["control"][
            "track_point_count"
        ]
        == 6
    )


def test_ordering_options_preserve_negative_1500_ms_boundary_result() -> None:
    results = ordering_experiment()
    one_hop = results["one_hop_spacing_E2_E3_E1"]

    assert one_hop["sequence_aware_serialized"]["correct_recovered_points"] == 3
    assert one_hop["sequence_aware_serialized"]["late_discard"] == 0
    assert one_hop["event_time_priority_1500_ms"]["correct_recovered_points"] == 2
    assert one_hop["event_time_priority_1500_ms"]["late_discard"] == 1
    assert one_hop["event_time_priority_2000_ms"]["correct_recovered_points"] == 3
    assert one_hop["event_time_priority_2000_ms"]["late_discard"] == 0
