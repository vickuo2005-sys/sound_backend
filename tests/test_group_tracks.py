import sqlite3
import uuid

from fastapi.testclient import TestClient
import main


def test_persisted_group_track_membership_is_read_only_and_deduplicated():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript("""
        CREATE TABLE target_tracks(id TEXT, label TEXT, status TEXT, point_count INTEGER);
        CREATE TABLE target_track_points(track_id TEXT, group_id TEXT);
        INSERT INTO target_tracks VALUES ('a', 'drone', 'CLOSED', 2), ('b', 'drone', 'CLOSED', 3);
        INSERT INTO target_track_points VALUES ('a','old'), ('a','old'), ('b','other');
    """)
    before = db.total_changes
    assert [r['id'] for r in main.lookup_group_tracks(db, 'old', False)] == ['a']
    assert main.lookup_group_tracks(db, "old' OR 1=1 --", False) == []
    assert db.total_changes == before
    db.close()


def test_group_tracks_api_validates_id_and_distinguishes_database_failure(monkeypatch):
    client = TestClient(main.app)
    assert client.get('/event-groups/not-a-uuid/tracks').status_code == 422
    monkeypatch.setattr(main, 'use_postgres', lambda: False)
    def unavailable():
        raise RuntimeError('private connection diagnostic')
    monkeypatch.setattr(main, 'get_sqlite_connection', unavailable)
    response = client.get(f'/event-groups/{uuid.uuid4()}/tracks')
    assert response.status_code == 503
    assert 'private connection diagnostic' not in response.text
