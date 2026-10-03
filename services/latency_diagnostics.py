from __future__ import annotations

import math
import threading
import sqlite3
from contextlib import contextmanager
from contextvars import ContextVar
from time import monotonic
from copy import deepcopy
from collections import deque
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class StageSummary:
    count: int
    mean_ms: float
    p50_ms: float
    p95_ms: float
    p99_ms: float
    max_ms: float
    last_ms: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "count": self.count,
            "mean_ms": self.mean_ms,
            "p50_ms": self.p50_ms,
            "p95_ms": self.p95_ms,
            "p99_ms": self.p99_ms,
            "max_ms": self.max_ms,
            "last_ms": self.last_ms,
        }


class LatencyDiagnostics:
    """Small in-process latency sampler for staging/field validation.

    This intentionally avoids database writes and external telemetry so the
    diagnostic path does not create the latency it is trying to measure.
    Samples are process-local and reset on deploy/restart.
    """

    def __init__(self, max_samples_per_stage: int = 256) -> None:
        self.max_samples_per_stage = max(16, int(max_samples_per_stage))
        self._lock = threading.RLock()
        self._samples: dict[str, deque[float]] = {}
        self._pending: dict[str, int] = {}
        self._peak_pending: dict[str, int] = {}
        self._traces: deque[dict[str, Any]] = deque(maxlen=32)
        self._trace_local = threading.local()
        self._critical_traces: deque[dict[str, Any]] = deque(maxlen=32)
        self._critical_counts: dict[str, deque[int]] = {}
        self._pool_stats: dict[str, int] = {
            "acquisitions": 0,
            "releases": 0,
            "checked_out": 0,
            "peak_checked_out": 0,
            "creation_failures": 0,
            "acquire_timeouts": 0,
        }

    @staticmethod
    def _percentile(values: list[float], percentile: float) -> float:
        if not values:
            return 0.0
        ordered = sorted(values)
        if len(ordered) == 1:
            return ordered[0]
        rank = (len(ordered) - 1) * max(0.0, min(1.0, percentile))
        low = int(math.floor(rank))
        high = int(math.ceil(rank))
        if low == high:
            return ordered[low]
        weight = rank - low
        return ordered[low] * (1.0 - weight) + ordered[high] * weight

    def record(self, stage: str, duration_ms: float | int | None) -> None:
        try:
            value = float(duration_ms) if duration_ms is not None else None
        except (TypeError, ValueError, OverflowError):
            return
        if value is None or not math.isfinite(value) or value < 0:
            return
        key = str(stage or "").strip()
        if not key:
            return
        with self._lock:
            bucket = self._samples.setdefault(
                key, deque(maxlen=self.max_samples_per_stage)
            )
            bucket.append(value)
            correlated = _critical_current.get()
            if correlated is not None and not correlated["completed"]:
                values = correlated.setdefault("stage_samples", {}).setdefault(key, [])
                if len(values) < 64:
                    values.append(value)
            trace = getattr(self._trace_local, "current", None)
            if trace is not None:
                trace["stages"][key] = value
                values = trace.setdefault("stage_samples", {}).setdefault(key, [])
                if len(values) < 64:
                    values.append(value)

    def set_trace_context(self, purpose: str | None) -> None:
        self._trace_local.context = str(purpose or "").strip() or None

    def trace_context(self) -> str | None:
        return getattr(self._trace_local, "context", None)

    def record_pool_acquisition(self, duration_ms: float, purpose: str | None = None) -> None:
        self.record("postgres_pool_acquisition", duration_ms)
        with self._lock:
            self._pool_stats["acquisitions"] += 1
            self._pool_stats["checked_out"] += 1
            self._pool_stats["peak_checked_out"] = max(
                self._pool_stats["peak_checked_out"], self._pool_stats["checked_out"]
            )
            trace = getattr(self._trace_local, "current", None)
            if trace is not None:
                item = {"duration_ms": float(duration_ms), "purpose": str(purpose or self.trace_context() or "unknown")}
                acquisitions = trace.setdefault("postgres_acquisitions", [])
                if len(acquisitions) < 32:
                    acquisitions.append(item)
                trace["postgres_pool_acquisition_count"] = trace.get("postgres_pool_acquisition_count", 0) + 1
                trace["postgres_pool_wait_total_ms"] = trace.get("postgres_pool_wait_total_ms", 0.0) + float(duration_ms)
                trace["postgres_pool_wait_max_ms"] = max(trace.get("postgres_pool_wait_max_ms", 0.0), float(duration_ms))

    def record_pool_release(self, hold_ms: float, purpose: str | None = None) -> None:
        self.record("postgres_connection_hold", hold_ms)
        self.record("postgres_transaction_duration", hold_ms)
        with self._lock:
            self._pool_stats["releases"] += 1
            self._pool_stats["checked_out"] = max(0, self._pool_stats["checked_out"] - 1)
            trace = getattr(self._trace_local, "current", None)
            if trace is not None:
                holds = trace.setdefault("postgres_holds", [])
                if len(holds) < 32:
                    holds.append({"duration_ms": float(hold_ms), "purpose": str(purpose or self.trace_context() or "unknown")})

    def record_pool_timeout(self) -> None:
        with self._lock:
            self._pool_stats["acquire_timeouts"] += 1

    def record_pool_creation_failure(self) -> None:
        with self._lock:
            self._pool_stats["creation_failures"] += 1

    def pool_snapshot(self, pool: Any = None, *, min_size: int = 1, max_size: int = 20) -> dict[str, Any]:
        with self._lock:
            result = dict(self._pool_stats)
        result.update({"min_size": int(min_size), "max_size": int(max_size), "waiting_requests": 0})
        if pool is not None:
            try:
                used = getattr(pool, "_used", {})
                idle = getattr(pool, "_pool", [])
                result["checked_out"] = len(used)
                result["idle_connections"] = len(idle)
                result["available_connections"] = len(idle)
                result["pool_total_connections"] = len(used) + len(idle)
            except Exception:
                pass
        return result

    def begin_trace(self, event_id: str) -> None:
        self._trace_local.current = {
            "event_id": str(event_id or ""),
            "stages": {},
            "stage_samples": {},
            "postgres_acquisitions": [],
            "postgres_holds": [],
        }

    def finish_trace(self, total_ms: float | int | None) -> None:
        trace = getattr(self._trace_local, "current", None)
        self._trace_local.current = None
        if trace is None:
            return
        try:
            total = float(total_ms) if total_ms is not None else None
        except (TypeError, ValueError, OverflowError):
            return
        if total is None or not math.isfinite(total) or total < 0:
            return
        trace["total_ms"] = total
        samples = trace.get("stage_samples", {})
        for total_key, child_key, residual_key in (
            ("event_fusion", ("fusion_lock_wait", "fusion_observation_load", "fusion_group_lookup", "fusion_observation_save", "fusion_group_save", "fusion_compute", "fusion_group_cleanup"), "fusion_unaccounted_ms"),
            ("active_alert_tracking", ("active_tracking_source_load", "active_tracking_track_lookup", "active_tracking_point_load", "active_tracking_association", "active_tracking_db_save"), "tracking_unaccounted_ms"),
            ("region_tracking", ("active_tracking_source_load", "active_tracking_track_lookup", "active_tracking_point_load", "active_tracking_association", "active_tracking_db_save"), "region_tracking_unaccounted_ms"),
        ):
            if total_key in samples:
                child_total = sum(float(value) for key in child_key for value in samples.get(key, []))
                total_value = sum(float(value) for value in samples.get(total_key, []))
                trace["stages"][residual_key] = max(0.0, total_value - child_total)
                trace.setdefault("stage_samples", {}).setdefault(residual_key, []).append(trace["stages"][residual_key])
        if "event_fusion" in samples:
            sql_keys = ("fusion_observation_load", "fusion_group_lookup", "fusion_observation_save", "fusion_group_save", "fusion_group_cleanup")
            sql_ms = sum(float(value) for key in sql_keys for value in samples.get(key, []))
            lock_ms = sum(float(value) for value in samples.get("fusion_lock_wait", []))
            python_ms = sum(float(value) for value in samples.get("fusion_compute", []))
            commit_ms = sum(float(value) for value in samples.get("fusion_transaction_commit", []))
            hold_ms = sum(
                float(item.get("duration_ms") or 0.0)
                for item in trace.get("postgres_holds", [])
                if item.get("purpose") == "fusion_transaction"
            )
            trace["stages"].update({
                "fusion_transaction_sql_ms": sql_ms,
                "fusion_transaction_lock_ms": lock_ms,
                "fusion_transaction_python_ms": python_ms,
                "fusion_transaction_commit_ms": commit_ms,
                "fusion_transaction_idle_ms": max(0.0, hold_ms - sql_ms - lock_ms - python_ms - commit_ms),
            })
            for key in ("fusion_transaction_sql_ms", "fusion_transaction_lock_ms", "fusion_transaction_python_ms", "fusion_transaction_commit_ms", "fusion_transaction_idle_ms"):
                trace.setdefault("stage_samples", {}).setdefault(key, []).append(trace["stages"][key])
        for key, value in trace.get("stages", {}).items():
            if key.endswith("_unaccounted_ms") or key.startswith("fusion_transaction_"):
                self.record(key, value)
        with self._lock:
            self._traces.append(trace)

    def new_critical_trace(self, event_id: str) -> dict[str, Any]:
        return {"event_id": str(event_id)[:128], "origin": monotonic(),
                "timestamps_ms": {"backend_event_received": 0.0},
                "sql_statement_count": {"total": 0, "fusion": 0, "tracking": 0},
                "stage_samples": {}, "completed": False, "owner": self}

    @contextmanager
    def critical_scope(self, trace=..., *, section=None):
        token = _critical_current.set(_critical_current.get() if trace is ... else trace)
        section_token = _critical_section.set(section or _critical_section.get())
        try:
            yield _critical_current.get()
        finally:
            _critical_section.reset(section_token)
            _critical_current.reset(token)

    def critical_mark(self, name: str, trace=...) -> None:
        trace = _critical_current.get() if trace is ... else trace
        if trace is None:
            return
        elapsed = (monotonic() - trace["origin"]) * 1000.0
        if not math.isfinite(elapsed) or elapsed < 0:
            return
        with self._lock:
            times = trace["timestamps_ms"]
            if trace["completed"] or (name in times and name not in {"region_ready", "region_db_saved"}):
                return
            if name.startswith("tracking_") or name == "websocket_track_update_sent":
                if trace.get("tracking_correlated") is False:
                    return
            times[name] = elapsed
            for stage, start, end in (
                ("first_position_backend", "backend_event_received", "websocket_event_group_sent"),
                ("fusion_to_position", "fusion_started", "websocket_event_group_sent"),
                ("post_ingest_queue_wait", "post_ingest_enqueued", "post_ingest_started"),
                ("tracking_followup", "tracking_started", "websocket_track_update_sent"),
            ):
                if name == end and start in times and times[end] >= times[start]:
                    self.record(stage, times[end] - times[start])

    def critical_sql(self) -> None:
        trace = _critical_current.get()
        if trace is None:
            return
        with self._lock:
            if trace["completed"]:
                return
            counts = trace["sql_statement_count"]
            counts["total"] += 1
            section = _critical_section.get()
            if section in ("fusion", "tracking"):
                counts[section] += 1

    def finish_critical_trace(self, trace=..., *, outcome="completed") -> None:
        trace = _critical_current.get() if trace is ... else trace
        if trace is None:
            return
        with self._lock:
            if trace["completed"]:
                return
            trace["completed"] = True
            safe = {key: deepcopy(trace[key]) for key in
                    ("event_id", "timestamps_ms", "sql_statement_count", "stage_samples")}
            safe["outcome"] = outcome
            safe["tracking_correlated"] = trace.get("tracking_correlated", True)
            safe["sql_count_scope"] = "inline event path; excludes independent device worker and uncorrelated reorder emissions"
            self._critical_traces.append(safe)
            for key, count in safe["sql_statement_count"].items():
                self._critical_counts.setdefault(key, deque(maxlen=self.max_samples_per_stage)).append(count)

    def job_enqueued(self, kind: str) -> None:
        key = str(kind or "unknown")
        with self._lock:
            pending = self._pending.get(key, 0) + 1
            self._pending[key] = pending
            self._peak_pending[key] = max(self._peak_pending.get(key, 0), pending)

    def job_started(self, kind: str, queue_wait_ms: float) -> None:
        key = str(kind or "unknown")
        with self._lock:
            self.record(f"{key}_queue_wait", queue_wait_ms)
            self._pending[key] = max(0, self._pending.get(key, 0) - 1)

    def job_cancelled(self, kind: str) -> None:
        key = str(kind or "unknown")
        with self._lock:
            self._pending[key] = max(0, self._pending.get(key, 0) - 1)

    def job_finished(self, kind: str, duration_ms: float | None = None) -> None:
        if duration_ms is not None:
            self.record(f"{str(kind or 'unknown')}_worker", duration_ms)

    def _summary(self, values: list[float]) -> StageSummary:
        return StageSummary(
            count=len(values),
            mean_ms=math.fsum(value / len(values) for value in values),
            p50_ms=self._percentile(values, 0.50),
            p95_ms=self._percentile(values, 0.95),
            p99_ms=self._percentile(values, 0.99),
            max_ms=max(values),
            last_ms=values[-1],
        )

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            samples = {key: list(values) for key, values in self._samples.items() if values}
            pending = dict(self._pending)
            peak_pending = dict(self._peak_pending)
            traces = [dict(item, stages=dict(item["stages"])) for item in self._traces]
            pool_stats = dict(self._pool_stats)
            critical = deepcopy(list(self._critical_traces))
            counts = {key: list(value) for key, value in self._critical_counts.items()}
        # Copy under the lock; percentile sorting must not hold up worker writers.
        return {
            "sample_window": self.max_samples_per_stage,
            "stages": {
                key: self._summary(values).as_dict()
                for key, values in sorted(samples.items())
            },
            "pending_jobs": pending,
            "peak_pending_jobs": peak_pending,
            "pool": pool_stats,
            "recent_traces": traces,
            "critical_path_traces": critical,
            "sql_statement_counts": {key: {"count": len(values), "p50": self._percentile(values, .5), "p95": self._percentile(values, .95), "p99": self._percentile(values, .99), "max": max(values), "unit": "attempted statements"} for key, values in counts.items() if values},
            "note": "Process-local rolling samples; reset on deploy/restart.",
        }

    def reset(self) -> None:
        with self._lock:
            self._samples.clear()
            self._pending.clear()
            self._peak_pending.clear()
            self._traces.clear()
            self._critical_traces.clear()
            self._critical_counts.clear()
            self._pool_stats.update({key: 0 for key in self._pool_stats})
            self._trace_local.current = None


