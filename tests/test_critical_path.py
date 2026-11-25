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
    assert all(set(t['timestamps_ms']) >= {'post_ingest_enqueued','post_ingest_started'} for t in snapshot['critical_path_traces'])
    assert 'post_ingest_queue_wait' not in snapshot['stages']  # existing job_started records once
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


def test_sql_cursor_preserves_postgres_execute_return_value():
    class Cursor:
        def execute(self,*args): return None
        def executemany(self,*args): return None
    facade=CountingCursor(Cursor())
    assert facade.execute('SELECT 1') is None
    assert facade.executemany('SELECT 1',[]) is None


def test_existing_queue_metric_not_doubled_by_critical_marks():
    sampler=LatencyDiagnostics()
    with sampler.critical_scope(sampler.new_critical_trace('queued')):
        critical_mark('post_ingest_enqueued')
        critical_mark('post_ingest_started')
        sampler.job_started('post_ingest',3)
        sampler.finish_critical_trace()
    assert sampler.snapshot()['stages']['post_ingest_queue_wait']['count']==1


@pytest.mark.parametrize('environment,flag,enabled', [('production','true',False),('staging','false',False),('staging','true',True)])
def test_critical_tracing_is_staging_only(monkeypatch,environment,flag,enabled):
    import main
    sampler=LatencyDiagnostics()
    monkeypatch.setattr(main,'latency_diagnostics',sampler)
    monkeypatch.setenv('APP_ENV',environment)
    monkeypatch.setenv('CRITICAL_PATH_DIAGNOSTICS_ENABLED',flag)
    long_id='e'*300
    async def submission(event,response,upload_token):
        trace=critical_trace()
        assert (trace is not None)==enabled
        if enabled: assert trace['event_id']==long_id
        return {'status':'success'}
    monkeypatch.setattr(main,'_create_event',submission)
    event=main.SoundEvent(event_id=long_id,device_id='node',label='aircraft',timestamp='2026-10-04T00:00:00Z',latitude=25,longitude=121,rms_peak=.5)
    assert asyncio.run(main.create_event(event,main.Response(),'local-test'))=={'status':'success'}
    assert len(sampler.snapshot()['critical_path_traces'])==int(enabled)
    assert critical_trace() is None


def test_new_connection_during_failed_broadcast_is_not_false_send(monkeypatch):
    import main
    sampler=LatencyDiagnostics()
    monkeypatch.setattr(main,'latency_diagnostics',sampler)
    class NewClient:
        async def send_json(self,message): pytest.fail('new client was not in send snapshot')
    class FailedClient:
        async def send_json(self,message):
            main.dashboard_manager.active_connections.append(NewClient())
            raise RuntimeError('disconnected')
    monkeypatch.setattr(main.dashboard_manager,'active_connections',[FailedClient()])
    async def run():
        with sampler.critical_scope(sampler.new_critical_trace('failed-old-client')):
            await main.safe_dashboard_broadcast({'type':'event_group','group':{'region_center_lat':25,'region_center_lng':121}})
    asyncio.run(run())
    assert main.dashboard_manager.active_connections
    assert 'first_position_backend' not in sampler.snapshot()['stages']


def test_reorder_emissions_do_not_inherit_trigger_trace(monkeypatch):
    import main
    from types import SimpleNamespace
    sampler=LatencyDiagnostics()
    monkeypatch.setattr(main,'latency_diagnostics',sampler)
    seen=[]
    def process(measurement):
        seen.append(critical_trace())
        sampler.critical_sql()
        return {'id':'track'}
    monkeypatch.setattr(main,'process_tracking_measurement',process)
    with sampler.critical_scope(sampler.new_critical_trace('new-trigger'),section='tracking'):
        result=main.process_tracking_reorder_items((SimpleNamespace(payload={'event':'older'}),))
        sampler.finish_critical_trace()
    assert result=={'id':'track'} and seen==[None]
    assert sampler.snapshot()['critical_path_traces'][0]['sql_statement_count']['total']==0
