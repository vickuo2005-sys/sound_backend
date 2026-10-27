import asyncio
import json
import logging
import time

from fastapi.testclient import TestClient
import pytest

import main
from services.http_rtt_diagnostics import HttpRttDiagnosticsMiddleware, mark, _trace


def stub_submission(event):
    mark("S2_db_start")
    time.sleep(0.002)
    mark("S3_db_complete")
    return {"db_id": 17, "device_row": None, "is_existing_event": False,
            "saved_event": {"label": "other"}, "db_duration_ms": 2.0,
            "fixed_location_duration_ms": 0.1, "fixed_location_cache_stale": False}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("UPLOAD_TOKEN", "phase3c-test-only-token")
    monkeypatch.setattr(main, "POST_INFERENCE_LATENCY_TRACING_ENABLED", True)
    monkeypatch.setattr(main, "process_event_initial_submission", stub_submission)
    return TestClient(main.app)


def post(client, request_id="p3c_request", **overrides):
    payload = {"event_id": "p3c_event", "device_id": "p3c_node",
               "timestamp": "2026-10-27T00:00:00Z", "label": "other", **overrides}
    return client.post("/events", headers={"x-upload-token": "phase3c-test-only-token",
                                          "x-phase3c-request-id": request_id}, json=payload)


def test_correlates_request_and_preserves_payload_and_legacy_metric(client, caplog):
    caplog.set_level(logging.INFO, logger="services.http_rtt_diagnostics")
    instrumented = post(client)
    plain = client.post("/events", headers={"x-upload-token": "phase3c-test-only-token"},
                        json={"event_id": "p3c_event", "device_id": "p3c_node",
                              "timestamp": "2026-10-27T00:00:00Z", "label": "other"})
    assert instrumented.status_code == plain.status_code == 200
    for key in ("status", "message", "event_id", "db_id"):
        assert instrumented.json()[key] == plain.json()[key]
    assert instrumented.headers["x-phase3c-request-id"] == "p3c_request"
    assert instrumented.headers["server-timing"].startswith("db;dur=2.00")
    assert "phase3c_handler;dur=" in instrumented.headers["server-timing"]
    assert "phase3c_response;dur=" in instrumented.headers["server-timing"]
    assert "phase3c_parse_envelope;dur=" in instrumented.headers["server-timing"]
    records = [r.message for r in caplog.records if r.message.startswith("phase3c_http ")]
    assert len(records) == 1
    trace = json.loads(records[0].split(" ", 1)[1])
    assert trace["requestId"] == "p3c_request" and trace["eventId"] == "p3c_event"
    assert trace["requestBodyBytes"] > 0
    assert trace["stages"]["S3_db_complete"] >= trace["stages"]["S2_db_start"]
    assert trace["metrics"]["phase3c_db"] >= 1
    assert trace["metrics"]["phase3c_handler"] >= trace["metrics"]["phase3c_db"]
    assert "phase3c-test-only-token" not in records[0]
    assert "2026-10-27T00:00:00Z" not in records[0]
    assert _trace.get() is None


@pytest.mark.parametrize("environment,request_id", [
    ("production", "p3c_req"), ("test", "p3c_req"),
    ("staging", "not-a-diagnostic-id"), ("staging", "p3c_" + "x" * 101)])
def test_no_instrumentation_without_staging_and_bounded_valid_id(client, monkeypatch, caplog,
                                                                  environment, request_id):
    monkeypatch.setenv("APP_ENV", environment)
    caplog.set_level(logging.INFO, logger="services.http_rtt_diagnostics")
    response = post(client, request_id)
    assert response.status_code == 200
    assert "x-phase3c-request-id" not in response.headers
    assert "phase3c_handler" not in response.headers.get("server-timing", "")
    assert not [r for r in caplog.records if r.message.startswith("phase3c_http ")]


