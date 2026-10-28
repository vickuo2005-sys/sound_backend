"""Opt-in staging ACK bridge. Process-local, bounded; no persistence or clock mixing."""
import asyncio
import logging
import math
import os
import re
import time
import uuid
from collections import OrderedDict

BOOT_ID = str(uuid.uuid4())
LOG = logging.getLogger("uvicorn.error")


def enabled():
    return os.getenv("APP_ENV", "").lower() == "staging"


def valid_id(value):
    return isinstance(value, str) and bool(re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value))


class RealtimeLatencyBridge:
    def __init__(self):
        self.pending = OrderedDict()
        self.subscribers = {}

    def prune(self):
        now = time.perf_counter() * 1000
        for key, row in list(self.pending.items()):
            if now - row["B0"] > 120000:
                self.pending.pop(key, None)
        while len(self.pending) > 512:
            self.pending.popitem(last=False)

    async def ack(self, row, kind, extra=None):
        state = row["state"]
        if row["manager"].get(state.device_id) is not state:
            return
        payload = {k: v for k, v in row.items() if k not in {"state", "manager", "targets", "receipts"}}
        payload.update(extra or {})
        try:
            async with state.send_lock:
                await asyncio.wait_for(state.websocket.send_json({
                    "protocol_version": 1, "message_type": kind,
                    "device_id": state.device_id, "payload": payload,
                }), timeout=1)
        except Exception:
            # Diagnostics must not terminate the regular node socket.
            LOG.info("PHASE3D_ACK_SEND_FAILED traceId=%s", row["traceId"])

    async def begin(self, payload, state, manager, b0, b1):
        if not enabled():
            return None
        detection = payload.get("detection_state") or {}
        trace = detection.get("phase3d") if isinstance(detection, dict) else None
        if not isinstance(trace, dict) or not all(valid_id(trace.get(k)) for k in ("traceId", "windowId", "sessionId", "runId")):
            return None
        if not detection.get("active") or not isinstance(detection.get("sequence"), int):
            return None
        # Ignore retransmitted/stale state, including heartbeat snapshots.
        if state.detection_sequence is not None and detection["sequence"] <= state.detection_sequence:
            return None
        self.prune()
        if trace["traceId"] in self.pending:
            return None
        row = {k: trace[k] for k in ("traceId", "windowId", "sessionId", "runId")}
        row.update(nodeId=state.device_id, sequence=detection["sequence"],
                   connectionId=state.connection_id, generation=state.generation,
                   serverBootId=BOOT_ID, B0=b0, B1=b1,
                   state=state, manager=manager, receipts=set(),
                   targets={ws: sid for ws, sid in self.subscribers.items()})
        self.pending[row["traceId"]] = row
        self.prune()
        await self.ack(row, "phase3d_backend_ack")
        return row

    async def complete(self, row):
        row["B3"] = time.perf_counter() * 1000
        await self.ack(row, "phase3d_backend_timing")
        LOG.info("PHASE3D_BACKEND %s", __import__("json").dumps({k: v for k, v in row.items() if k not in {"state", "manager", "targets", "receipts"}}))

    async def dashboard_message(self, ws, message):
        if not enabled() or not isinstance(message, dict):
            return
        if message.get("type") == "phase3d_subscribe":
            sid = message.get("browserSessionId")
            if valid_id(sid) and (ws in self.subscribers or len(self.subscribers) < 8):
                self.subscribers[ws] = sid
                await ws.send_json({"type": "phase3d_ready", "browserSessionId": sid, "serverBootId": BOOT_ID})
            return
        if message.get("type") != "phase3d_receipt":
            return
        self.prune()
        row = self.pending.get(message.get("traceId"))
        if not row or row["targets"].get(ws) != self.subscribers.get(ws) or ws not in row["targets"] or ws in row["receipts"]:
            return
        receipt = message.get("receipt")
        if not isinstance(receipt, dict):
            return
        times = [receipt.get(k) for k in ("D0", "D1", "D2", "D3", "D4", "D5")]
        if any(isinstance(t, bool) or not isinstance(t, (int, float)) or not math.isfinite(t) for t in times):
            return
        if times != sorted(times) or receipt.get("sequence") != row["sequence"] or receipt.get("nodeId") != row["nodeId"]:
            return
        row["receipts"].add(ws)
        safe = {k: receipt.get(k) for k in ("D0", "D1", "D2", "D3", "D4", "D5", "nodeId", "sequence", "active", "label", "confidence", "observedAtMs", "alertIndicator", "mapApplicable", "duplicate", "outOfOrder", "browserGeneration", "visible")}
        safe["browserSessionId"] = self.subscribers[ws]
        await self.ack(row, "phase3d_dashboard_ack", {"dashboard": safe})


bridge = RealtimeLatencyBridge()
