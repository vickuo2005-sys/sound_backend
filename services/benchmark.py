"""Isolated, opt-in benchmark ingestion. Never stores audio or location."""
import csv
import hashlib
import hmac
import io
import json
import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, model_validator

router = APIRouter(prefix="/benchmark", tags=["benchmark"])
HOPS = [1500, 1000, 750, 500, 350, 300, 250, 200, 150, 100]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Session(Strict):
    session_id: UUID
    brand: str = Field(max_length=80)
    model: str = Field(max_length=120)
    android_version: str = Field(max_length=40)
    abi: str = Field(max_length=160)
    cores: int = Field(ge=1, le=256)
    memory_mb: int = Field(ge=1, le=1048576)
    app_version: str = Field(max_length=80)
    model_id: str = Field(max_length=100)
    model_version: str = Field(max_length=80)
    model_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    model_metadata_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    pipeline_version: Literal['native-wav-ai.v1', 'native-wav-ai.v2']
    protocol_version: Literal['benchmark.protocol.v1', 'benchmark.protocol.v1.1', 'benchmark.protocol.v1.2'] = 'benchmark.protocol.v1'
    inference_settings: Literal['tflite_flutter-0.12.1-default-options']
    input_shape: list[int] = Field(min_length=1, max_length=8)
    output_shape: list[int] = Field(min_length=1, max_length=8)
    started_at: datetime


class Sample(Strict):
    sequence: int = Field(ge=0)
    ready_native_ms: float = Field(ge=0, le=1e15)
    native_queue_ms: float = Field(ge=0, le=600000)
    native_save_ms: float = Field(ge=0, le=600000)
    bridge_upper_ms: float = Field(ge=0, le=600000)
    flutter_queue_ms: float = Field(ge=0, le=600000)
    preprocess_ms: float = Field(ge=0, le=600000)
    inference_ms: float = Field(ge=0, le=600000)
    pipeline_upper_ms: float = Field(ge=0, le=600000)
    success: bool


class Run(Strict):
    run_id: UUID
    hop_ms: int
    window_ms: Literal[3000]
    phase: Literal["survey", "confirmation"]
    duration_ms: int = Field(ge=0, le=600000)
    generated: int = Field(ge=0, le=100000)
    processed: int = Field(ge=0, le=100000)
    dropped: int = Field(ge=0, le=100000)
    max_backlog: int = Field(ge=0, le=10)
    thermal_max: int | None = Field(default=None, ge=0, le=6)
    cpu_ms: int | None = Field(default=None, ge=0)
    errors: list[str] = Field(max_length=32)
    samples: list[Sample] = Field(max_length=2000)

    @model_validator(mode="after")
    def counts(self):
        if self.hop_ms not in HOPS or self.processed != len(self.samples):
            raise ValueError("invalid hop or sample count")
        if self.generated != self.processed + self.dropped:
            raise ValueError("generated must equal processed + dropped")
        if len({s.sequence for s in self.samples}) != self.processed:
            raise ValueError("duplicate sequence")
        if any(len(e) > 200 for e in self.errors):
            raise ValueError("error too long")
        return self


class Batch(Strict):
    session_id: UUID
    completed_at: datetime
    status: Literal["completed", "cancelled", "failed", "interrupted"]
    reason: str = Field(max_length=200)
    criteria_version: Literal["benchmark.v1"]
    runs: list[Run] = Field(max_length=20)

    @model_validator(mode="after")
    def unique(self):
        if len({r.run_id for r in self.runs}) != len(self.runs):
            raise ValueError("duplicate run")
        return self


def summary(values):
    values = sorted(values)
    if not values:
        return None
    def p(q):
        import math
        return values[max(0, math.ceil(q * len(values)) - 1)]
    return dict(p50=p(.5), p95=p(.95), p99=p(.99), average=sum(values)/len(values), maximum=values[-1])


