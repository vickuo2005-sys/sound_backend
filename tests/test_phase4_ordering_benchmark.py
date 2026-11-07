from tools.benchmark_phase4_ordering import run_benchmark


def test_sequence_mailbox_recovers_completion_order_without_two_second_delay() -> None:
    cases = run_benchmark()
    for case_name in (
        "case_1_E2_E3_E1_one_second",
        "case_2_exact_hop_E2_E3_E1",
        "case_3_mild_jitter",
        "case_4_heavy_jitter",
    ):
        options = cases[case_name]
        sequence = options["B_sequence_gate_serialized_mailbox"]
        reorder = options["C_event_time_reorder_2000_ms"]
        assert sequence["recovered_measurements"] >= reorder["recovered_measurements"]
        assert sequence["late_discard"] == 0
        assert sequence["added_latency_p95_ms"] < reorder["added_latency_p95_ms"]


def test_current_parallel_reproduces_late_discard_for_e2_e3_e1() -> None:
    result = run_benchmark()["case_1_E2_E3_E1_one_second"]

    assert result["A_current_parallel"]["recovered_measurements"] == 2
    assert result["A_current_parallel"]["late_discard"] == 1
    assert result["B_sequence_gate_serialized_mailbox"]["recovered_measurements"] == 3


def test_two_tracks_are_not_combined_into_one_global_pending_key() -> None:
    result = run_benchmark()["case_7_two_independent_tracks"]
    sequence = result["B_sequence_gate_serialized_mailbox"]

    assert sequence["recovered_measurements"] == 4
    assert sequence["max_pending"] <= 2
    assert "per-track" in sequence["complexity"]
