"""Staging-only write-freeze policy and route inventory.

The policy is deliberately fail-closed: the flag is ignored unless APP_ENV is
exactly ``staging``.  This module contains no database or network side effects
so it can be tested independently of the application.
"""

from __future__ import annotations

from enum import StrEnum


class RouteClass(StrEnum):
    READ_ONLY = "READ_ONLY"
    WRITE_BLOCKED_DURING_FREEZE = "WRITE_BLOCKED_DURING_FREEZE"
    EXEMPT_INTERNAL_IF_REQUIRED = "EXEMPT_INTERNAL_IF_REQUIRED"


def freeze_is_active(app_env: str | None, requested: bool) -> bool:
    """Enable the freeze only for the explicit staging environment."""

    return str(app_env or "").strip().lower() == "staging" and bool(requested)


def classify_route(method: str, path: str) -> RouteClass:
    """Classify HTTP paths whose handlers can mutate runtime state.

    ``GET /tracks`` and ``GET /device-command/{device_id}`` are intentionally
    blocked because their existing handlers perform stale-track cleanup or
    device-status upserts respectively.
    """

    method = method.upper()
    path = path.rstrip("/") or "/"
    if method == "GET":
        if path == "/device-command" or path.startswith("/device-command/"):
            return RouteClass.WRITE_BLOCKED_DURING_FREEZE
        return RouteClass.READ_ONLY
    if method == "POST" and path == "/diagnostics/db-latency":
        return RouteClass.EXEMPT_INTERNAL_IF_REQUIRED
    if method == "POST" and path == "/observations/shadow":
        # Shadow ingest is bounded in-memory state; it does not write the
        # application database.  Its optional shadow tracker is also in-memory.
        return RouteClass.EXEMPT_INTERNAL_IF_REQUIRED
    if method in {"POST", "PUT", "PATCH", "DELETE"}:
        return RouteClass.WRITE_BLOCKED_DURING_FREEZE
    return RouteClass.READ_ONLY


def write_quiescent(*, active_write_requests: int, pending_jobs: dict[str, int]) -> bool:
    """Return whether tracked request and background write work is drained."""

    return active_write_requests == 0 and sum(int(value or 0) for value in pending_jobs.values()) == 0