def test_invalid_payload_and_auth_failure_keep_original_response(client):
    response = post(client, "p3c_invalid", event_id=None)
    assert response.status_code == 422
    assert response.headers["x-phase3c-request-id"] == "p3c_invalid"
    response = client.post("/events", headers={"x-phase3c-request-id": "p3c_auth"},
                           json={"event_id": "p3c_event", "device_id": "p3c_node",
                                 "timestamp": "2026-10-27T00:00:00Z", "label": "other"})
    assert response.status_code in (401, 403)
    assert response.headers["x-phase3c-request-id"] == "p3c_auth"


def test_db_failure_retains_db_span_and_no_false_success(client, monkeypatch, caplog):
    # Exercise the actual threaded helper's finally, not a synthetic return.
    # Fixture replaces the helper: retrieve the real function before fixture via
    # its saved module reference below, avoiding a reload of runtime globals.
    monkeypatch.setattr(main, "process_event_initial_submission", ORIGINAL_HELPER)
    def fail(*args):
        raise RuntimeError("test DB failure")
    monkeypatch.setattr(main, "save_event_with_inserted", fail)
    caplog.set_level(logging.INFO, logger="services.http_rtt_diagnostics")
    response = post(client, "p3c_failed")
    assert response.status_code == 500
    assert response.json()["detail"] == "db_event_write_error"
    assert "phase3c_db;dur=" in response.headers["server-timing"]
    assert _trace.get() is None


ORIGINAL_HELPER = main.process_event_initial_submission


def test_query_correlation_supports_existing_normal_client_without_header(client, monkeypatch):
    payload = {"event_id": "p3c_query_event", "device_id": "p3c_node",
               "timestamp": "2026-10-27T00:00:00Z", "label": "other"}
    response = client.post("/events?phase3c_request_id=p3c_query", json=payload,
                           headers={"x-upload-token": "phase3c-test-only-token"})
    assert response.status_code == 200
    assert response.headers["x-phase3c-request-id"] == "p3c_query"
    assert response.json()["event_id"] == "p3c_query_event"
    assert "phase3c_handler;dur=" in response.headers["server-timing"]
    response = client.post("/events?phase3c_request_id=p3c_query", json=payload,
                           headers={"x-upload-token": "phase3c-test-only-token",
                                    "x-phase3c-request-id": "p3c_header"})
    assert response.headers["x-phase3c-request-id"] == "p3c_header"
    for query in ["a=1&b=2&c=3&d=4&e=5", "phase3c_request_id=invalid", "x=" + "a" * 260]:
        response = client.post("/events?" + query, json=payload,
                               headers={"x-upload-token": "phase3c-test-only-token"})
        assert response.status_code == 200
        assert "x-phase3c-request-id" not in response.headers
    monkeypatch.setenv("APP_ENV", "production")
    response = client.post("/events?phase3c_request_id=p3c_query", json=payload,
                           headers={"x-upload-token": "phase3c-test-only-token"})
    assert response.status_code == 200
    assert "x-phase3c-request-id" not in response.headers


def test_parallel_asgi_contexts_do_not_cross_contaminate(monkeypatch):
    monkeypatch.setenv("APP_ENV", "staging")
    async def run():
        seen = []
        async def app(scope, receive, send):
            await receive()
            mark("S1_payload_validated")
            await asyncio.sleep(0.001)
            mark("S4_processing_complete")
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})
        middleware = HttpRttDiagnosticsMiddleware(app)
        async def request(i):
            async def receive():
                return {"type": "http.request", "body": b"{}", "more_body": False}
            async def send(message):
                if message["type"] == "http.response.start":
                    seen.append((i, dict(message["headers"])[b"x-phase3c-request-id"].decode()))
            await middleware({"type": "http", "method": "POST", "path": "/events",
                              "headers": [(b"x-phase3c-request-id", f"p3c_{i}".encode())]}, receive, send)
        await asyncio.gather(*(request(i) for i in range(20)))
        assert sorted(seen) == [(i, f"p3c_{i}") for i in range(20)]
        assert _trace.get() is None
    asyncio.run(run())
