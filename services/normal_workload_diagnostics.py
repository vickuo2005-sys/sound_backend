"""Staging-only Phase3E HTTP observation; no payload reads or metrics writes."""
from contextvars import ContextVar
import json
import logging
import os
import re
from time import perf_counter
from urllib.parse import parse_qs

_current = ContextVar("phase3e_request", default=None)
_identifier = re.compile(r"p3e_[A-Za-z0-9_-]{1,120}\Z")
log = logging.getLogger("uvicorn.error")


def mark(stage, **fields):
    trace = _current.get()
    if trace is not None:
        trace["stages"].setdefault(stage, perf_counter()*1000)
        for key in ("eventId", "dbId", "nodeId", "is_listening", "app_status", "detection_active", "sequence"):
            value = fields.get(key)
            if isinstance(value, (str, int, float, bool)):
                trace[key] = value[:128] if isinstance(value, str) else value


def correlation():
    trace = _current.get()
    return {"requestId": trace["requestId"]} if trace else {}


class NormalWorkloadDiagnosticsMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if (scope.get("type") != "http" or scope.get("method") != "POST"
                or scope.get("path") not in {"/events", "/location-update", "/upload-audio"}
                or os.getenv("APP_ENV", "").lower() != "staging"):
            await self.app(scope, receive, send)
            return
        request_id = next((v.decode("ascii", errors="ignore") for k, v in scope.get("headers", []) if k.lower() == b"x-phase3e-request-id"), "")
        if not request_id and len(scope.get("query_string", b"")) <= 256:
            try:
                request_id = parse_qs(scope.get("query_string", b"").decode("ascii"), max_num_fields=4).get("phase3e_request_id", [""])[0]
            except (ValueError, UnicodeError):
                pass
        if not _identifier.fullmatch(request_id):
            await self.app(scope, receive, send)
            return
        trace = {"requestId": request_id, "path": scope["path"], "stages": {"request_received": perf_counter()*1000}}
        token = _current.set(trace)

        async def observed_send(message):
            if message["type"] == "http.response.start":
                trace["status"] = message["status"]
                mark("response_ready")
            await send(message)

        try:
            await self.app(scope, receive, observed_send)
        finally:
            mark("response_send_complete")
            _current.reset(token)
            log.info("PHASE3E_HTTP %s", json.dumps(trace, separators=(",", ":")))
