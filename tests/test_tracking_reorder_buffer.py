from __future__ import annotations

from services.tracking.reorder_buffer import TrackingReorderBuffer


def offered_times(
    buffer: TrackingReorderBuffer,
    order: list[tuple[str, float]],
) -> tuple[list[float], list[str]]:
    emitted: list[float] = []
    discarded: list[str] = []
    for observation_id, event_time_ms in order:
        result = buffer.offer(
            "region-a",
            observation_id=observation_id,
            event_time_ms=event_time_ms,
            payload={"event_time_ms": event_time_ms},
        )
        emitted.extend(item.event_time_ms for item in result.ready)
        if result.discarded_reason:
            discarded.append(result.discarded_reason)
    emitted.extend(item.event_time_ms for item in buffer.flush_key("region-a"))
    return emitted, discarded


def test_in_order_observations_remain_in_order() -> None:
    emitted, discarded = offered_times(
        TrackingReorderBuffer(500),
        [("e1", 1000), ("e2", 1200), ("e3", 1400)],
    )

    assert emitted == [1000, 1200, 1400]
    assert discarded == []


def test_mild_out_of_order_is_recovered_by_300_and_500_ms() -> None:
    for window_ms in (300, 500):
        emitted, discarded = offered_times(
            TrackingReorderBuffer(window_ms),
            [("e2", 1200), ("e1", 1000), ("e3", 1400)],
        )
        assert emitted == [1000, 1200, 1400]
        assert discarded == []


def test_heavy_out_of_order_within_window_is_recovered() -> None:
    emitted, discarded = offered_times(
        TrackingReorderBuffer(500),
        [("e3", 1400), ("e2", 1200), ("e1", 1000)],
    )

    assert emitted == [1000, 1200, 1400]
    assert discarded == []


def test_e2_e3_e1_one_second_spacing_exceeds_300_and_500_ms_window() -> None:
    for window_ms in (300, 500):
        emitted, discarded = offered_times(
            TrackingReorderBuffer(window_ms),
            [("e2", 2000), ("e3", 3000), ("e1", 1000)],
        )
        assert emitted == [2000, 3000]
        assert discarded == ["arrived_behind_emitted_watermark"]


def test_late_arrival_is_counted_after_watermark_emission() -> None:
    buffer = TrackingReorderBuffer(300)
    buffer.offer(
        "region-a",
        observation_id="e2",
        event_time_ms=2000,
        payload={},
    )
    emitted = buffer.offer(
        "region-a",
        observation_id="e3",
        event_time_ms=3000,
        payload={},
    )
    late = buffer.offer(
        "region-a",
        observation_id="e1",
        event_time_ms=1000,
        payload={},
    )

    assert [item.observation_id for item in emitted.ready] == ["e2"]
    assert late.discarded_reason == "arrived_behind_emitted_watermark"
    assert buffer.metrics()["late_discarded"] == 1


def test_duplicate_observation_id_is_discarded() -> None:
    buffer = TrackingReorderBuffer(500)
    buffer.offer(
        "region-a",
        observation_id="e1",
        event_time_ms=1000,
        payload={},
    )
    duplicate = buffer.offer(
        "region-a",
        observation_id="e1",
        event_time_ms=1000,
        payload={},
    )

    assert duplicate.discarded_reason == "duplicate"
    assert buffer.metrics()["duplicate_discarded"] == 1


def test_missing_observation_does_not_block_tail_flush() -> None:
    emitted, discarded = offered_times(
        TrackingReorderBuffer(500),
        [("e1", 1000), ("e3", 1400)],
    )

    assert emitted == [1000, 1400]
    assert discarded == []
