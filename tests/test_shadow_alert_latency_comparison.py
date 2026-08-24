from tools.compare_shadow_alert_latency import compare_reports


def report(nodes: int, joined: int, p95: float) -> dict:
    return {
        "nodes": nodes,
        "counts": {"joined": joined},
        "stages": {
            "app_http_rtt": {
                "p50_ms": p95 / 2,
                "p95_ms": p95,
                "p99_ms": p95 + 5,
                "max_ms": p95 + 10,
            }
        },
    }


def test_shadow_alert_latency_comparison_reports_on_minus_off() -> None:
    result = compare_reports(report(2, 50, 100), report(2, 50, 110))

    assert result["evidence_complete"] is True
    assert result["on_minus_off"]["app_http_rtt"]["p95_ms"] == 10
    assert result["regression_detected"] is False


def test_incomplete_sample_set_never_claims_regression_result() -> None:
    result = compare_reports(report(4, 49, 100), report(4, 50, 200))

    assert result["evidence_complete"] is False
    assert result["regression_detected"] is None
    assert result["warnings"]