latency_diagnostics = LatencyDiagnostics()


# ContextVars isolate async requests; executor handoff uses explicit shared trace.
_critical_current: ContextVar[Any] = ContextVar("latency_critical_trace", default=None)
_critical_section: ContextVar[str] = ContextVar("latency_critical_section", default="ingestion")


def critical_trace():
    return _critical_current.get()


def critical_mark(name: str) -> None:
    trace = _critical_current.get()
    if trace is not None:
        trace["owner"].critical_mark(name, trace)


def count_sql() -> None:
    trace = _critical_current.get()
    if trace is not None:
        trace["owner"].critical_sql()


class CountingCursor:
    """Transparent cursor facade: count attempts, never SQL text/parameters."""
    _critical_counted = True

    def __init__(self, cursor):
        self._cursor = cursor

    def __getattr__(self, name):
        return getattr(self._cursor, name)

    def __iter__(self):
        return iter(self._cursor)

    def __enter__(self):
        self._cursor.__enter__()
        return self

    def __exit__(self, *args):
        return self._cursor.__exit__(*args)

    def execute(self, *args, **kwargs):
        count_sql()
        self._cursor.execute(*args, **kwargs)
        return self

    def executemany(self, *args, **kwargs):
        # Count one API call, not guessed backend wire round trips.
        count_sql()
        self._cursor.executemany(*args, **kwargs)
        return self


class CountingSQLiteConnection(sqlite3.Connection):
    def cursor(self, *args, **kwargs):
        return CountingCursor(super().cursor(*args, **kwargs))

    def execute(self, *args, **kwargs):
        count_sql()
        return super().execute(*args, **kwargs)

    def executemany(self, *args, **kwargs):
        count_sql()
        return super().executemany(*args, **kwargs)
