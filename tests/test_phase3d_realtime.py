import asyncio
import math
import time
from types import SimpleNamespace

from services.realtime_latency import RealtimeLatencyBridge


class Socket:
    def __init__(self):
        self.messages = []

    async def send_json(self, message):
        self.messages.append(message)


def setup(monkeypatch):
    monkeypatch.setenv("APP_ENV", "staging")
    bridge = RealtimeLatencyBridge()
    sock, browser = Socket(), Socket()
    state = SimpleNamespace(device_id="node_A01", connection_id="conn", generation=2,
                            websocket=sock, send_lock=asyncio.Lock(), detection_sequence=None)
    manager = SimpleNamespace(get=lambda _: state)
    payload = {"detection_state": {"active": True, "sequence": 1, "phase3d": {
        "traceId": "p3d_1", "windowId": "window_1", "sessionId": "session_1", "runId": "run_1"}}}
    return bridge, sock, browser, state, manager, payload


def test_correlated_receipt_before_broadcast_complete_and_duplicate(monkeypatch):
    async def run():
        b, sock, browser, state, manager, payload = setup(monkeypatch)
        await b.dashboard_message(browser, {"type": "phase3d_subscribe", "browserSessionId": "browser_1"})
        row = await b.begin(payload, state, manager, time.perf_counter()*1000, time.perf_counter()*1000)
        assert sock.messages[-1]["message_type"] == "phase3d_backend_ack"
        row["B2"] = time.perf_counter()*1000
        receipt = {f"D{i}": i for i in range(6)} | {"nodeId": "node_A01", "sequence": 1}
        message = {"type": "phase3d_receipt", "traceId": "p3d_1", "receipt": receipt}
        await b.dashboard_message(browser, message)
        await b.dashboard_message(browser, message)
        assert len(sock.messages) == 2
        await b.complete(row)
        assert sock.messages[-1]["payload"]["B3"] >= row["B2"]
        assert await b.begin(payload, state, manager, 0, 0) is None
    asyncio.run(run())


def test_wrong_browser_invalid_timestamps_and_stale_connection_rejected(monkeypatch):
    async def run():
        b, sock, browser, state, manager, payload = setup(monkeypatch)
        await b.dashboard_message(browser, {"type": "phase3d_subscribe", "browserSessionId": "browser_1"})
        await b.begin(payload, state, manager, time.perf_counter()*1000, time.perf_counter()*1000)
        receipt = {f"D{i}": i for i in range(6)} | {"nodeId": "node_A01", "sequence": 1}
        msg = {"type": "phase3d_receipt", "traceId": "p3d_1", "receipt": receipt}
        await b.dashboard_message(Socket(), msg)
        await b.dashboard_message(browser, msg | {"receipt": receipt | {"D2": math.nan}})
        await b.dashboard_message(browser, msg | {"receipt": receipt | {"D2": -1}})
        assert len(sock.messages) == 1
        manager.get = lambda _: None
        await b.dashboard_message(browser, msg)
        assert len(sock.messages) == 1
    asyncio.run(run())


def test_production_disabled_stale_sequence_bounded_and_expiring(monkeypatch):
    async def run():
        b, sock, browser, state, manager, payload = setup(monkeypatch)
        monkeypatch.setenv("APP_ENV", "production")
        assert await b.begin(payload, state, manager, 0, 0) is None
        await b.dashboard_message(browser, {"type": "phase3d_subscribe", "browserSessionId": "browser_1"})
        assert not b.subscribers
        monkeypatch.setenv("APP_ENV", "staging")
        state.detection_sequence = 1
        assert await b.begin(payload, state, manager, 0, 0) is None
        now = time.perf_counter()*1000
        for i in range(600):
            b.pending[str(i)] = {"B0": now}
        b.prune()
        assert len(b.pending) == 512
        b.pending["old"] = {"B0": now-130000}
        b.prune()
        assert "old" not in b.pending
    asyncio.run(run())
