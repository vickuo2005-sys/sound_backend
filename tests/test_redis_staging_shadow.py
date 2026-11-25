import ast
from dataclasses import replace
import json
from pathlib import Path
import time
from types import SimpleNamespace
import pytest
from services.events import redis_shadow as shadow
from services.events.redis_streams import RedisDelivery, RedisStreamsEventBus
from services.events.types import EventType
from services.latency_diagnostics import LatencyDiagnostics
from test_event_envelope import envelope
from test_event_redis_integration import redis_bus


def event_data(identifier='shadow-test',**changes):
    return SimpleNamespace(**dict({'event_id':identifier,'device_id':'node_A01','trace_id':'trace-'+identifier,
        'timestamp':'2026-10-04T00:00:00Z','label':'Drone','latitude':25.0,'longitude':121.0},**changes))


def runtime(capacity=4,bytes_limit=65536,factory=None):
    config=shadow.Config('redis://127.0.0.1:1',capacity=capacity,max_bytes=bytes_limit,allow_loopback_test=True)
    return shadow.RedisShadow(config,LatencyDiagnostics(),factory=factory)


def until(predicate,seconds=6):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        if predicate(): return
        time.sleep(.01)
    assert predicate(), 'Shadow did not reach expected state before deadline'


def test_config_staging_guard_and_remote_security(monkeypatch):
    for environment in ('production','local',''):
        monkeypatch.setenv('APP_ENV',environment); monkeypatch.setenv('REDIS_SHADOW_ENABLED','true')
        assert not shadow.enabled()
    monkeypatch.setenv('APP_ENV','staging'); assert shadow.enabled()
    with pytest.raises(ValueError): shadow.Config('redis://example.invalid:6379')
    with pytest.raises(ValueError): shadow.Config('rediss://example.invalid:6379')
    monkeypatch.setenv('REDIS_SHADOW_CONSUMERS','2')
    with pytest.raises(ValueError): shadow.Config.environment()


def test_queue_full_is_visible_and_size_guard_does_not_raise():
    current=runtime(capacity=1)
    original=event_data()
    assert current.initial(original,{'saved_event':{}},1,time.monotonic())
    assert not current.initial(original,{'saved_event':{}},1,time.monotonic())
    assert current.snapshot()['enqueue_rejected']==1 and current.queue.qsize()==1
    oversized=runtime(bytes_limit=1024)
    assert not oversized.initial(event_data(audio_path='x'*2048),{'saved_event':{}},1,time.monotonic())
    assert oversized.snapshot()['oversize_rejected']==1 and oversized.queue.empty()


def test_exact_serialized_size_guard_applies_only_to_shadow():
    # CJK characters are more bytes than characters; publisher must check UTF-8 bytes.
    connections=[]
    def unavailable(name):
        connections.append(name)
        raise ConnectionError('Synthetic audit connection unavailable')
    current=runtime(bytes_limit=1024,factory=unavailable)
    assert current.initial(event_data(audio_path='聲'*300),{'saved_event':{'audio_path':'聲'*300}},1,time.monotonic())
    current.start()
    try:
        until(lambda:current.queue.unfinished_tasks==0)
        assert current.snapshot()['oversize_rejected']==2
        assert current.snapshot()['xadd_success']==0
        assert 'publisher' not in connections
    finally: current.close()


def test_audit_lifecycle_optional_track_duplicates_and_identity():
    audit=shadow.Audit()
    def observe(kind,metadata=None,correlation='e'):
        return audit.observe(RedisDelivery('1-0',envelope(event_type=kind,correlation_id=correlation,metadata=metadata or {})))
    observe(EventType.ACOUSTIC_EVENT_RECEIVED); observe(EventType.EVENT_PERSISTED)
    observe(EventType.POSITION_UPDATED)
    assert audit.snapshot()['complete_lifecycle_count']==1
    observe(EventType.POSITION_UPDATED)
    assert audit.snapshot()['duplicate_phase_count']==1
    other=shadow.Audit()
    other.observe(RedisDelivery('2-0',envelope(event_type=EventType.TRACK_UPDATED)))
    assert other.snapshot()['ordering_violation_count']==1
    observe(EventType.TRACK_UPDATED,correlation='wrong')
    assert audit.snapshot()['correlation_mismatch_count']==1


