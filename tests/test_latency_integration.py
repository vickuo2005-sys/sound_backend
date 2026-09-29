from pathlib import Path
import asyncio
from concurrent.futures import Future, ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
import main
from services.latency_diagnostics import LatencyDiagnostics

ROOT = Path(__file__).resolve().parents[1]


def test_latency_instrumentation_compiles_and_is_wired() -> None:
    main = (ROOT / "main.py").read_text(encoding="utf-8")
    solver = (ROOT / "services" / "localization" / "timestamp_tdoa.py").read_text(encoding="utf-8")
    html = (ROOT / "templates" / "dashboard_v2_4.html").read_text(encoding="utf-8")

    compile(main, "main.py", "exec")
    compile(solver, "timestamp_tdoa.py", "exec")
    assert 'from services.latency_diagnostics import latency_diagnostics' in main
    assert '"latency_diagnostics": latency_snapshot' in main
    assert '"post_ingest_queue_wait"' not in main or 'job_started(' in main
    assert 'latency_diagnostics.record("event_db_write"' in main
    assert 'latency_diagnostics.record("event_fusion"' in main or '"event_fusion",' in main
    assert 'latency_diagnostics.record("tdoa_solver"' in solver or '"tdoa_solver",' in solver
    assert 'latencyDiagnosticsList' in html
    assert 'latencyDiagnosticsBreakdown' in html
    for stage in ('fusion_lock_wait', 'fusion_observation_load', 'fusion_compute',
                  'active_tracking_association', 'event_db_write', 'device_status_db_upsert'):
        assert stage in html or stage in main
    assert 'function renderLatencyDiagnostics()' in html
    assert 'performance.now()-browserStarted' in html


def test_dashboard_reports_browser_handler_not_network_delay() -> None:
    html = (ROOT / "templates" / "dashboard_v2_4.html").read_text(encoding="utf-8")
    assert "Browser message handler" in html
    assert "function browserLatencyPercentile(" in html


@pytest.fixture
def diagnostics(monkeypatch):
    sampler = LatencyDiagnostics()
    monkeypatch.setattr(main, "latency_diagnostics", sampler)
    return sampler


def schedule(kind):
    if kind == "post_ingest":
        main.schedule_event_post_ingest("test", "aircraft", False)
    else:
        main.schedule_device_event_status_update(SimpleNamespace(event_id="test", device_id="test"))


@pytest.mark.parametrize("kind", ["post_ingest", "device_status"])
@pytest.mark.parametrize("outcome", ["success", "exception", "closed_loop"])
def test_worker_lifecycle(monkeypatch, diagnostics, kind, outcome):
    callbacks = []
    def call_soon(callback):
        if outcome == "closed_loop":
            raise RuntimeError("closed")
        callbacks.append(callback)
    def work(*args):
        if outcome == "exception":
            raise ValueError("test failure")
        return None
    monkeypatch.setattr(main, "process_event_post_ingest", work)
    monkeypatch.setattr(main, "upsert_device_event_status", work)
    monkeypatch.setattr(main, "update_device_status_cache_row", lambda row: None)
    ticks = iter(
        [10.25, 10.75]
        if kind == "post_ingest"
        else [10.25, 10.5, 10.75, 10.75]
    )
    monkeypatch.setattr(main, "monotonic", lambda: next(ticks))
    diagnostics.job_enqueued(kind)
    loop = SimpleNamespace(call_soon_threadsafe=call_soon)
    if kind == "post_ingest":
        main.run_event_post_ingest_worker(loop, "test", "aircraft", False, 10)
    else:
        main.run_device_event_status_worker(loop, SimpleNamespace(event_id="test", device_id="test"), 10)
    snapshot = diagnostics.snapshot()
    assert snapshot["pending_jobs"][kind] == 0
    assert snapshot["stages"][f"{kind}_queue_wait"]["last_ms"] == 250
    expected_worker_ms = 250 if kind == "device_status" and outcome == "exception" else 500
    assert snapshot["stages"][f"{kind}_worker"]["last_ms"] == expected_worker_ms
    assert len(callbacks) == (1 if outcome == "success" else 0)


