from concurrent.futures import ThreadPoolExecutor
import pytest
from services.events.bus import QueueFull
from services.events.memory_bus import InMemoryEventBus
from services.events.result import ProcessingResult, ProcessingStatus
from test_event_envelope import envelope


def test_bounded_duplicates_terminal_history_and_metrics():
    metrics=[]; bus=InMemoryEventBus(capacity=2,dedupe_capacity=1,recorder=lambda k,v:metrics.append((k,v)))
    event=envelope(); bus.subscribe(event.event_type,lambda e:None)
    assert bus.publish(event)
    assert not bus.publish(event)
    bus.publish(envelope(event_id='next'))
    with pytest.raises(QueueFull): bus.publish(envelope(event_id='full'))
    assert bus.snapshot()['queue_depth']==2
    assert bus.drain()==2
    assert not bus.publish(envelope(event_id='next'))
    assert bus.publish(event) # bounded history intentionally allows old terminal keys
    bus.drain()
    assert bus.snapshot()['terminal_history_size']==1
    assert {k for k,v in metrics}>={'event_bus_publish','event_bus_queue_wait','event_bus_handler_duration','event_bus_end_to_end'}
    assert all(v>=0 for k,v in metrics)


def test_concurrent_publish_and_global_fifo():
    bus=InMemoryEventBus(capacity=500); accepted=[]
    def publish(i): bus.publish(envelope(event_id=str(i)))
    with ThreadPoolExecutor(max_workers=10) as pool: list(pool.map(publish,range(100)))
    bus.subscribe(envelope().event_type,lambda e:accepted.append(e.event_id))
    assert bus.drain()==100 and len(set(accepted))==100
    assert bus.snapshot()['consumed']==100
    ordered=InMemoryEventBus(); received=[]
    ordered.subscribe(envelope().event_type,lambda e:received.append(e.event_id))
    for i in range(50): ordered.publish(envelope(event_id=str(i)))
    ordered.drain(); assert received==list(map(str,range(50)))


def test_retry_order_and_terminal_errors_no_infinite_retry():
    bus=InMemoryEventBus(max_attempts=3); attempts=[]
    def handler(event):
        attempts.append(event.event_id)
        if event.event_id=='retry' and attempts.count('retry')<3: raise TimeoutError()
        if event.event_id=='permanent': raise ValueError('payload')
        if event.event_id=='exhaust': return ProcessingResult(ProcessingStatus.RETRYABLE_FAILURE)
    bus.subscribe(envelope().event_type,handler)
    for key in ['retry','next','permanent','exhaust']: bus.publish(envelope(event_id=key))
    bus.drain()
    assert attempts==['retry']*3+['next','permanent']+['exhaust']*3
    snap=bus.snapshot(); assert snap['retries']==4 and snap['consumed']==2 and snap['failures']==2
    assert snap['queue_depth']==snap['inflight']==0
    assert [d['attempts'] for d in snap['dead_letters']]==[1,3]


def test_unknown_subscriber_and_invalid_envelope():
    bus=InMemoryEventBus()
    with pytest.raises(ValueError): bus.publish({})
    bus.publish(envelope()); bus.drain()
    assert bus.snapshot()['failures']==1