def test_missing_lifecycle_is_counted_after_timeout():
    audit=shadow.Audit(timeout=1)
    audit.observe(RedisDelivery('1-0',envelope()))
    audit.contexts['e']['time']-=2
    audit.expire()
    assert audit.snapshot()['missing_phase_count']==1 and not audit.contexts


def test_audit_module_has_no_domain_mutation_imports_or_calls():
    source=Path(shadow.__file__).read_text()
    tree=ast.parse(source)
    imports=[node.module for node in ast.walk(tree) if isinstance(node,ast.ImportFrom)]
    assert not any(name and any(part in name for part in ('main','tracking','database','realtime','event_fusion')) for name in imports)
    names={node.attr for node in ast.walk(tree) if isinstance(node,ast.Attribute)}
    assert not names.intersection({'broadcast','process_fusion_event','process_tracking_for_event_group_region',
        'get_db','get_postgres_connection','execute','commit'})


@pytest.mark.parametrize('mode',['disabled','unavailable','full','oversize'])
def test_actual_api_legacy_parity_and_fault_isolation(monkeypatch,mode):
    import main
    from fastapi.testclient import TestClient
    monkeypatch.setenv('APP_ENV','staging'); monkeypatch.setenv('REDIS_SHADOW_ENABLED','false')
    monkeypatch.setattr(main,'verify_upload_token',lambda token:None)
    monkeypatch.setattr(main,'staging_write_freeze_active',lambda:False)
    monkeypatch.setattr(main,'utc_wall_time_ms',lambda:1791072000000)
    monkeypatch.setattr(main,'monotonic',lambda:1000.0)
    calls=[]
    def initial(e):
        calls.append(e.event_id)
        return {'db_id':7,'device_row':None,'is_existing_event':True,'saved_event':{'event_id':e.event_id,'label':e.label}}
    monkeypatch.setattr(main,'process_event_initial_submission',initial)
    client=TestClient(main.app)
    payload={'event_id':'shadow-test','device_id':'node_A01','timestamp':'2026-10-04T00:00:00Z',
        'latitude':25,'longitude':121,'rms_peak':.5,'label':'non_aircraft'}
    reference=client.post('/events',json=payload)
    assert reference.status_code==200
    current=runtime(capacity=1,bytes_limit=1024 if mode=='oversize' else 65536)
    monkeypatch.setattr(shadow,'_runtime',current)
    if mode!='disabled': monkeypatch.setenv('REDIS_SHADOW_ENABLED','true')
    if mode=='full': current.initial(event_data(),{'saved_event':{}},1,time.monotonic())
    if mode=='oversize': payload['audio_path']='x'*2048
    if mode=='unavailable':
        def unavailable(_): raise ConnectionError('Synthetic connection failure; no secret')
        current.factory=unavailable; current.start()
    try:
        response=client.post('/events',json=payload)
        assert response.status_code==200 and response.json()==reference.json()
        assert calls==['shadow-test','shadow-test']
        if mode=='disabled': assert current.queue.empty()
        if mode=='full': assert current.snapshot()['enqueue_rejected']==1
        if mode=='oversize': assert current.snapshot()['oversize_rejected']==1
        if mode=='unavailable':
            until(lambda:current.snapshot()['xadd_failure']>0)
            assert current.snapshot()['reconnect_count']>0 and current.queue.qsize()<=1
            assert len(current.buses)<=2
    finally: current.close()


@pytest.fixture
def real_shadow(redis_bus):
    transport,url=redis_bus
    config=shadow.Config(url,stream='staging:'+transport.stream,group='staging-shadow-test',allow_loopback_test=True)
    current=shadow.RedisShadow(config,LatencyDiagnostics(),factory=lambda name:RedisStreamsEventBus.from_url(
        url,stream=config.stream,group=config.group,consumer=name,block_ms=10,max_reconnect_attempts=1))
    yield current,transport.client,url
    current.close(); transport.client.delete(config.stream,config.stream+':dlq')