def evaluate(run):
    n = run.processed
    pipeline = summary([s.pipeline_upper_ms for s in run.samples])
    reasons = []
    if n < (60 if run.phase == "confirmation" else 30):
        reasons.append("insufficient_samples")
    if run.phase == "confirmation" and run.duration_ms < 120000:
        reasons.append("confirmation_too_short")
    if n == 0 or sum(s.success for s in run.samples)/max(1, n) < .99:
        reasons.append("inference_success")
    if run.dropped/max(1, run.generated) > .01:
        reasons.append("dropped_rate")
    if pipeline is None or pipeline["p95"] >= run.hop_ms:
        reasons.append("pipeline_budget")
    if run.max_backlog > 2:
        reasons.append("backlog")
    if run.thermal_max is not None and run.thermal_max >= 3:
        reasons.append("thermal")
    if run.errors:
        reasons.append("interrupted_or_error")
    return dict(passed=not reasons, reasons=reasons, pipeline=pipeline,
                inference=summary([s.inference_ms for s in run.samples]),
                recommended=not reasons and pipeline["p95"] < .8*run.hop_ms)


def decisions(batch):
    operating = [r.hop_ms for r in batch.runs if r.processed >= 30 and all(s.success for s in r.samples) and not r.errors]
    stable = [r.hop_ms for r in batch.runs if r.phase == "confirmation" and evaluate(r)["passed"]]
    recommended = [r.hop_ms for r in batch.runs if r.phase == "confirmation" and evaluate(r)["recommended"]]
    return dict(lowest_operating_hop=min(operating, default=None), lowest_stable_hop=min(stable, default=None), recommended_hop=min(recommended, default=None))


_lock = threading.Lock()
_limits = {}


def guard(request):
    if os.getenv("BENCHMARK_ENABLED") != "true":
        raise HTTPException(503, "benchmark disabled")
    # No forwarded headers: trusted reverse proxy must enforce distributed limits.
    host = request.client.host if request.client else "unknown"
    now = time.monotonic()
    with _lock:
        for k in list(_limits):
            if now - _limits[k][0] > 3600:
                del _limits[k]
        start, count = _limits.get(host, (now, 0))
        if count >= 60 or (host not in _limits and len(_limits) >= 10000):
            raise HTTPException(429, "rate limit", headers={"Retry-After": "3600"})
        _limits[host] = (start, count+1)


def secret_hash(authorization):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "session credential required")
    token = authorization[7:]
    if len(token) != 64 or any(c not in "0123456789abcdef" for c in token):
        raise HTTPException(401, "invalid credential")
    return hashlib.sha256(token.encode()).hexdigest()


@contextmanager
def database():
    # Separate URL deliberately prevents accidental writes to production DB.
    url = os.getenv("BENCHMARK_DATABASE_URL", "")
    if url.startswith("sqlite:///"):
        conn = sqlite3.connect(url[10:], timeout=10)
        placeholder = "?"
        conn.execute("PRAGMA foreign_keys=ON")
    elif url.startswith(("postgres://", "postgresql://")):
        import psycopg2
        conn = psycopg2.connect(url, connect_timeout=10)
        placeholder = "%s"
    else:
        raise HTTPException(503, "benchmark database not configured")
    try:
        with conn:
            with_cursor = conn.cursor()
            try:
                yield lambda sql, args=(): _execute(with_cursor, sql.replace("?", placeholder), args)
            finally:
                with_cursor.close()
    finally:
        conn.close()


def _execute(cursor, sql, args):
    cursor.execute(sql, args)
    return cursor


@router.post("/sessions")
def create_session(body: Session, request: Request, authorization: str | None = Header(default=None)):
    guard(request)
    digest = secret_hash(authorization)
    metadata = body.model_dump_json()
    with database() as execute:
        execute("INSERT INTO benchmark_sessions(session_id, credential_hash, metadata_json) VALUES (?, ?, ?) ON CONFLICT(session_id) DO NOTHING", (str(body.session_id), digest, metadata))
        row = execute("SELECT credential_hash, metadata_json FROM benchmark_sessions WHERE session_id=?", (str(body.session_id),)).fetchone()
        if not hmac.compare_digest(row[0], digest):
            raise HTTPException(403, "session ownership mismatch")
        if json.loads(row[1]) != json.loads(metadata):
            raise HTTPException(409, "session metadata immutable")
    return {"stored": True, "session_id": str(body.session_id)}


