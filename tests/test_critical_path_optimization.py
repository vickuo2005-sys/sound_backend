from datetime import datetime, timedelta, timezone
import os
import re
import uuid
import pytest
from services import event_fusion as fusion
from services.latency_diagnostics import LatencyDiagnostics, CountingCursor
from tools.test_event_fusion import make_connection


@pytest.mark.parametrize('postgres',[False,True])
def test_rollup_returning_summary_equivalent_and_query_count(postgres,monkeypatch):
    if postgres:
        dsn=os.getenv('CRITICAL_PATH_TEST_PG_DSN')
        if not dsn: pytest.skip('isolated local PostgreSQL not configured')
        import psycopg2
        from psycopg2.extras import RealDictCursor
        from psycopg2.extensions import parse_dsn
        assert parse_dsn(dsn)['host']=='127.0.0.1', 'only disposable loopback PostgreSQL allowed'
        connection=psycopg2.connect(dsn,cursor_factory=RealDictCursor)
        sqlite=make_connection()
        with connection.cursor() as c:
            schema='critical_'+uuid.uuid4().hex
            c.execute('CREATE SCHEMA "'+schema+'"')
            # A transaction-local schema, rolled back in finally.
            c.execute('SET search_path TO "'+schema+'"')
            for row in sqlite.execute("SELECT sql FROM sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%' ORDER BY CASE type WHEN 'table' THEN 0 ELSE 1 END"):
                sql=row[0].replace('INTEGER PRIMARY KEY AUTOINCREMENT','BIGSERIAL PRIMARY KEY')
                sql=re.sub(r'\b(timestamp|event_timestamp|first_event_time|last_event_time|start_time|end_time|region_updated_at|created_at|updated_at) TEXT',r'\1 TIMESTAMPTZ',sql)
                sql=re.sub(r'\b(region_geojson|reporting_device_ids) TEXT',r'\1 JSONB',sql)
                sql=sql.replace(' INTEGER',' BIGINT').replace(' REAL',' DOUBLE PRECISION')
                c.execute(sql)
        sqlite.close()
    else:
        connection=make_connection()
    now=datetime(2026,10,4,tzinfo=timezone.utc)
    class FrozenDatetime(datetime):
        @classmethod
        def now(cls,tz=None): return now
    monkeypatch.setattr(fusion,'datetime',FrozenDatetime)
    try:
        with fusion.open_cursor(connection) as cursor:
            group=fusion.create_group(cursor,'aircraft',now,postgres)
            for i,(device,stamp) in enumerate([('b',now+timedelta(seconds=1)),('a',now),('',now),('null-time',None),('a',now+timedelta(seconds=2))]):
                fusion.execute(cursor,postgres,"INSERT INTO event_group_observations (id,group_id,event_id,device_id,event_timestamp,latitude,longitude,observation_kind) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                    (str(i),group['id'],str(i),device,fusion.db_time(stamp,postgres) if stamp else None,25+i*.0001,121,'fusion'))
            fusion.execute(cursor,postgres,'INSERT INTO device_locations (device_id,latitude,longitude,location_source,created_at,updated_at) VALUES (%s,%s,%s,%s,%s,%s)',('a',24,120,'manual_map',fusion.db_time(now,postgres),fusion.db_time(now,postgres)))
            sampler=LatencyDiagnostics();trace=sampler.new_critical_trace('rollup')
            with sampler.critical_scope(trace,section='fusion'):
                actual=fusion.update_group_rollup(cursor,group['id'],postgres,mark_active=True)
                sampler.finish_critical_trace()
            # Reconstruct the legacy read/enrichment after the identical writes.
            fusion.execute(cursor,postgres,'SELECT * FROM event_groups WHERE id=%s',(group['id'],))
            row=fusion.fetchone_dict(cursor)
            legacy=fusion.group_payload(cursor,row,postgres)
            assert {k:v for k,v in actual.items() if k!='reporting_nodes'}==legacy
            assert actual['devices']==['','a','b','null-time']
            assert actual['reporting_device_ids']==['a','b','null-time']
            assert actual['region_center_lat']==pytest.approx((24+25+25.0003)/3)
            assert actual['node_count']==4
            assert sampler.snapshot()['critical_path_traces'][0]['sql_statement_count']['fusion']==(6 if postgres else 7)
            assert '_persisted_group_row' not in actual
    finally:
        if postgres: connection.rollback()
        connection.close()


def test_stale_cleanup_fast_path_retains_state_and_default_payload(tmp_path,monkeypatch):
    import main
    monkeypatch.delenv('DATABASE_URL',raising=False)
    monkeypatch.setattr(main,'DB_NAME',str(tmp_path/'stale.sqlite'))
    main.init_sqlite_db()
    now=datetime.now(timezone.utc).timestamp()*1000
    track=main.process_tracking_measurement({'label':'aircraft','estimated_lat':25,'estimated_lng':121,
        'confidence':.9,'uncertainty_radius_m':30,'event_time_ms':now},close_stale=False)
    with main.get_sqlite_connection() as c:
        c.execute('UPDATE target_tracks SET last_event_time_ms=? WHERE id=?',(now-100000,track['id']))
    calls=[]; original=main.enrich_track_with_points
    monkeypatch.setattr(main,'enrich_track_with_points',lambda row: calls.append(row['id']) or original(row))
    closed=main.close_stale_tracks(close_after_seconds=1,enrich=False)
    assert closed[0]['status']=='CLOSED' and calls==[] and 'recent_points' not in closed[0]
    with main.get_sqlite_connection() as c:
        c.execute("UPDATE target_tracks SET status='ACTIVE' WHERE id=?",(track['id'],))
    default=main.close_stale_tracks(close_after_seconds=1)
    assert default[0]['status']=='CLOSED' and calls==[track['id']]
    assert len(default[0]['recent_points'])==1
