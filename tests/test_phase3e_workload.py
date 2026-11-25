import asyncio
import json
import logging
from services.normal_workload_diagnostics import NormalWorkloadDiagnosticsMiddleware, mark, correlation


def test_staging_actual_response_exception_and_context_reset(monkeypatch,caplog):
    monkeypatch.setenv('APP_ENV','staging')
    async def run(fail=False):
        messages=[]
        async def app(scope,receive,send):
            assert correlation()['requestId']=='p3e_unit_event_1'
            mark('E1_db_write_complete',eventId='event_1',nodeId='node_A01',password='must_not_log')
            if fail:raise RuntimeError('fixture')
            await send({'type':'http.response.start','status':200,'headers':[]})
            await send({'type':'http.response.body','body':b'ok'})
        async def send(message):messages.append(message)
        scope={'type':'http','method':'POST','path':'/events','headers':[], 'query_string':b'phase3e_request_id=p3e_unit_event_1'}
        try:await NormalWorkloadDiagnosticsMiddleware(app)(scope,None,send)
        except RuntimeError:assert fail
        assert not correlation()
        if not fail:assert messages[-1]['body']==b'ok'
    with caplog.at_level(logging.INFO,logger='uvicorn.error'):
        asyncio.run(run());asyncio.run(run(True))
    logs=[json.loads(record.message.split('PHASE3E_HTTP ',1)[1]) for record in caplog.records if 'PHASE3E_HTTP ' in record.message]
    assert len(logs)==2
    assert logs[0]['stages']['response_send_complete']>=logs[0]['stages']['E1_db_write_complete']>=logs[0]['stages']['request_received']
    assert 'must_not_log' not in caplog.text


def test_production_or_invalid_identifier_passes_through(monkeypatch,caplog):
    async def app(scope,receive,send):assert not correlation()
    middleware=NormalWorkloadDiagnosticsMiddleware(app)
    scope={'type':'http','method':'POST','path':'/location-update','headers':[(b'x-phase3e-request-id',b'p3e_unit_gps_1')]}
    monkeypatch.setenv('APP_ENV','production');asyncio.run(middleware(scope,None,None))
    monkeypatch.setenv('APP_ENV','staging');scope['headers']=[(b'x-phase3e-request-id',b'bad value')];asyncio.run(middleware(scope,None,None))
    assert not caplog.records
