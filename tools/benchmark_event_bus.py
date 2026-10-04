"""Synthetic architecture-only bursts. No main import, DB, sockets or cloud services."""
from collections import defaultdict
import json
from pathlib import Path
import sys
from time import monotonic
import tracemalloc

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from services.events import EventEnvelope, EventType
from services.events.bus import QueueFull
from services.events.memory_bus import InMemoryEventBus


def run(nodes,events_per_node=20):
    samples=defaultdict(list); lag=[]; last={}; violations=0
    bus=InMemoryEventBus(capacity=128,dedupe_capacity=256,recorder=lambda k,v:samples[k].append(v))
    def handle(event):
        nonlocal violations
        partition=event.partition_key; sequence=event.payload['sequence']
        if sequence<=last.get(partition,-1): violations+=1
        last[partition]=sequence
        lag.append((monotonic()-event.metadata['published_monotonic'])*1000)
    bus.subscribe(EventType.ACOUSTIC_EVENT_RECEIVED,handle)
    tracemalloc.start(); total_start=monotonic(); publish_duration=0
    for i in range(nodes*events_per_node):
        event=EventEnvelope(event_id=f'load-{nodes}-{i}',event_type=EventType.ACOUSTIC_EVENT_RECEIVED,
            correlation_id=f'load-{nodes}-{i}',device_id=f'node_{i%nodes}',partition_key='aircraft',
            event_time_ms=i,received_at_ms=i,payload={'label':'aircraft','sequence':i},
            metadata={'published_monotonic':monotonic(),'synthetic':True})
        while True:
            start=monotonic()
            try:
                bus.publish(event); publish_duration+=monotonic()-start; break
            except QueueFull:
                publish_duration+=monotonic()-start
                bus.drain(limit=32) # explicit backpressure, no silent event loss
    bus.drain()
    elapsed=monotonic()-total_start; _,peak=tracemalloc.get_traced_memory(); tracemalloc.stop()
    stats=bus.snapshot(); assert stats['published']==stats['consumed']==nodes*events_per_node
    assert violations==stats['failures']==stats['queue_depth']==0
    assert stats['peak_queue_depth']<=128 and stats['terminal_history_size']<=256
    sorted_lag=sorted(lag)
    return {'nodes':nodes,'synthetic_events':nodes*events_per_node,'elapsed_ms':elapsed*1000,
        'publish_throughput_per_second':nodes*events_per_node/publish_duration,
        'consume_handler_throughput_per_second':nodes*events_per_node/(sum(samples['event_bus_handler_duration'])/1000),
        'overall_throughput_per_second':nodes*events_per_node/elapsed,
        'processing_lag_p95_ms':sorted_lag[int((len(lag)-1)*.95)],'processing_lag_max_ms':max(lag),
        'python_allocations_peak_bytes':peak,'memory_scope':'tracemalloc Python allocations; not RSS/Render memory',
        'ordering_violations':violations,'bus':stats}


if __name__=='__main__':
    results={'environment':'LOCAL_SYNTHETIC_ENVELOPE_ONLY','not_acoustic_field_sla':True,
        'results':[run(nodes) for nodes in (4,20,50,100)]}
    (ROOT/'outputs/event_driven_load.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
    print(json.dumps(results,indent=2))
