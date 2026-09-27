from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_latency_instrumentation_compiles_and_is_wired() -> None:
    main = (ROOT / "main.py").read_text(encoding="utf-8")
    solver = (ROOT / "services" / "localization" / "timestamp_tdoa.py").read_text(encoding="utf-8")
    html = (ROOT / "templates" / "dashboard_v2_4.html").read_text(encoding="utf-8")

    compile(main, "main.py", "exec")
    compile(solver, "timestamp_tdoa.py", "exec")
    assert 'from services.latency_diagnostics import latency_diagnostics' in main
    assert '"latency_diagnostics": latency_diagnostics.snapshot()' in main
    assert '"post_ingest_queue_wait"' not in main or 'job_started(' in main
    assert 'latency_diagnostics.record("event_db_write"' in main
    assert 'latency_diagnostics.record("event_fusion"' in main or '"event_fusion",' in main
    assert 'latency_diagnostics.record("tdoa_solver"' in solver or '"tdoa_solver",' in solver
    assert 'latencyDiagnosticsList' in html
    assert 'function renderLatencyDiagnostics()' in html
    assert 'performance.now()-browserStarted' in html


def test_dashboard_reports_browser_handler_not_network_delay() -> None:
    html = (ROOT / "templates" / "dashboard_v2_4.html").read_text(encoding="utf-8")
    assert "Browser message handler" in html
    assert "function browserLatencyPercentile(" in html
