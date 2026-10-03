import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import pytest
from services.latency_diagnostics import LatencyDiagnostics, CountingCursor, critical_mark, critical_trace


def test_correlated_sql_thread_handoff_and_exception_samples():
    sampler=LatencyDiagnostics()
    def work(i):
        trace=sampler.new_critical_trace(str(i))
        class Cursor:
            def execute(self,*args):
                raise ValueError("query failed")
        with sampler.critical_scope(trace,section="fusion"):
            critical_mark("fusion_started")
            for _ in range(i+1):
                with pytest.raises(ValueError): CountingCursor(Cursor()).execute("private SQL")
            sampler.record("fusion_failure_duration",.2)
            critical_mark("websocket_event_group_sent")
            sampler.finish_critical_trace()
        assert critical_trace() is None
    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(work,range(12)))
    snap=sampler.snapshot()
    for t in snap["critical_path_traces"]:
        assert t["sql_statement_count"]["fusion"]==int(t["event_id"])+1
        assert t["sql_statement_count"]["total"]==int(t["event_id"])+1
        assert t["sql_statement_count"]["tracking"]==0
        assert t["stage_samples"]["fusion_failure_duration"]==[.2]
    assert snap["stages"]["first_position_backend"]["count"]==12
    assert 'private SQL' not in json.dumps(snap)
    assert 'origin' not in json.dumps(snap)


def test_nested_scope_clear_bounds_and_invalid_samples():
    sampler=LatencyDiagnostics()
    for i in range(40):
        t=sampler.new_critical_trace(str(i))
        with sampler.critical_scope(t):
            with sampler.critical_scope(None):
                sampler.critical_sql()
                assert critical_trace() is None
            assert critical_trace() is t
            for invalid in (None,float('nan'),float('inf'),-1,'invalid'):
                sampler.record('invalid',invalid)
            critical_mark('post_ingest_enqueued')
            critical_mark('post_ingest_started')
            sampler.finish_critical_trace()
            sampler.finish_critical_trace()  # exactly once
    snapshot=sampler.snapshot()
    assert len(snapshot['critical_path_traces'])==32
    assert snapshot['stages']['post_ingest_queue_wait']['count']==40
    assert 'invalid' not in snapshot['stages']
    assert all(t['sql_statement_count']['total']==0 for t in snapshot['critical_path_traces'])


def test_full_local_ingest_worker_broadcast_trace(tmp_path,monkeypatch):
    import main
    from datetime import datetime,timezone
    monkeypatch.delenv('DATABASE_URL',raising=False)
    monkeypatch.setenv('APP_ENV','staging')
    monkeypatch.setenv('UPLOAD_TOKEN','local-test')
    monkeypatch.setattr(main,'DB_NAME',str(tmp_path/'local.sqlite'))
    sampler=LatencyDiagnostics()
    monkeypatch.setattr(main,'latency_diagnostics',sampler)
    monkeypatch.setattr(main,'LOCALIZATION_ENABLED',False)
    monkeypatch.setattr(main,'TRACKING_REORDER_BUFFER_ENABLED',False)
    main.init_sqlite_db()
    messages=[]
    class Sink:
        async def send_json(self,message): messages.append(message)
    monkeypatch.setattr(main.dashboard_manager,'active_connections',[Sink()])
    async def run():
        event=main.SoundEvent(event_id='correlated-event',device_id='node-test',label='aircraft',
            timestamp=datetime.now(timezone.utc).isoformat(),latitude=25,longitude=121,rms_peak=.8)
        result=await main.create_event(event,main.Response(),'local-test')
        assert result['status']=='success'
        for _ in range(1000):
            if sampler.snapshot()['critical_path_traces']: return
            await asyncio.sleep(.005)
        pytest.fail('worker trace did not complete')
    asyncio.run(run())
    snapshot=sampler.snapshot()
    trace=snapshot['critical_path_traces'][0]
    assert trace['event_id']=='correlated-event'
    assert set(trace['timestamps_ms']) >= {'backend_event_received','event_db_write_done',
        'post_ingest_enqueued','post_ingest_started','fusion_started','fusion_group_resolved',
        'fusion_observation_saved','region_ready','region_db_saved','websocket_event_group_sent','post_ingest_done'}
    assert trace['sql_statement_count']['fusion']>0
    assert trace['sql_statement_count']['total']>=trace['sql_statement_count']['fusion']
    groups=[m for m in messages if m['type']=='event_group']
    assert groups[0]['critical_path']['event_id']=='correlated-event'
    assert 'device_relative_times' in groups[0]['group']
    assert '_critical_trace' not in json.dumps(groups)
    assert snapshot['stages']['first_position_backend']['count']==1


def test_no_position_no_clients_and_failed_broadcast_not_counted(monkeypatch):
    import main
    sampler=LatencyDiagnostics()
    monkeypatch.setattr(main,'latency_diagnostics',sampler)
    monkeypatch.setattr(main.dashboard_manager,'active_connections',[])
    async def ok(message): pass
    monkeypatch.setattr(main.dashboard_manager,'broadcast',ok)
    async def run():
        with sampler.critical_scope(sampler.new_critical_trace('no-client')):
            await main.safe_dashboard_broadcast({'type':'event_group','group':{'region_center_lat':25,'region_center_lng':121}})
        monkeypatch.setattr(main.dashboard_manager,'active_connections',[object()])
        with sampler.critical_scope(sampler.new_critical_trace('invalid')):
            await main.safe_dashboard_broadcast({'type':'event_group','group':{'region_center_lat':None,'region_center_lng':121}})
        async def fail(message): raise ValueError('failed')
        monkeypatch.setattr(main.dashboard_manager,'broadcast',fail)
        with sampler.critical_scope(sampler.new_critical_trace('failed')):
            await main.safe_dashboard_broadcast({'type':'event_group','group':{'region_center_lat':25,'region_center_lng':121}})
    asyncio.run(run())
    assert 'first_position_backend' not in sampler.snapshot()['stages']
