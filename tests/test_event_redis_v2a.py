"""Real-server regressions for identity, transaction ambiguity and retained PEL."""
import pytest
from test_event_redis_integration import redis_bus
from test_event_envelope import envelope
from services.events.result import ProcessingResult, ProcessingStatus


@pytest.mark.parametrize('growth,expected',[(0,False),(5,True),(100,True)])
def test_overload_detects_marginal_sustained_growth(growth,expected):
    from tools.validate_real_redis import overload_window
    samples=[{'elapsed_s':second,'published':150*second,'completed':(150-growth)*second,
        'backlog':growth*second} for second in range(1,5)]
    result=overload_window(samples,4)
    assert result['overload'] is expected
    assert result['ingest_eps']==150 and result['consume_eps']==150-growth


def test_dlq_preserves_validated_trace_identity_without_payload(redis_bus):
    bus,_=redis_bus
    bus.publish(envelope(event_id='original',trace_id='trace-original'))
    delivery=bus.consume(1)[0]
    bus.process(delivery,lambda e:ProcessingResult(ProcessingStatus.PERMANENT_FAILURE,'SyntheticError'))
    rows=bus.client.xrange(bus.stream+':dlq')
    assert len(rows)==1
    assert rows[0][1]=={'source_id':delivery.message_id,'event_id':'original',
        'trace_id':'trace-original','error_class':'SyntheticError'}
    assert bus.pending()['pending']==0
    assert bus.client.xlen(bus.stream)==1


def test_ambiguous_exec_can_duplicate_dlq_but_ack_is_atomic(redis_bus,monkeypatch):
    import redis
    bus,_=redis_bus
    bus.publish(envelope(event_id='ambiguous',trace_id='trace-ambiguous'))
    delivery=bus.consume(1)[0]
    original=bus.client.pipeline
    calls=[]
    def pipeline(*args,**kwargs):
        pipe=original(*args,**kwargs); execute=pipe.execute
        def ambiguous(*a,**kw):
            result=execute(*a,**kw)
            calls.append(result)
            if len(calls)==1:
                raise redis.ConnectionError('Injected lost EXEC reply after server applied transaction')
            return result
        pipe.execute=ambiguous
        return pipe
    monkeypatch.setattr(bus.client,'pipeline',pipeline)
    bus.process(delivery,lambda e:ProcessingResult(ProcessingStatus.PERMANENT_FAILURE,'SyntheticError'))
    assert len(calls)==2 and calls[0][1]==1 and calls[1][1]==0
    rows=bus.client.xrange(bus.stream+':dlq')
    assert len(rows)==2 # honest at-least-once DLQ, never an exactly-once claim
    assert all(row[1]['event_id']=='ambiguous' and row[1]['trace_id']=='trace-ambiguous' for row in rows)
    assert bus.pending()['pending']==0


def test_minid_trim_keeps_pending_recoverable(redis_bus):
    bus,_=redis_bus
    ids=[bus.publish(envelope(event_id=str(i))) for i in range(5)]
    deliveries=bus.consume(5)
    for delivery in deliveries[:2]: bus.ack(delivery)
    assert bus.client.xlen(bus.stream)==5 and bus.pending()['pending']==3
    assert bus.client.xtrim(bus.stream,minid=bus.pending()['min'],approximate=False)==2
    _,claimed=bus.auto_claim(min_idle_ms=0)
    assert [d.message_id for d in claimed]==ids[2:]
    for delivery in claimed: bus.process(delivery,lambda e:None)
    assert bus.pending()['pending']==0 and bus.client.xlen(bus.stream)==3
