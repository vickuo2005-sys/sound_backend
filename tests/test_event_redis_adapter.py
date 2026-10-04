from unittest.mock import Mock
import pytest
from services.events.redis_streams import RedisStreamsEventBus, RedisDelivery
from services.events.result import ProcessingResult, ProcessingStatus
from test_event_envelope import envelope


def client():
    obj=Mock(); obj.xadd.return_value=b'1-0'; obj.xpending_range.return_value=[{'times_delivered':1}]
    return obj


def test_serialization_ack_pending_claim_and_no_trim():
    c=client(); event=envelope(); bus=RedisStreamsEventBus(c)
    assert bus.publish(event)=='1-0'
    assert c.xadd.call_args.args==('acoustic_events',{'event':event.to_json()})
    assert c.xadd.call_args.kwargs=={}
    entries=[(b'1-0',{b'event':event.to_json().encode()})]
    c.xreadgroup.return_value=[(b'acoustic_events',entries)]
    delivery=bus.consume()[0]; assert delivery.event==event
    assert c.xreadgroup.call_args.kwargs['block']==100
    bus.ack(delivery); c.xack.assert_called_once_with('acoustic_events','event_driven_v1','1-0')
    c.xclaim.return_value=entries; assert bus.claim(['1-0'])[0]==delivery
    c.xautoclaim.return_value=[b'0-0',entries,[]]; assert bus.auto_claim()==('0-0',[delivery])
    bus.pending(); c.xpending.assert_called_once()
    c.xdel.assert_not_called(); c.xtrim.assert_not_called()


def test_reconnect_is_bounded_and_shutdown():
    c=client(); c.xadd.side_effect=[ConnectionError(),b'1-0']; bus=RedisStreamsEventBus(c)
    assert bus.publish(envelope())=='1-0' and c.xadd.call_count==2
    c.xadd.side_effect=ConnectionError()
    with pytest.raises(ConnectionError): bus.publish(envelope())
    assert c.xadd.call_count==5
    bus.close(); assert bus.consume()==[]
    with pytest.raises(RuntimeError): bus.publish(envelope())
    c.close.assert_called_once()


def test_malformed_retryable_permanent_exhausted_and_ack_semantics():
    c=client(); bus=RedisStreamsEventBus(c,max_attempts=2)
    c.xreadgroup.return_value=[('acoustic_events',[('1-0',{'event':'malformed'})])]
    malformed=bus.consume()[0]; assert malformed.event is None
    bus.process(malformed,lambda e:pytest.fail('malformed event invoked handler'))
    c.pipeline.assert_called_with(transaction=True)
    c.pipeline.return_value.xack.assert_called_once()
    delivery=RedisDelivery('2-0',envelope())
    result=bus.process(delivery,lambda e:ProcessingResult(ProcessingStatus.RETRYABLE_FAILURE,'TimeoutError'))
    assert result.status==ProcessingStatus.RETRYABLE_FAILURE
    c.xack.assert_not_called()
    c.xpending_range.return_value=[{'times_delivered':2}]
    bus.process(delivery,lambda e:ProcessingResult(ProcessingStatus.RETRYABLE_FAILURE))
    assert c.pipeline.call_count==2
    bus.process(delivery,lambda e:None); c.xack.assert_called_once()


def test_group_creation_errors_and_bounds():
    c=client(); bus=RedisStreamsEventBus(c)
    bus.ensure_group(); c.xgroup_create.assert_called_once_with('acoustic_events','event_driven_v1',id='0-0',mkstream=True)
    c.xgroup_create.side_effect=RuntimeError('BUSYGROUP existing'); assert bus.ensure_group() is False
    c.xgroup_create.side_effect=RuntimeError('permission')
    with pytest.raises(RuntimeError): bus.ensure_group()
    with pytest.raises(ValueError): RedisStreamsEventBus(c,block_ms=0)
    with pytest.raises(ValueError): bus.consume(0)
    with pytest.raises(ValueError): bus.claim([])
