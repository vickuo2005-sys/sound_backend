from services.tracking.ordering_experiments import PerKeySequenceExecutor
from services.tracking.reorder_buffer import TrackingReorderBuffer


def offer_sequence_order(order: list[int]) -> tuple[list[int], list[float]]:
    executor = PerKeySequenceExecutor(max_late_ms=500)
    emitted: list[int] = []
    latencies: list[float] = []
    for arrival_index, sequence in enumerate(order):
        arrival_ms = arrival_index * 100.0
        result = executor.offer(
            "region-a",
            observation_id=f"obs-{sequence}",
            sequence=sequence,
            event_time_ms=sequence * 1000.0,
            arrival_time_ms=arrival_ms,
            payload={},
        )
        emitted.extend(item.item.sequence for item in result.ready)
        latencies.extend(item.additional_latency_ms for item in result.ready)
    return emitted, latencies


def reorder_times(window_ms: float, order: list[tuple[str, float]]) -> tuple[list[float], int]:
    buffer = TrackingReorderBuffer(window_ms)
    emitted: list[float] = []
    for observation_id, event_time_ms in order:
        result = buffer.offer(
            "region-a",
            observation_id=observation_id,
            event_time_ms=event_time_ms,
            payload={},
        )
        emitted.extend(item.event_time_ms for item in result.ready)
    emitted.extend(item.event_time_ms for item in buffer.flush_key("region-a"))
    return emitted, int(buffer.metrics()["late_discarded"])


def test_sequence_executor_recovers_e2_e3_e1() -> None:
    emitted, latencies = offer_sequence_order([2, 3, 1])

    assert emitted == [1, 2, 3]
    assert latencies == [0.0, 200.0, 100.0]


def test_sequence_executor_skips_missing_after_bounded_wait() -> None:
    executor = PerKeySequenceExecutor(max_late_ms=500)
    first = executor.offer(
        "region-a",
        observation_id="obs-1",
        sequence=1,
        event_time_ms=1000,
        arrival_time_ms=0,
        payload={},
    )
    executor.offer(
        "region-a",
        observation_id="obs-3",
        sequence=3,
        event_time_ms=3000,
        arrival_time_ms=100,
        payload={},
    )
    flushed = executor.flush_expired("region-a", now_ms=600)

    assert [item.item.sequence for item in first.ready] == [1]
    assert [item.item.sequence for item in flushed.ready] == [3]
    assert flushed.gaps_skipped == 1


def test_sequence_executor_deduplicates_and_isolates_regions() -> None:
    executor = PerKeySequenceExecutor(max_late_ms=500)
    region_a = executor.offer(
        "region-a",
        observation_id="a-1",
        sequence=1,
        event_time_ms=1000,
        arrival_time_ms=0,
        payload={},
    )
    region_b = executor.offer(
        "region-b",
        observation_id="b-1",
        sequence=1,
        event_time_ms=1000,
        arrival_time_ms=0,
        payload={},
    )
    duplicate = executor.offer(
        "region-a",
        observation_id="a-1",
        sequence=1,
        event_time_ms=1000,
        arrival_time_ms=10,
        payload={},
    )

    assert [item.item.observation_id for item in region_a.ready] == ["a-1"]
    assert [item.item.observation_id for item in region_b.ready] == ["b-1"]
    assert duplicate.discarded_reason == "duplicate_id"


def test_1500_and_2000_ms_reorder_recover_one_second_e2_e3_e1() -> None:
    for window_ms in (1500, 2000):
        emitted, late = reorder_times(
            window_ms,
            [("e2", 2000), ("e3", 3000), ("e1", 1000)],
        )
        assert emitted == [1000, 2000, 3000]
        assert late == 0


def test_exact_1500_ms_hop_needs_more_than_1500_ms_watermark_window() -> None:
    order = [("e2", 1500), ("e3", 3000), ("e1", 0)]

    emitted_1500, late_1500 = reorder_times(1500, order)
    emitted_2000, late_2000 = reorder_times(2000, order)

    assert emitted_1500 == [1500, 3000]
    assert late_1500 == 1
    assert emitted_2000 == [0, 1500, 3000]
    assert late_2000 == 0
