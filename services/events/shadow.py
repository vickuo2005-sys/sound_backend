"""Observe canonical outputs only. No DB, WebSocket, executor or Redis dependency."""
from collections import OrderedDict
from threading import RLock
from time import monotonic, time_ns
import os
import math

from .envelope import EventEnvelope, thaw
from .types import EventType
from .partitioning import derive_partition_key
from .memory_bus import InMemoryEventBus
from .handlers import PersistenceHandler, FusionHandler, TrackingHandler, RealtimeHandler
from .result import ProcessingResult


def flags():
    permitted = os.getenv('APP_ENV', '').strip().lower() in ('local', 'staging')
    return (permitted and os.getenv('EVENT_DRIVEN_PIPELINE_ENABLED', 'false').lower() == 'true',
            permitted and os.getenv('EVENT_DRIVEN_SHADOW_ENABLED', 'false').lower() == 'true')


class ShadowPipeline:
    def __init__(self, sampler, capacity=256):
        self.sampler = sampler
        self._lock = RLock()
        self._contexts = OrderedDict()
        self.capacity = capacity
        self.errors = 0
        self.comparisons = 0
        self.context_evictions = 0
        self.ordering_violations = 0
        self.bus = InMemoryEventBus(capacity=capacity, recorder=sampler.record)
        self._received = OrderedDict()
        self._phases = OrderedDict()
        for kind in EventType:
            self.bus.subscribe(kind, self._observe_delivery)

    def _observe_delivery(self, event):
        start = monotonic()
        handler_name = {EventType.ACOUSTIC_EVENT_RECEIVED:'persistence', EventType.EVENT_PERSISTED:'fusion',
                        EventType.EVENT_FUSED:'fusion', EventType.POSITION_UPDATED:'tracking',
                        EventType.TRACK_UPDATED:'realtime', EventType.EVENT_PROCESSING_FAILED:'failure'}[event.event_type]
        try:
            return self._validate_delivery(event)
        finally:
            self.sampler.record('event_bus_' + handler_name + '_handler_duration', (monotonic()-start)*1000)

    def _validate_delivery(self, event):
        previous = self._phases.get(event.event_id)
        required = {EventType.EVENT_PERSISTED:EventType.ACOUSTIC_EVENT_RECEIVED,
                    EventType.EVENT_FUSED:EventType.EVENT_PERSISTED,
                    EventType.POSITION_UPDATED:EventType.EVENT_FUSED,
                    EventType.TRACK_UPDATED:EventType.POSITION_UPDATED}
        if event.event_type in required and previous != required[event.event_type]:
            self.ordering_violations += 1
            raise ValueError('Invalid shadow stage order')
        self._phases[event.event_id] = event.event_type
        self._phases.move_to_end(event.event_id)
        while len(self._phases) > self.capacity:
            self._phases.popitem(last=False)
        # Validate serialized envelope equivalence without recomputing domain mutations.
        assert EventEnvelope.from_json(event.to_json()) == event
        self._received[event.idempotency_key] = event.to_json()
        while len(self._received) > self.capacity:
            self._received.popitem(last=False)
        return ProcessingResult()

    def _publish(self, events):
        for event in events:
            self.bus.publish(event)
        self.bus.drain()

    def observe_persistence(self, event_data, result, received_at_ms=None):
        with self._lock, self.sampler.critical_scope(None):
            now = received_at_ms if received_at_ms is not None else time_ns() // 1_000_000
            event_time = event_data.get('device_event_time_ms')
            event_time_source = 'device_event_time_ms'
            if type(event_time) not in (int,float) or not math.isfinite(event_time) or event_time < 0:
                from services.event_fusion import parse_datetime
                timestamp = parse_datetime(event_data.get('timestamp'))
                event_time = int(timestamp.timestamp()*1000) if timestamp else now
                event_time_source = 'legacy_timestamp' if timestamp else 'observation_wall_clock_fallback'
            else:
                event_time = int(event_time)
            original = EventEnvelope(event_id=event_data['event_id'], correlation_id=event_data['event_id'],
                event_type=EventType.ACOUSTIC_EVENT_RECEIVED, device_id=event_data.get('device_id'),
                trace_id=event_data.get('trace_id'), event_time_ms=event_time, received_at_ms=now,
                payload=event_data, metadata={'label': event_data.get('label'), 'shadow':True,
                    'event_time_source':event_time_source})
            from dataclasses import replace
            original = replace(original, partition_key=derive_partition_key(original))
            persisted = PersistenceHandler().observe(original, result['saved_event'])
            assert thaw(persisted.payload) == result['saved_event']
            self.comparisons += 1
            self._contexts[original.event_id] = persisted
            self._contexts.move_to_end(original.event_id)
            while len(self._contexts) > self.capacity:
                self._contexts.popitem(last=False)
                self.context_evictions += 1
            self._publish([original, persisted])

    def observe_post_ingest(self, event_id, result):
        with self._lock, self.sampler.critical_scope(None):
            persisted = self._contexts.pop(event_id, None)
            if persisted is None:
                raise ValueError('No captured persistence context')
            group = result.get('event_group')
            if not group:
                failed = persisted.transition(EventType.EVENT_PROCESSING_FAILED, {'error_class':'NoFusionResult'})
                self._publish([failed])
                return
            fused = FusionHandler().observe(persisted, group)
            position = fused.transition(EventType.POSITION_UPDATED, group)
            assert thaw(fused.payload) == group
            track = result.get('region_track') or result.get('active_alert_track')
            events = [fused, position]
            self.comparisons += 1
            if track:
                updated = TrackingHandler().observe(position, track)
                observed_realtime = RealtimeHandler().observe(updated, track)
                assert thaw(observed_realtime.payload) == track
                events.append(updated)
                self.comparisons += 1
            self._publish(events)

    def snapshot(self):
        with self._lock:
            return {**self.bus.snapshot(), 'shadow_errors':self.errors, 'comparisons':self.comparisons,
                    'context_evictions':self.context_evictions, 'context_count':len(self._contexts),
                    'ordering_violations':self.ordering_violations,
                    'event_bus_retry_count':self.bus.snapshot()['retries'],
                    'event_bus_duplicate_count':self.bus.snapshot()['duplicates'],
                    'mode':'canonical-result projection only; no independent algorithm recomputation'}


_pipeline = None
_pipeline_lock = RLock()


def observe(sampler, stage, *args):
    """Failure isolation applies only to observation. Legacy errors are not swallowed here."""
    global _pipeline
    if not flags()[1]:
        return
    with _pipeline_lock:
        if _pipeline is None:
            _pipeline = ShadowPipeline(sampler)
        try:
            getattr(_pipeline, 'observe_' + stage)(*args)
        except Exception:
            _pipeline.errors += 1


def snapshot():
    enabled, shadow_enabled = flags()
    if not (enabled or shadow_enabled):
        return None
    with _pipeline_lock:
        return {'enabled':enabled, 'shadow_enabled':shadow_enabled, 'legacy_authoritative':True,
                'redis_real_traffic_enabled':False, 'pipeline_flag_reserved':True,
                **(_pipeline.snapshot() if _pipeline else {
                    'implementation':'memory', 'queue_depth':0, 'peak_queue_depth':0,
                    'published':0, 'consumed':0, 'retries':0, 'failures':0})}