@pytest.mark.parametrize("kind", ["post_ingest", "device_status"])
@pytest.mark.parametrize("cancel", [False, True])
def test_submit_failure_and_queued_cancellation(monkeypatch, diagnostics, kind, cancel):
    future = Future()
    def submit(*args):
        if not cancel:
            raise RuntimeError("executor shut down")
        return future
    monkeypatch.setattr(main, "post_ingest_executor", SimpleNamespace(submit=submit))
    if kind == "device_status":
        monkeypatch.setattr(main, "device_status_executor", SimpleNamespace(submit=submit))
    async def run():
        schedule(kind)
    asyncio.run(run())
    if cancel:
        assert diagnostics.snapshot()["pending_jobs"][kind] == 1
        assert future.cancel()
    snapshot = diagnostics.snapshot()
    assert snapshot["pending_jobs"][kind] == 0
    assert snapshot["stages"] == {}


@pytest.mark.parametrize("kind", ["post_ingest", "device_status"])
def test_actual_executor_queue(monkeypatch, diagnostics, kind):
    gate, occupied = Event(), Event()
    def block():
        occupied.set()
        assert gate.wait(5)
    monkeypatch.setattr(main, "process_event_post_ingest", lambda *args: {})
    monkeypatch.setattr(main, "upsert_device_event_status", lambda *args: None)
    monkeypatch.setattr(main, "update_device_status_cache_row", lambda row: None)
    with ThreadPoolExecutor(max_workers=1) as executor:
        executor.submit(block)
        assert occupied.wait(5)
        monkeypatch.setattr(main, "post_ingest_executor", executor)
        if kind == "device_status":
            monkeypatch.setattr(main, "device_status_executor", executor)
        try:
            async def run():
                schedule(kind)
            asyncio.run(run())
            assert diagnostics.snapshot()["pending_jobs"][kind] == 1
        finally:
            gate.set()
    snapshot = diagnostics.snapshot()
    assert snapshot["pending_jobs"][kind] == 0
    assert snapshot["stages"][f"{kind}_queue_wait"]["count"] == 1
    assert snapshot["stages"][f"{kind}_worker"]["count"] == 1


def test_actual_runtime_api_and_dashboard(diagnostics, monkeypatch):
    monkeypatch.setattr(main, "use_postgres", lambda: False)
    diagnostics.record("event_db_write", 12)
    client = TestClient(main.app)
    response = client.get("/runtime-status")
    assert response.status_code == 200
    assert response.json()["latency_diagnostics"] == diagnostics.snapshot()
    assert response.json()["latency_diagnostics"]["stages"]["event_db_write"]["p95_ms"] == 12
    assert response.json()["device_status_workers"] == main.DEVICE_STATUS_WORKERS
    assert "recent_traces" in response.json()["latency_diagnostics"]
    assert client.get("/health").status_code == 200


@pytest.mark.parametrize("fails", [False, True])
def test_websocket_broadcast_records_even_on_failure(monkeypatch, diagnostics, fails):
    received = []
    async def broadcast(message):
        received.append(message)
        if fails:
            raise RuntimeError("client disconnected")
    monkeypatch.setattr(main.dashboard_manager, "broadcast", broadcast)
    ticks = iter([1, 1.25])
    monkeypatch.setattr(main, "monotonic", lambda: next(ticks))
    message = {"type": "location_update", "device_id": "test"}
    asyncio.run(main.safe_dashboard_broadcast(message))
    assert received == [message]
    assert diagnostics.snapshot()["stages"]["websocket_broadcast"]["last_ms"] == 250


def test_localization_stage_boundaries(monkeypatch, diagnostics):
    monkeypatch.setattr(main, "LOCALIZATION_ENABLED", True)
    monkeypatch.setattr(main, "TRACKING_ENABLED", True)
    group = {"observations": [{"device_id": "test"}], "label": "aircraft"}
    monkeypatch.setattr(main, "get_event_fusion_group", lambda _: group)
    monkeypatch.setattr(main, "localize_observations", lambda *args, **kwargs: {})
    monkeypatch.setattr(main, "save_localization_result", lambda *args: {"id": "saved"})
    monkeypatch.setattr(main, "process_tracking_for_localization", lambda *args, **kwargs: {"id": "track"})
    ticks = iter(range(10))
    monkeypatch.setattr(main, "monotonic", lambda: next(ticks))
    result = main.process_event_group_localization("group")
    assert result == {"localization": {"id": "saved"}, "track": {"id": "track"}}
    stages = diagnostics.snapshot()["stages"]
    for key in ["localization_group_load", "localization_compute", "localization_db_save", "localization_tracking"]:
        assert stages[key]["last_ms"] == 1000
    assert stages["localization_pipeline"]["last_ms"] == 9000


