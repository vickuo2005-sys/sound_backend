from services.latency_diagnostics import LatencyDiagnostics
from concurrent.futures import ThreadPoolExecutor
import json
import pytest


def test_latency_diagnostics_percentiles_and_queue_state() -> None:
    diagnostics = LatencyDiagnostics(max_samples_per_stage=32)
    for value in [10, 20, 30, 40, 50]:
        diagnostics.record("tdoa_solver", value)

    diagnostics.job_enqueued("post_ingest")
    diagnostics.job_enqueued("post_ingest")
    diagnostics.job_started("post_ingest", 125.0)
    diagnostics.job_finished("post_ingest", 300.0)

    snapshot = diagnostics.snapshot()
    solver = snapshot["stages"]["tdoa_solver"]
    assert solver["count"] == 5
    assert solver["p50_ms"] == 30
    assert solver["p95_ms"] > 40
    assert solver["max_ms"] == 50

    queue = snapshot["stages"]["post_ingest_queue_wait"]
    assert queue["last_ms"] == 125.0
    assert snapshot["pending_jobs"]["post_ingest"] == 1
    assert snapshot["peak_pending_jobs"]["post_ingest"] == 2
    diagnostics.job_cancelled("post_ingest")
    assert diagnostics.snapshot()["pending_jobs"]["post_ingest"] == 0


def test_latency_diagnostics_ignores_invalid_samples() -> None:
    diagnostics = LatencyDiagnostics()
    diagnostics.record("x", None)
    diagnostics.record("x", -1)
    diagnostics.record("", 10)
    assert diagnostics.snapshot()["stages"] == {}


def test_exact_percentiles_and_default_rolling_window():
    diagnostics = LatencyDiagnostics()
    for value in range(300):
        diagnostics.record("stage", value)
    snapshot = diagnostics.snapshot()
    stage = snapshot["stages"]["stage"]
    assert snapshot["sample_window"] == stage["count"] == 256
    assert stage == pytest.approx(dict(count=256, mean_ms=171.5, p50_ms=171.5,
                                     p95_ms=286.25, p99_ms=296.45, max_ms=299, last_ms=299))
    diagnostics.record("single", 42)
    assert diagnostics.snapshot()["stages"]["single"]["p99_ms"] == 42


@pytest.mark.parametrize("value", [None, -1, float("nan"), float("inf"), -float("inf"), "bad", {}, 10**1000])
def test_invalid_samples_do_not_throw_or_pollute(value):
    diagnostics = LatencyDiagnostics()
    diagnostics.record("stage", value)
    assert diagnostics.snapshot()["stages"] == {}


def test_large_finite_values_remain_json_serializable():
    diagnostics = LatencyDiagnostics()
    for _ in range(256):
        diagnostics.record("stage", 1e308)
    json.dumps(diagnostics.snapshot(), allow_nan=False)


def test_concurrent_record_snapshot_and_reset():
    diagnostics = LatencyDiagnostics()
    def run(index):
        for value in range(100):
            diagnostics.job_enqueued("jobs")
            diagnostics.record(str(index), value)
            diagnostics.job_started("jobs", 1)
            diagnostics.job_finished("jobs", 2)
            snapshot = diagnostics.snapshot()
            assert snapshot["pending_jobs"]["jobs"] >= 0
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(run, range(8)))
    snapshot = diagnostics.snapshot()
    assert snapshot["pending_jobs"] == {"jobs": 0}
    for index in range(8):
        assert snapshot["stages"][str(index)]["count"] == 100
    assert snapshot["stages"]["jobs_worker"]["count"] == 256
    diagnostics.reset()
    assert diagnostics.snapshot()["stages"] == {}
    assert diagnostics.snapshot()["pending_jobs"] == {}
    assert diagnostics.snapshot()["peak_pending_jobs"] == {}
    assert snapshot["stages"]["0"]["count"] == 100  # Detached snapshot.
