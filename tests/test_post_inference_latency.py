import time

from fastapi.testclient import TestClient

import main


def initial_submission_result(event: main.SoundEvent) -> dict:
    trace = event.latency_trace or {}
    db_started_at = main.utc_wall_time_ms()
    db_committed_at = main.utc_wall_time_ms()
    trace["db_started_at"] = db_started_at
    trace["db_start"] = db_started_at
    trace["db_committed_at"] = db_committed_at
    trace["db_complete"] = db_committed_at
    saved_event = main.fast_saved_event_payload(event, 101, main.current_time_iso())
    return {
        "db_id": 101,
        "device_row": {
            "device_id": event.device_id,
            "last_event_at": main.current_time_iso(),
            "is_listening": True,
        },
        "is_existing_event": False,
        "saved_event": saved_event,
        "created_at": main.current_time_iso(),
        "db_duration_ms": 2.25,
        "fixed_location_duration_ms": 0.15,
        "fixed_location_cache_stale": False,
    }


def test_events_traces_fast_ingest_and_does_not_wait_for_post_ingest(
    monkeypatch,
) -> None:
    monkeypatch.setenv("UPLOAD_TOKEN", "latency-token")
    monkeypatch.setattr(main, "process_event_initial_submission", initial_submission_result)
    monkeypatch.setattr(main, "schedule_device_event_status_update", lambda event: None)
    broadcasts: list[dict] = []
    monkeypatch.setattr(
        main,
        "schedule_dashboard_broadcast",
        lambda message, context="dashboard": broadcasts.append(message),
    )

    post_ingest_finished = False

    def slow_post_ingest(*args, **kwargs) -> dict:
        nonlocal post_ingest_finished
        time.sleep(0.2)
        post_ingest_finished = True
        return {}

    monkeypatch.setattr(main, "process_event_post_ingest", slow_post_ingest)
    client = TestClient(main.app)
    started = time.perf_counter()
    response = client.post(
        "/events",
        headers={"x-upload-token": "latency-token"},
        json={
            "event_id": "trace-event-1",
            "trace_id": "trace-1",
            "latency_trace": {
                "trace_id": "trace-1",
                "ai_finished_at": main.utc_wall_time_ms() - 10,
                "http_request_started_at": main.utc_wall_time_ms() - 5,
            },
            "device_id": "node_A01",
            "timestamp": main.current_time_iso(),
            "label": "aircraft",
        },
    )
    elapsed = time.perf_counter() - started

    assert response.status_code == 200
    assert elapsed < 0.15
    assert post_ingest_finished is False
    assert response.headers["server-timing"].startswith("db;dur=2.25")
    body = response.json()
    assert body["trace_id"] == "trace-1"
    assert body["latency_trace"]["backend_received_at"] > 0
    assert body["latency_trace"]["backend_received"] > 0
    assert body["latency_trace"]["db_committed_at"] > 0
    assert body["latency_trace"]["db_complete"] > 0
    assert body["latency_trace"]["event_trigger_scheduled_at"] > 0
    assert body["latency_trace"]["ws_schedule"] > 0
    assert body["latency_trace"]["post_ingest_enqueued_at"] > 0
    assert body["latency_trace"]["ingest_response_started_at"] > 0
    assert body["latency_trace"]["response_start"] > 0
    assert body["server_timing_ms"]["server_non_db"] >= 0
    assert broadcasts[0]["type"] == "event_trigger"
    assert broadcasts[0]["event_id"] == "trace-event-1"

    time.sleep(0.25)
    assert post_ingest_finished is True


def test_events_db_failure_never_returns_false_success(monkeypatch) -> None:
    monkeypatch.setenv("UPLOAD_TOKEN", "latency-token")

    def fail_initial_submission(event: main.SoundEvent) -> dict:
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(main, "process_event_initial_submission", fail_initial_submission)
    client = TestClient(main.app)
    response = client.post(
        "/events",
        headers={"x-upload-token": "latency-token"},
        json={
            "event_id": "trace-event-failure",
            "device_id": "node_A01",
            "timestamp": main.current_time_iso(),
            "label": "aircraft",
        },
    )

    assert response.status_code == 500
    assert response.json()["detail"] == "db_event_write_error"


def test_stale_fixed_location_cache_does_not_block_fast_ingest(monkeypatch) -> None:
    cached_rows = [
        {
            "device_id": "node_A01",
            "latitude": 25.04,
            "longitude": 121.53,
            "location_source": "manual_map",
        }
    ]
    loads = 0

    def load_rows() -> list[dict]:
        nonlocal loads
        loads += 1
        return []

    monkeypatch.setattr(main, "FAST_EVENT_INGEST_ENABLED", True)
    monkeypatch.setattr(main, "DEVICE_FIXED_LOCATION_CACHE_TTL_SECONDS", 60.0)
    monkeypatch.setattr(main, "use_postgres", lambda: True)
    monkeypatch.setattr(main, "_load_device_fixed_locations", load_rows)
    monkeypatch.setattr(
        main,
        "device_fixed_location_cache",
        (main.monotonic() - 61.0, cached_rows),
    )

    rows, stale = main.list_device_fixed_locations_for_ingest()

    assert stale is True
    assert rows == cached_rows
    assert loads == 0


def test_dashboard_event_trigger_renders_directly_and_records_latency() -> None:
    html = main.dashboard_v4_clean().body.decode("utf-8")
    handler = html.split("} else if (data.type === 'event_trigger') {", 1)[1]
    handler = handler.split("} else if (data.type === 'event_group') {", 1)[0]

    assert "renderAlerts();" in handler
    assert "updateDeviceMarker(device);" in handler
    assert "refreshAll();" not in handler
    assert "ws_message_received_at" in handler
    assert "event_state_updated_at" in handler
    assert "render_started_at" in handler
    assert "render_finished_at" in handler
    assert "ws_received:" in handler
    assert "render_complete:" in handler
    assert "ws_received_at_monotonic" in handler
    assert "render_complete_at_monotonic" in handler
    assert "const advancesEventState" in handler
    assert "incomingSequence >= previousSequence" in handler
    assert "&& advancesEventState" in handler
    assert ": previousDevice;" in handler
    assert "window.__postInferenceLatencyStats" in html
    assert "p50:" in html
    assert "p95:" in html
    assert "p99:" in html


def test_staging_db_latency_probe_reports_pool_and_query_timing(monkeypatch) -> None:
    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def execute(self, query: str) -> None:
            assert query == "SELECT 1 AS ok"

        def fetchone(self) -> dict:
            return {"ok": 1}

    class Connection:
        def cursor(self) -> Cursor:
            return Cursor()

        def close(self) -> None:
            return None

    monkeypatch.setenv("UPLOAD_TOKEN", "latency-token")
    monkeypatch.setattr(main, "STAGING_DB_LATENCY_PROBE_ENABLED", True)
    monkeypatch.setattr(main, "use_postgres", lambda: True)
    monkeypatch.setattr(main, "get_postgres_connection", lambda: Connection())

    response = TestClient(main.app).post(
        "/diagnostics/db-latency",
        headers={"x-upload-token": "latency-token"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert response.headers["server-timing"].startswith("db_acquire;dur=")
    assert "db_ping;dur=" in response.headers["server-timing"]
