import asyncio
from copy import deepcopy
import pytest
from services.events import EventType
from services.events.handlers import PersistenceHandler, FusionHandler, TrackingHandler, RealtimeHandler
from services.events import shadow
from services.latency_diagnostics import LatencyDiagnostics
from test_event_envelope import envelope


@pytest.fixture(autouse=True)
def clean_state(monkeypatch):
    monkeypatch.setattr(shadow,'_pipeline',None)
    monkeypatch.delenv('EVENT_DRIVEN_PIPELINE_ENABLED',raising=False)
    monkeypatch.delenv('EVENT_DRIVEN_SHADOW_ENABLED',raising=False)
    monkeypatch.setenv('APP_ENV','local')


def test_handlers_delegate_explicit_inputs_and_shadow_never_calls_domain():
    calls=[]
    def persistence(data): calls.append(('persistence',data)); return {'saved_event':{'id':1}}
    def fusion(event_id): calls.append(('fusion',event_id)); return {'id':'group'}
    def tracking(group): calls.append(('tracking',group)); return {'id':'track'}
    event=envelope()
    persisted=PersistenceHandler(persistence).execute_for_test(event)
    fused=FusionHandler(fusion).execute_for_test(persisted)
    position=fused.transition(EventType.POSITION_UPDATED,fused.payload)
    track=TrackingHandler(tracking).execute_for_test(position)
    assert calls==[('persistence',event.to_dict()['payload']),('fusion','e'),('tracking',{'id':'group'})]
    async def send(data): calls.append(('realtime',dict(data)))
    assert asyncio.run(RealtimeHandler(send).execute_for_test(track)).payload==track.payload
    def forbidden(*args): pytest.fail('shadow must not invoke side effects')
    for handler, incoming in [(PersistenceHandler(forbidden),event),(FusionHandler(forbidden),persisted),
                              (TrackingHandler(forbidden),position),(RealtimeHandler(forbidden),track)]:
        assert handler.observe(incoming,{'canonical':True}).payload['canonical']
    with pytest.raises(ValueError): FusionHandler().observe(event,{})


@pytest.mark.parametrize('environment',['production','prod','', 'local','staging'])
def test_flags_default_off_and_production_cannot_enable(monkeypatch,environment):
    monkeypatch.setenv('APP_ENV',environment)
    assert shadow.flags()==(False,False) and shadow.snapshot() is None
    monkeypatch.setenv('EVENT_DRIVEN_SHADOW_ENABLED','true')
    monkeypatch.setenv('EVENT_DRIVEN_PIPELINE_ENABLED','true')
    permitted=environment in ('local','staging')
    assert shadow.flags()==(permitted,permitted)
    if not permitted:
        shadow.observe(LatencyDiagnostics(),'persistence',{}, {})
        assert shadow._pipeline is None


def test_no_mutation_ordering_errors_and_separate_metrics(monkeypatch):
    sampler=LatencyDiagnostics(); pipeline=shadow.ShadowPipeline(sampler)
    source={'event_id':'e','device_id':'node_A01','label':'uav'}
    persistence={'saved_event':{'event_id':'e','label':'drone'}}
    result={'event_group':{'id':'g','devices':['node_A01']},'region_track':{'id':'track'},'active_alert_track':None}
    copies=deepcopy((source,persistence,result))
    pipeline.observe_persistence(source,persistence)
    pipeline.observe_post_ingest('e',result)
    assert (source,persistence,result)==copies
    assert [key[1] for key in pipeline._received]==['acoustic_event_received','event_persisted','event_fused','position_updated','track_updated']
    assert pipeline.snapshot()['published']==pipeline.snapshot()['consumed']==5
    assert pipeline.comparisons==3
    assert all(key.startswith('event_bus_') for key in sampler.snapshot()['stages'])
    assert not sampler.snapshot()['critical_path_traces']
    monkeypatch.setenv('EVENT_DRIVEN_SHADOW_ENABLED','true')
    shadow.observe(sampler,'persistence',{}, {})
    assert shadow.snapshot()['shadow_errors']==1


def test_feature_off_and_shadow_on_legacy_post_ingest_parity(monkeypatch):
    import main
    sampler=LatencyDiagnostics(); monkeypatch.setattr(main,'latency_diagnostics',sampler)
    calls=[]
    group={'id':'g','label':'aircraft'}; track={'id':'t'}
    def fusion(event_id): calls.append(('fusion',event_id)); return deepcopy(group)
    def tracking(value,**kwargs): calls.append(('tracking',deepcopy(value))); return deepcopy(track)
    monkeypatch.setattr(main,'process_event_fusion_for_event',fusion)
    monkeypatch.setattr(main,'process_tracking_for_event_group_region',tracking)
    monkeypatch.setattr(main,'with_realtime_alert_timing',lambda value:value)
    monkeypatch.setattr(main,'LOCALIZATION_ENABLED',False)
    canonical=main.process_event_post_ingest('e','aircraft',False)
    assert shadow._pipeline is None
    canonical_calls=list(calls); calls.clear()
    monkeypatch.setenv('EVENT_DRIVEN_SHADOW_ENABLED','true')
    shadow.observe(sampler,'persistence',{'event_id':'e','device_id':'node','label':'aircraft'},{'saved_event':{'event_id':'e'}})
    assert main.process_event_post_ingest('e','aircraft',False)==canonical
    assert calls==canonical_calls # exactly one real Fusion and Tracking call, not two
    sent=[]
    async def broadcast(message,*args): sent.append(deepcopy(message))
    monkeypatch.setattr(main,'safe_dashboard_broadcast',broadcast)
    asyncio.run(main.broadcast_event_post_ingest_result(canonical))
    assert sent==[{'type':'event_group','group':group},{'type':'track_update','track':track}]
    snapshot=asyncio.run(main.runtime_status())
    assert snapshot['event_bus']['redis_real_traffic_enabled'] is False
    assert snapshot['event_bus']['metrics']
    monkeypatch.setenv('EVENT_DRIVEN_SHADOW_ENABLED','false')
    assert 'event_bus' not in asyncio.run(main.runtime_status())


def test_context_bounds_and_missing_result(monkeypatch):
    pipeline=shadow.ShadowPipeline(LatencyDiagnostics(),capacity=2)
    for i in range(3):
        pipeline.observe_persistence({'event_id':str(i),'device_id':'node'},{'saved_event':{'event_id':str(i)}})
    assert pipeline.context_evictions==1 and len(pipeline._contexts)==2
    with pytest.raises(ValueError): pipeline.observe_post_ingest('0',{})
    pipeline.observe_post_ingest('2',{})
    assert any(key[1]=='event_processing_failed' for key in pipeline._received)
