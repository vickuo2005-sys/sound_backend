"""Opt-in staging /events timing. No payloads, secrets, DB writes or metrics I/O."""
from contextvars import ContextVar
import json
import logging
import os
import re
from time import monotonic
from urllib.parse import parse_qs

_trace = ContextVar("phase3c_http_trace", default=None)
logger = logging.getLogger(__name__)
_ID = re.compile(r"p3c_[A-Za-z0-9_-]{1,100}\Z")
_EVENT_ID = re.compile(r"[A-Za-z0-9_.:-]{1,128}\Z")


def mark(stage):
    trace = _trace.get()
    if trace is not None:
        trace["stages"].setdefault(stage, (monotonic() - trace["start"]) * 1000)


def correlate_event(event_id):
    trace = _trace.get()
    # Only valid diagnostic identifiers; never arbitrary user payload in logs.
    if trace is not None and isinstance(event_id, str) and _EVENT_ID.fullmatch(event_id):
        trace["eventId"] = event_id


class HttpRttDiagnosticsMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        request_id = next((v.decode("ascii", errors="ignore")
                           for k, v in scope.get("headers", [])
                           if k.lower() == b"x-phase3c-request-id"), "")
        # The hash-pinned normal MetadataUploadClient cannot add a diagnostic
        # header. A bounded opt-in query ID lets that exact client be measured
        # without replacing it or changing its production headers/selection.
        if (not request_id and scope.get("type") == "http"
                and scope.get("path") == "/events"
                and os.getenv("APP_ENV", "").lower() == "staging"):
            query = scope.get("query_string", b"")
            if len(query) <= 256:
                try:
                    request_id = parse_qs(query.decode("ascii"),
                                          max_num_fields=4).get("phase3c_request_id", [""])[0]
                except (ValueError, UnicodeError):
                    request_id = ""
        if not (scope["type"] == "http" and scope.get("method") == "POST"
                and scope.get("path") == "/events"
                and os.getenv("APP_ENV", "").lower() == "staging"
                and _ID.fullmatch(request_id)):
            await self.app(scope, receive, send)
            return
        trace = {"requestId": request_id, "start": monotonic(),
                 "stages": {"S0_asgi_entry": 0.0}, "requestBodyBytes": 0}
        token = _trace.set(trace)

        async def observed_receive():
            message = await receive()
            if message["type"] == "http.request":
                trace["requestBodyBytes"] += len(message.get("body", b""))
                if not message.get("more_body", False):
                    mark("body_read_complete")
            return message

        async def observed_send(message):
            if message["type"] == "http.response.start":
                mark("S5_response_ready")
                trace["status"] = message["status"]
                s = trace["stages"]
                metrics = {"phase3c_handler": s["S5_response_ready"]}
                if "S1_payload_validated" in s and "body_read_complete" in s:
                    metrics["phase3c_parse_envelope"] = s["S1_payload_validated"] - s["body_read_complete"]
                if "S2_db_start" in s and "S3_db_complete" in s:
                    metrics["phase3c_db"] = s["S3_db_complete"] - s["S2_db_start"]
                    metrics["phase3c_non_db"] = metrics["phase3c_handler"] - metrics["phase3c_db"]
                if "S4_processing_complete" in s:
                    metrics["phase3c_response"] = s["S5_response_ready"] - s["S4_processing_complete"]
                trace["metrics"] = metrics
                headers = list(message.get("headers", []))
                old = [v.decode("latin1") for k, v in headers if k.lower() == b"server-timing"]
                headers = [(k, v) for k, v in headers if k.lower() not in
                           (b"server-timing", b"x-phase3c-request-id")]
                timing = ", ".join(old + [f"{k};dur={v:.3f}" for k, v in metrics.items()])
                headers.extend([(b"server-timing", timing.encode("ascii")),
                                (b"x-phase3c-request-id", request_id.encode("ascii"))])
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, observed_receive, observed_send)
        finally:
            mark("response_send_returned")
            _trace.reset(token)
            # ASGI entry is inside the application, after proxy/server scheduling.
            # Parse envelope includes FastAPI validation/dependencies, not pure
            # JSON parsing. Broadcast is scheduled asynchronously: unavailable.
            logger.info("phase3c_http %s", json.dumps({
                k: v for k, v in trace.items() if k != "start"
            }, separators=(",", ":")))