@router.post("/results/batch")
def save_batch(body: Batch, request: Request, authorization: str | None = Header(default=None)):
    guard(request)
    digest = secret_hash(authorization)
    result = body.model_dump_json()
    result_hash = hashlib.sha256(result.encode()).hexdigest()
    with database() as execute:
        # Lock on PostgreSQL serializes retries; SQLite conditional update is atomic.
        row = execute("SELECT credential_hash, result_hash FROM benchmark_sessions WHERE session_id=?", (str(body.session_id),)).fetchone()
        if not row or not hmac.compare_digest(row[0], digest):
            raise HTTPException(403, "session ownership mismatch")
        if row[1] and row[1] != result_hash:
            raise HTTPException(409, "completed result immutable")
        execute("UPDATE benchmark_sessions SET result_json=?, result_hash=? WHERE session_id=? AND (result_hash IS NULL OR result_hash=?)", (result, result_hash, str(body.session_id), result_hash))
        if execute("SELECT result_hash FROM benchmark_sessions WHERE session_id=?", (str(body.session_id),)).fetchone()[0] != result_hash:
            raise HTTPException(409, "concurrent conflicting result")
        for run in body.runs:
            execute("INSERT INTO benchmark_runs(run_id, session_id, hop_ms, phase, payload_json) VALUES (?, ?, ?, ?, ?) ON CONFLICT(run_id) DO NOTHING", (str(run.run_id), str(body.session_id), run.hop_ms, run.phase, run.model_dump_json()))
            owner = execute("SELECT session_id FROM benchmark_runs WHERE run_id=?", (str(run.run_id),)).fetchone()
            if owner[0] != str(body.session_id):
                raise HTTPException(409, "run belongs to another session")
    return {"stored": True, "session_id": str(body.session_id), "result_sha256": result_hash, **decisions(body)}


def csv_safe(value):
    value = str(value if value is not None else "")
    return "'"+value if value.lstrip().startswith(("=", "+", "-", "@")) else value


@router.get("/admin/export.csv")
def export_csv(request: Request, authorization: str | None = Header(default=None)):
    guard(request)
    key = os.getenv("BENCHMARK_ADMIN_TOKEN", "")
    if len(key) < 32 or not hmac.compare_digest(authorization or "", "Bearer "+key):
        raise HTTPException(403, "administrator required")
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    metadata_fields = list(Session.model_fields)
    run_fields = ['run_id', 'hop_ms', 'window_ms', 'phase', 'duration_ms', 'generated', 'processed', 'dropped', 'max_backlog', 'thermal_max', 'cpu_ms']
    metrics = ['native_queue_ms', 'native_save_ms', 'bridge_upper_ms', 'flutter_queue_ms', 'preprocess_ms', 'inference_ms', 'pipeline_upper_ms']
    percentiles = ['p50', 'p95', 'p99', 'average', 'maximum']
    writer.writerow(metadata_fields + ['status', 'session_reason'] + run_fields +
                    [f'{metric}_{stat}' for metric in metrics for stat in percentiles] +
                    ['passed', 'reasons', 'lowest_operating_hop', 'lowest_stable_hop', 'recommended_hop'])
    with database() as execute:
        cursor = execute("SELECT metadata_json, result_json FROM benchmark_sessions WHERE result_json IS NOT NULL ORDER BY session_id")
        while rows := cursor.fetchmany(100):
            for metadata, result in rows:
                s, batch = Session.model_validate_json(metadata).model_dump(mode='json'), Batch.model_validate_json(result)
                decision = decisions(batch)
                for run in batch.runs or [None]:
                    if run is None:
                        writer.writerow(map(csv_safe, [s.get(k) for k in metadata_fields] + [batch.status, batch.reason] +
                            [None]*(len(run_fields)+len(metrics)*len(percentiles)) + [False, batch.reason, None, None, None]))
                        continue
                    e = evaluate(run)
                    statistics = {m: summary([getattr(sample, m) for sample in run.samples]) or {} for m in metrics}
                    writer.writerow(map(csv_safe, [s.get(k) for k in metadata_fields] + [batch.status, batch.reason] +
                        [getattr(run, k) for k in run_fields] + [statistics[m].get(p) for m in metrics for p in percentiles] +
                        [e['passed'], ';'.join(e['reasons']), *decision.values()]))
    return Response("\ufeff"+output.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="benchmark.csv"'})


class BenchmarkBodyLimit:
    """Limit streamed bodies before Pydantic parses them, including chunked requests."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope["path"].startswith("/benchmark/"):
            return await self.app(scope, receive, send)
        chunks, size = [], 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            size += len(message.get("body", b""))
            if size > 4*1024*1024:
                response = Response("payload too large", status_code=413)
                return await response(scope, receive, send)
            chunks.append(message)
            if not message.get("more_body", False):
                break
        async def replay():
            return chunks.pop(0) if chunks else await receive()
        await self.app(scope, replay, send)
