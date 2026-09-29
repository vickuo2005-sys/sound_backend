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


def test_correlated_trace_is_bounded_and_includes_stage_durations():
    diagnostics = LatencyDiagnostics()
    diagnostics.begin_trace("evt-1")
    diagnostics.record("fusion_compute", 12.5)
    diagnostics.record("event_db_commit", 3)
    diagnostics.finish_trace(20)
    trace = diagnostics.snapshot()["recent_traces"][0]
    assert trace["event_id"] == "evt-1"
    assert trace["total_ms"] == 20
    assert trace["stages"] == {"fusion_compute": 12.5, "event_db_commit": 3.0}
    diagnostics.reset()
    assert diagnostics.snapshot()["recent_traces"] == []


def test_trace_keeps_repeated_stages_and_pool_accounting():
    diagnostics = LatencyDiagnostics()
    diagnostics.begin_trace("evt-repeat")
    diagnostics.record("fusion_group_save", 10)
    diagnostics.record("fusion_group_save", 20)
    diagnostics.record_pool_acquisition(3, "fusion_group_lookup")
    diagnostics.record_pool_acquisition(7, "fusion_group_save")
    diagnostics.record_pool_release(30, "fusion_group_save")
    diagnostics.finish_trace(100)
    trace = diagnostics.snapshot()["recent_traces"][0]
    assert trace["stage_samples"]["fusion_group_save"] == [10.0, 20.0]
    assert trace["postgres_pool_acquisition_count"] == 2
    assert trace["postgres_pool_wait_total_ms"] == 10.0
    assert trace["postgres_pool_wait_max_ms"] == 7.0
    assert trace["postgres_holds"][0]["duration_ms"] == 30.0


def test_trace_residual_accounting_is_explicit():
    diagnostics = LatencyDiagnostics()
    diagnostics.begin_trace("evt-residual")
    diagnostics.record("fusion_lock_wait", 10)
    diagnostics.record("fusion_compute", 20)
    diagnostics.record("event_fusion", 100)
    diagnostics.record("active_tracking_source_load", 5)
    diagnostics.record("active_alert_tracking", 25)
    diagnostics.finish_trace(125)
    trace = diagnostics.snapshot()["recent_traces"][0]
    assert trace["stages"]["fusion_unaccounted_ms"] == 70
    assert trace["stages"]["tracking_unaccounted_ms"] == 20


def test_fusion_transaction_accounting_is_non_overlapping():
    diagnostics = LatencyDiagnostics()
    diagnostics.begin_trace("evt-transaction")
    diagnostics.record("fusion_observation_load", 10)
    diagnostics.record("fusion_lock_wait", 5)
    diagnostics.record("fusion_compute", 7)
    diagnostics.record("postgres_transaction_commit", 3)
    diagnostics.record("fusion_transaction_commit", 3)
    diagnostics.record_pool_release(50, "fusion_transaction")
    diagnostics.record("event_fusion", 60)
    diagnostics.finish_trace(60)
    stages = diagnostics.snapshot()["recent_traces"][0]["stages"]
    assert stages["fusion_transaction_sql_ms"] == 10
    assert stages["fusion_transaction_lock_ms"] == 5
    assert stages["fusion_transaction_python_ms"] == 7
    assert stages["fusion_transaction_commit_ms"] == 3
    assert stages["fusion_transaction_idle_ms"] == 25


def test_fusion_transaction_commit_accounting_uses_fusion_commits_only():
    diagnostics = LatencyDiagnostics()
    diagnostics.begin_trace("evt-commit-scope")
    diagnostics.record("event_fusion", 100)
    diagnostics.record("fusion_transaction_commit", 12)
    diagnostics.record("postgres_transaction_commit", 12)
    diagnostics.record("postgres_transaction_commit", 88)
    diagnostics.finish_trace(100)
    stages = diagnostics.snapshot()["recent_traces"][0]["stages"]
    assert stages["fusion_transaction_commit_ms"] == 12
