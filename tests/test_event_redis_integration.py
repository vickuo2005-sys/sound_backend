"""Real Redis only. No fakeredis substitute; an explicit disposable loopback URL is required."""
import os
from urllib.parse import urlsplit
import uuid
import pytest
from services.events.redis_streams import RedisStreamsEventBus
from services.events.result import ProcessingResult, ProcessingStatus
from test_event_envelope import envelope


@pytest.fixture
def redis_bus():
    url=os.getenv('EVENT_DRIVEN_TEST_REDIS_URL')
    if not url:
        pytest.skip('No disposable local Redis/Docker configured; real integration NOT TESTED')
    assert urlsplit(url).hostname in ('localhost','127.0.0.1','::1'), 'Cloud/shared Redis forbidden for tests'
    pytest.importorskip('redis')
    stream='codex-event-v1-'+uuid.uuid4().hex
    bus=RedisStreamsEventBus.from_url(url,stream=stream,group='test',consumer='first',block_ms=10,max_attempts=2)
    bus.client.ping(); bus.ensure_group()
    yield bus,url
    bus.client.delete(stream,stream+':dlq') # only this disposable test namespace
    bus.close()


@pytest.mark.parametrize('case',['publish','consume','ack','crash_before_ack','pending_recovery',
    'duplicate_delivery','reconnect','malformed','retryable_failure','permanent_failure',
    'same_partition_order','independent_partitions','4_node_burst','20_node_burst','100_node_burst'])
def test_real_redis_contract(redis_bus,case):
    bus,url=redis_bus
    if case=='malformed':
        bus.client.xadd(bus.stream,{'event':'broken'})
        delivery=bus.consume()[0]
        assert delivery.event is None
        bus.process(delivery,lambda e:pytest.fail('malformed invoked handler'))
        assert bus.pending()['pending']==0 and bus.client.xlen(bus.stream+':dlq')==1
        return
    count={'4_node_burst':4,'20_node_burst':20,'100_node_burst':100,'same_partition_order':20,'independent_partitions':20}.get(case,1)
    for i in range(count):
        bus.publish(envelope(event_id=str(i),device_id=f'node_{i}',partition_key='aircraft' if case!='independent_partitions' else str(i%2)))
    deliveries=bus.consume(count=count)
    assert len(deliveries)==count
    assert [d.event.event_id for d in deliveries]==list(map(str,range(count)))
    if case in ('crash_before_ack','pending_recovery','duplicate_delivery'):
        assert bus.pending()['pending']==count
        recovery=RedisStreamsEventBus.from_url(url,stream=bus.stream,group=bus.group,consumer='replacement',block_ms=10)
        try:
            _,claimed=recovery.auto_claim(min_idle_ms=0)
            assert {d.message_id for d in claimed}=={d.message_id for d in deliveries}
            # No ACK before takeover models a crashed consumer; duplicate effects prevented by consumer key.
            seen=set(); effects=[]
            def handler(event):
                if event.idempotency_key not in seen:
                    seen.add(event.idempotency_key); effects.append(event.event_id)
            for d in deliveries+claimed: handler(d.event)
            assert len(effects)==count
            for d in claimed: recovery.ack(d)
            assert recovery.pending()['pending']==0
        finally: recovery.close()
        return
    if case=='retryable_failure':
        result=bus.process(deliveries[0],lambda e:ProcessingResult(ProcessingStatus.RETRYABLE_FAILURE,'TimeoutError'))
        assert result.status==ProcessingStatus.RETRYABLE_FAILURE and bus.pending()['pending']==1
        claimed=bus.claim([deliveries[0].message_id],min_idle_ms=0)
        bus.process(claimed[0],lambda e:ProcessingResult(ProcessingStatus.RETRYABLE_FAILURE,'TimeoutError'))
        assert bus.pending()['pending']==0 and bus.client.xlen(bus.stream+':dlq')==1
        return
    if case=='permanent_failure':
        bus.process(deliveries[0],lambda e:ProcessingResult(ProcessingStatus.PERMANENT_FAILURE,'ValueError'))
        assert bus.pending()['pending']==0 and bus.client.xlen(bus.stream+':dlq')==1
        return
    if case=='reconnect':
        bus.client.connection_pool.disconnect()
        assert bus.publish(envelope(event_id='reconnected'))
    for delivery in deliveries: bus.process(delivery,lambda e:None)
    assert bus.pending()['pending']==0
    assert bus.client.xlen(bus.stream)>=count # ACK does not XDEL
