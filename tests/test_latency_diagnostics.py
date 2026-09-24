from services.latency_diagnostics import LatencyDiagnostics


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


def test_latency_diagnostics_ignores_invalid_samples() -> None:
    diagnostics = LatencyDiagnostics()
    diagnostics.record("x", None)
    diagnostics.record("x", -1)
    diagnostics.record("", 10)
    assert diagnostics.snapshot()["stages"] == {}
