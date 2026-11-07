import threading

import pytest
from fastapi import HTTPException

import main


class FakeCursor:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query):
        assert query == "SELECT 1"

    def fetchone(self):
        return {"ok": 1}


class FakeConnection:
    closed = 0

    def rollback(self):
        return None

    def cursor(self):
        return FakeCursor()


class FakePool:
    def __init__(self):
        self.connection = FakeConnection()
        self.returned = []

    def getconn(self):
        return self.connection

    def putconn(self, connection, close=False):
        self.returned.append((connection, close))


def configure_fake_pool(monkeypatch):
    pool = FakePool()
    gate = threading.BoundedSemaphore(1)
    monkeypatch.setattr(main, "_postgres_pool", pool)
    monkeypatch.setattr(main, "_postgres_pool_gate", gate)
    monkeypatch.setattr(main, "get_postgres_pool", lambda: pool)
    monkeypatch.setattr(main, "POSTGRES_POOL_ACQUIRE_TIMEOUT_SECONDS", 0.01)
    return pool, gate


def test_postgres_connection_releases_pool_slot_on_close(monkeypatch):
    pool, gate = configure_fake_pool(monkeypatch)

    connection = main.get_postgres_connection()
    assert gate.acquire(blocking=False) is False

    connection.close()
    connection.close()

    assert pool.returned == [(pool.connection, False)]
    assert gate.acquire(blocking=False) is True
    gate.release()


def test_postgres_connection_returns_503_when_pool_is_busy(monkeypatch):
    _, gate = configure_fake_pool(monkeypatch)
    assert gate.acquire(blocking=False) is True

    try:
        with pytest.raises(HTTPException) as exc_info:
            main.get_postgres_connection()
    finally:
        gate.release()

    assert exc_info.value.status_code == 503
    assert "temporarily busy" in str(exc_info.value.detail)


def test_tracks_cache_avoids_stale_close_write(monkeypatch):
    cached = {
        "status": "success",
        "count": 1,
        "closed_count": 0,
        "tracks": [{"id": "cached-track"}],
    }
    monkeypatch.setattr(main, "get_tracks_cache", lambda key: cached)

    def unexpected_close():
        raise AssertionError("cache hit must not perform a stale-track write")

    monkeypatch.setattr(main, "close_stale_tracks", unexpected_close)

    assert main.tracks(
        status_filter=None,
        label=None,
        limit=20,
        points_limit=20,
    ) == cached