def test_real_shadow_lifecycle_metrics_and_sanitized_diagnostics(real_shadow):
    current,client,_=real_shadow; current.start()
    current.initial(event_data(),{'saved_event':{'id':7,'label':'Drone'}},1791072000000,time.monotonic())
    current.post_ingest('shadow-test',{'event_group':{'id':'group','region_center_lat':25.1,'region_center_lng':121.1},'region_track':{'id':'track','last_lat':25.2}})
    until(lambda:current.snapshot()['ack_success']==4)
    assert current.audit.snapshot()['complete_lifecycle_count']==1
    assert current.audit.snapshot()['ordering_violation_count']==0
    assert client.xpending(current.config.stream,current.config.group)['pending']==0
    rows=client.xrange(current.config.stream)
    actual=[json.loads(row[1]['event']) for row in rows]
    assert [e['event_type'] for e in actual]==[k.value for k in (EventType.ACOUSTIC_EVENT_RECEIVED,
        EventType.EVENT_PERSISTED,EventType.POSITION_UPDATED,EventType.TRACK_UPDATED)]
    assert actual[2]['payload']['region_center_lat']==25.1 and actual[3]['payload']['last_lat']==25.2
    assert len({e['partition_key'] for e in actual})==1
    assert all(e['event_id']==e['correlation_id']=='shadow-test' and e['trace_id']=='trace-shadow-test' for e in actual)
    snapshot=json.dumps(current.snapshot())
    assert 'redis://' not in snapshot and 'rediss://' not in snapshot and 'password' not in snapshot.lower()
    stages=current.sampler.snapshot()['stages']
    for name in ('enqueue_ms','publish_ms','publish_from_ingest_ms','ack_ms','end_to_end_ms'):
        assert stages['redis_shadow_'+name]['count']>0


def test_real_shadow_recovers_pending_without_domain_effects(real_shadow):
    current,client,url=real_shadow
    old=RedisStreamsEventBus.from_url(url,stream=current.config.stream,group=current.config.group,consumer='abandoned',block_ms=10)
    old.ensure_group(); old.publish(envelope(event_id='recover',correlation_id='recover'))
    original=old.consume(1)[0]
    assert old.pending()['pending']==1
    old.close(); time.sleep(1.05)
    current.start()
    until(lambda:current.snapshot()['pending_recovered']==1)
    assert client.xpending(current.config.stream,current.config.group)['pending']==0
    assert current.audit.snapshot()['consume_success']==1
    assert current.snapshot()['consumer_db_writes'] is False and current.snapshot()['consumer_ws_broadcast'] is False
    assert current.audit.snapshot()['recent_observations'][0]['stream_id']==original.message_id


def test_pending_persisted_phase_restores_previously_acked_received_phase(real_shadow):
    current,client,url=real_shadow
    old=RedisStreamsEventBus.from_url(url,stream=current.config.stream,group=current.config.group,consumer='prior-process',block_ms=10)
    old.ensure_group()
    initial=envelope(event_id='partial',correlation_id='partial',trace_id='partial-trace')
    old.publish(initial); old.process(old.consume(1)[0],lambda e:None)
    old.publish(initial.transition(EventType.EVENT_PERSISTED,{'id':1}))
    pending=old.consume(1)[0]
    assert old.pending()['pending']==1
    old.close(); time.sleep(1.05)
    current.start()
    until(lambda:current.snapshot()['pending_recovered']==1)
    assert client.xpending(current.config.stream,current.config.group)['pending']==0
    assert current.audit.snapshot()['ordering_violation_count']==0
    assert current.snapshot()['audit_history_replayed_count']==1
    assert current.snapshot()['ack_success']==1
    assert current.audit.snapshot()['consume_success']==1
    assert current.audit.snapshot()['recent_observations'][-1]['stream_id']==pending.message_id


def test_isolated_transport_probe_recovers_and_retains_only_synthetic_entries(real_shadow):
    from services.events.redis_shadow_probe import run
    current,client,url=real_shadow
    result=run(current.config,LatencyDiagnostics())
    assert result['status']=='PASS'
    assert result['pending_before_disconnect']==1 and result['pending_final']==0
    assert result['ordering_violations']==0 and result['history_replayed']==1
    assert result['domain_db_writes'] is False and result['websocket_broadcasts'] is False
    assert result['os_process_killed'] is False
    assert result['stream']!=current.config.stream
    assert client.xlen(result['stream'])==2
    assert client.xlen(current.config.stream)==0
    assert 'redis://' not in json.dumps(result)
    client.delete(result['stream'])
