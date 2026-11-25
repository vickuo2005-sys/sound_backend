from dataclasses import FrozenInstanceError
import math
import pytest
from services.events import EventEnvelope, EventType
from services.events.partitioning import derive_partition_key


def envelope(**kwargs):
    return EventEnvelope(**dict(dict(event_id='e', correlation_id='e', event_type=EventType.ACOUSTIC_EVENT_RECEIVED,
        event_time_ms=1, received_at_ms=2, device_id='node_A01', payload={'label':'Drone', 'audio_path':'file.wav'}), **kwargs))


def test_roundtrip_unicode_long_id_extensions_and_determinism():
    event=envelope(event_id='聲音'*3000, metadata={'x':['中文',None]})
    decoded=EventEnvelope.from_json(event.to_json())
    assert decoded==event
    assert decoded.to_json()==event.to_json()
    extended=EventEnvelope.from_dict({**event.to_dict(),'future_optional':42})
    assert extended.extensions['future_optional']==42
    assert EventEnvelope.from_json(extended.to_json())==extended
    assert event.site_id is None and event.trace_id is None


def test_deep_immutability_and_copy():
    value={'nested':[{'x':1}]}; event=envelope(payload=value)
    value['nested'][0]['x']=2
    assert event.payload['nested'][0]['x']==1
    with pytest.raises(TypeError): event.payload['nested'][0]['x']=3
    with pytest.raises(FrozenInstanceError): event.event_id='changed'
    copy=event.to_dict(); copy['payload']['nested'][0]['x']=4
    assert event.payload['nested'][0]['x']==1


@pytest.mark.parametrize('change',[{'schema_version':2},{'schema_version':True},{'event_id':''},
    {'event_type':'unknown'},{'event_time_ms':-1},{'received_at_ms':True},{'payload':[]},
    {'payload':{'raw_audio':b'abc'}},{'payload':{'audio_base64':'YWJj'}},{'payload':{'x':math.nan}},
    {'metadata':{'authorization':'secret'}},{'payload':{'nested':{'upload_token':'secret'}}},
    {'payload':{'audio_path':'https://user:password@example.com/a'}}])
def test_invalid_schema_and_sensitive_data(change):
    with pytest.raises(ValueError): envelope(**change)


def test_missing_required_and_stable_types():
    with pytest.raises(ValueError): EventEnvelope.from_dict({})
    assert len(EventType)==6
    assert derive_partition_key(envelope())=='drone'
    assert envelope().transition(EventType.EVENT_PERSISTED,{'id':1}).event_id=='e'