@pytest.mark.parametrize("fails", [False, True])
def test_fusion_and_pipeline_timings(monkeypatch, diagnostics, fails):
    def fusion(*args):
        if fails:
            raise ValueError("fusion failure")
        return None
    monkeypatch.setattr(main, "process_event_fusion_for_event", fusion)
    monkeypatch.setattr(main, "with_realtime_alert_timing", lambda value: value)
    ticks = iter([0, 1, 2, 3])
    monkeypatch.setattr(main, "monotonic", lambda: next(ticks))
    main.process_event_post_ingest("test", "noise", False)
    stages = diagnostics.snapshot()["stages"]
    assert stages["event_fusion"]["last_ms"] == 1000
    assert stages["post_ingest_pipeline"]["last_ms"] == 3000
    assert diagnostics.snapshot()["recent_traces"][0]["event_id"] == "test"
    assert diagnostics.snapshot()["recent_traces"][0]["total_ms"] == 3000


def test_db_sample_survives_later_lookup_failure(monkeypatch, diagnostics):
    monkeypatch.setattr(main, "save_event_with_inserted", lambda *args: (1, True))
    def lookup():
        raise RuntimeError("lookup failed after commit")
    monkeypatch.setattr(main, "list_device_fixed_locations_for_ingest", lookup)
    ticks = iter([0, .125, .2])
    monkeypatch.setattr(main, "monotonic", lambda: next(ticks))
    event = SimpleNamespace(latency_trace={})
    with pytest.raises(RuntimeError, match="lookup failed"):
        main.process_event_initial_submission(event)
    assert diagnostics.snapshot()["stages"]["event_db_write"]["last_ms"] == 125


def test_direct_device_worker_does_not_consume_queued_job(monkeypatch, diagnostics):
    diagnostics.job_enqueued("device_status")
    monkeypatch.setattr(main, "upsert_device_event_status", lambda *args: None)
    monkeypatch.setattr(main, "update_device_status_cache_row", lambda *args: None)
    main.run_device_event_status_worker(SimpleNamespace(call_soon_threadsafe=lambda cb: None), None)
    assert diagnostics.snapshot()["pending_jobs"]["device_status"] == 1
    assert "device_status_queue_wait" not in diagnostics.snapshot()["stages"]


def test_event_api_initial_submission_sample(monkeypatch, diagnostics):
    monkeypatch.setenv("UPLOAD_TOKEN", "test-only")
    def initial(event):
        return {"db_id": 1, "device_row": None, "is_existing_event": True,
                "saved_event": {}, "created_at": main.current_time_iso(),
                "db_duration_ms": 1, "fixed_location_duration_ms": 0,
                "fixed_location_cache_stale": False}
    monkeypatch.setattr(main, "process_event_initial_submission", initial)
    monkeypatch.setattr(main, "schedule_event_post_ingest", lambda *args: None)
    monkeypatch.setattr(main, "schedule_dashboard_broadcast", lambda *args, **kwargs: None)
    response = TestClient(main.app).post("/events", headers={"x-upload-token": "test-only"},
        json={"event_id": "latency-test", "device_id": "test", "timestamp": main.current_time_iso(), "label": "noise"})
    assert response.status_code == 200
    stage = diagnostics.snapshot()["stages"]["event_initial_submission"]
    assert stage["count"] == 1
    assert stage["last_ms"] >= 0


@pytest.mark.parametrize("fails", [False, True])
def test_solver_span_success_and_exception(monkeypatch, diagnostics, fails):
    from services.localization import timestamp_tdoa as solver
    from tools.test_timestamp_tdoa import synthetic_observations
    monkeypatch.setattr(solver, "latency_diagnostics", diagnostics)
    if fails:
        def broken(*args, **kwargs):
            raise ValueError("solver failure")
        # scipy is imported lazily inside the solver.
        import scipy.optimize
        monkeypatch.setattr(scipy.optimize, "least_squares", broken)
    ticks = iter([10, 10.025])
    monkeypatch.setattr(solver, "monotonic", lambda: next(ticks))
    observations, _ = synthetic_observations()
    result = solver.estimate_timestamp_tdoa(observations)
    assert result["status"] == ("FALLBACK" if fails else "SUCCESS")
    assert diagnostics.snapshot()["stages"]["tdoa_solver"]["last_ms"] == pytest.approx(25)
