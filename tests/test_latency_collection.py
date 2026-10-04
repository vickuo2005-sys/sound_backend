import pytest
from services.latency_diagnostics import LatencyDiagnostics
from tools.collect_latency_diagnostics import validate_runtime


def test_collector_accepts_empty_and_populated_samples():
    sampler = LatencyDiagnostics()
    payload = {"build": {"render_git_commit": "a" * 40}, "latency_diagnostics": sampler.snapshot()}
    assert validate_runtime(payload, "a" * 40)["stages"] == {}
    sampler.record("event_db_write", 10)
    payload["latency_diagnostics"] = sampler.snapshot()
    assert validate_runtime(payload, "a" * 40)["stages"]["event_db_write"]["count"] == 1


def test_collector_rejects_wrong_commit():
    with pytest.raises(ValueError, match="commit"):
        validate_runtime({"build": {"render_git_commit": "b" * 40}}, "a" * 40)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1, "2", True])
def test_collector_rejects_invalid_duration(value):
    sampler = LatencyDiagnostics()
    sampler.record("stage", 1)
    snapshot = sampler.snapshot()
    snapshot["stages"]["stage"]["p95_ms"] = value
    with pytest.raises(ValueError, match="duration"):
        validate_runtime({"build": {"render_git_commit": "a" * 40}, "latency_diagnostics": snapshot}, "a" * 40)
