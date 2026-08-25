from __future__ import annotations

import threading
from concurrent.futures import Future

import pytest

from services.tracking.ordering_experiments import PerKeySequenceExecutor
from services.tracking.serialized_mailbox import (
    MailboxCapacityError,
    PerKeySerializedMailbox,
)


def offer(
    gate: PerKeySequenceExecutor,
    key: str,
    sequence: int,
    arrival_ms: float,
    *,
    observation_id: str | None = None,
):
    return gate.offer(
        key,
        observation_id=observation_id or f"{key}-{sequence}",
        sequence=sequence,
        event_time_ms=sequence * 1500.0,
        arrival_time_ms=arrival_ms,
        payload={"sequence": sequence},
    )


def test_sequence_gap_timeout_advances_without_permanent_block() -> None:
    gate = PerKeySequenceExecutor(max_late_ms=500)

    assert [item.item.sequence for item in offer(gate, "A01:s1", 1, 0).ready] == [1]
    assert offer(gate, "A01:s1", 3, 100).ready == ()
    flushed = gate.flush_expired("A01:s1", now_ms=600)

    assert [item.item.sequence for item in flushed.ready] == [3]
    assert flushed.gaps_skipped == 1
    metrics = gate.metrics()
    assert metrics["sequence_gap_count"] == 1
    assert metrics["sequence_timeout_advance_count"] == 1


def test_sequence_recovery_and_duplicate_diagnostics() -> None:
    gate = PerKeySequenceExecutor(max_late_ms=500)

    assert offer(gate, "A01:s1", 2, 0).ready == ()
    recovered = offer(gate, "A01:s1", 1, 100)
    duplicate = offer(
        gate,
        "A01:s1",
        1,
        200,
        observation_id="A01:s1-retry-with-new-id",
    )

    assert [item.item.sequence for item in recovered.ready] == [1, 2]
    assert duplicate.discarded_reason == "duplicate_sequence"
    metrics = gate.metrics()
    assert metrics["sequence_out_of_order_count"] == 1
    assert metrics["sequence_duplicate_count"] == 1


def test_process_session_restart_sequence_one_is_not_old_duplicate() -> None:
    gate = PerKeySequenceExecutor()

    first = offer(gate, "A01:session-one", 1, 0, observation_id="obs-s1-1")
    restarted = offer(
        gate,
        "A01:session-two",
        1,
        10,
        observation_id="obs-s2-1",
    )

    assert len(first.ready) == 1
    assert len(restarted.ready) == 1
    assert gate.metrics()["current_keys"] == 2


def test_sequence_state_cleanup_is_ttl_and_max_key_bounded() -> None:
    gate = PerKeySequenceExecutor(key_ttl_ms=100, max_keys=2)
    offer(gate, "A:s", 1, 0)
    offer(gate, "B:s", 1, 10)

    assert gate.cleanup_expired(now_ms=200) == 2
    offer(gate, "C:s", 1, 210)

    metrics = gate.metrics()
    assert metrics["current_keys"] == 1
    assert metrics["expired_key_count"] == 2
    assert metrics["max_keys_seen"] <= 2


def test_same_track_mailbox_is_strictly_serialized() -> None:
    mailbox = PerKeySerializedMailbox(max_workers=2)
    release_first = threading.Event()
    second_started = threading.Event()
    order: list[str] = []

    def first() -> None:
        order.append("first-start")
        release_first.wait(timeout=2)
        order.append("first-end")

    def second() -> None:
        second_started.set()
        order.append("second")

    first_future = mailbox.submit("track-a", first)
    second_future = mailbox.submit("track-a", second)

    assert second_started.wait(timeout=0.05) is False
    release_first.set()
    first_future.result(timeout=2)
    second_future.result(timeout=2)
    assert order == ["first-start", "first-end", "second"]
    mailbox.close()


def test_independent_tracks_can_process_concurrently() -> None:
    mailbox = PerKeySerializedMailbox(max_workers=2)
    release_a = threading.Event()
    b_completed = threading.Event()

    a_future = mailbox.submit("track-a", lambda: release_a.wait(timeout=2))
    b_future = mailbox.submit("track-b", b_completed.set)

    assert b_completed.wait(timeout=1) is True
    b_future.result(timeout=1)
    release_a.set()
    a_future.result(timeout=2)
    assert mailbox.metrics()["max_keys_seen"] == 2
    mailbox.close()


def test_mailbox_depth_is_bounded_and_drop_is_explicit() -> None:
    mailbox = PerKeySerializedMailbox(max_workers=1, max_pending_per_key=2)
    release = threading.Event()
    first = mailbox.submit("track-a", lambda: release.wait(timeout=2))
    second = mailbox.submit("track-a", lambda: None)
    rejected: Future[object] = mailbox.submit("track-a", lambda: None)

    with pytest.raises(MailboxCapacityError):
        rejected.result(timeout=1)
    assert mailbox.metrics()["capacity_drop_count"] == 1
    assert mailbox.metrics()["max_pending"] == 2
    release.set()
    first.result(timeout=2)
    second.result(timeout=2)
    mailbox.close()
