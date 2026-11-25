"""Staging-only, bounded, lossy observer. No domain DB/algorithm/WebSocket imports.

Enqueue only projects a fixed set of scalar canonical fields. JSON serialization,
Redis and audit work run on dedicated shadow threads. Redis never controls HTTP.
"""
from collections import Counter, OrderedDict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
import os
import re
from queue import Queue, Empty, Full
from threading import Event, RLock, Thread
from time import monotonic, monotonic_ns, time_ns
from urllib.parse import urlsplit
from uuid import uuid4

from .envelope import EventEnvelope, freeze
from .types import EventType
from .redis_streams import RedisStreamsEventBus
from .result import ProcessingResult, ProcessingStatus


def enabled():
    return os.getenv('APP_ENV','').lower()=='staging' and os.getenv('REDIS_SHADOW_ENABLED','false').lower()=='true'


@dataclass(frozen=True)
class Config:
    url: str
    stream: str = 'staging:acoustic-events:v1'
    group: str = 'staging-shadow-audit-v1'
    consumer: str = 'staging-shadow-single'
    capacity: int = 256
    max_bytes: int = 65536
    audit_capacity: int = 4096
    lifecycle_timeout_s: float = 60
    allow_loopback_test: bool = False

    def __post_init__(self):
        parsed=urlsplit(self.url)
        local=self.allow_loopback_test and parsed.hostname in ('127.0.0.1','localhost','::1')
        if not local and (parsed.scheme!='rediss' or not parsed.password):
            raise ValueError('Remote shadow Redis requires TLS and authentication')
        if not self.stream.startswith('staging:') or not self.group.startswith('staging-'):
            raise ValueError('Staging namespace required')
        if not all(re.fullmatch(r'[A-Za-z0-9:_-]{1,128}',v) for v in (self.stream,self.group,self.consumer)):
            raise ValueError('Safe bounded diagnostic names required')
        if not 1<=self.capacity<=4096 or not 1024<=self.max_bytes<=1048576 or not 16<=self.audit_capacity<=16384:
            raise ValueError('Bounded shadow settings required')
        if not 1<=self.lifecycle_timeout_s<=600: raise ValueError('Bounded lifecycle timeout required')

    @classmethod
    def environment(cls):
        if os.getenv('REDIS_SHADOW_CONSUMERS','1')!='1': raise ValueError('Exactly one shadow consumer required')
        if os.getenv('EVENT_DRIVEN_PIPELINE_ENABLED','false').lower()!='false' or os.getenv('REDIS_REAL_TRAFFIC_ENABLED','false').lower()!='false':
            raise ValueError('Authoritative event-driven flags must remain false')
        return cls(os.getenv('REDIS_SHADOW_URL',''),os.getenv('REDIS_SHADOW_STREAM','staging:acoustic-events:v1'),
            os.getenv('REDIS_SHADOW_GROUP','staging-shadow-audit-v1'),os.getenv('REDIS_SHADOW_CONSUMER','staging-shadow-single'),
            int(os.getenv('REDIS_SHADOW_QUEUE_MAX','256')),int(os.getenv('REDIS_SHADOW_MAX_EVENT_BYTES','65536')))


FIELDS=('event_id','device_id','label','timestamp','latitude','longitude','effective_latitude',
    'effective_longitude','confidence','audio_path','audio_object_key','group_id','track_id','id',
    'estimated_latitude','estimated_longitude','estimated_lat','estimated_lng','region_center_lat',
    'region_center_lng','last_lat','last_lng','node_count','reporting_node_count',
    'localization_method','tdoa_node_count','status')


def project(source):
    """Fixed-size field set; no nested/raw audio or arbitrary metadata retained."""
    result={}
    for key in FIELDS:
        value=source.get(key) if isinstance(source,dict) else getattr(source,key,None)
        if value is None or type(value) in (str,int,bool): result[key]=value
        elif type(value) is float and math.isfinite(value): result[key]=value
    return result


class Audit:
    def __init__(self, capacity=4096, timeout=60):
        self.capacity=capacity; self.timeout=timeout; self.contexts=OrderedDict()
        self.seen=OrderedDict(); self.counts=Counter(); self.evidence=deque(maxlen=256)
        self.lock=RLock()

    def expire(self):
        now=monotonic()
        with self.lock:
            for key,state in list(self.contexts.items()):
                if now-state['time']>self.timeout:
                    if not state['complete']: self.counts['missing_phase_count']+=1
                    del self.contexts[key]

    def observe(self, delivery):
        with self.lock:
            e=delivery.event
            if e is None:
                self.counts['malformed_count']+=1
                if delivery.error_class=='ValueError': self.counts['unknown_or_invalid_schema_count']+=1
                return ProcessingResult(ProcessingStatus.PERMANENT_FAILURE,'InvalidShadowEnvelope')
            key=(e.event_id,e.event_type.value)
            if e.correlation_id!=e.event_id:
                self.counts['correlation_mismatch_count']+=1
                return ProcessingResult(ProcessingStatus.PERMANENT_FAILURE,'ShadowCorrelationMismatch')
            try:
                freeze({'identity':[e.event_id,e.correlation_id,e.trace_id,e.device_id]})
            except ValueError:
                self.counts['malformed_count']+=1
                return ProcessingResult(ProcessingStatus.PERMANENT_FAILURE,'ShadowUnsafeIdentity')
            if key in self.seen:
                self.counts['duplicate_count']+=1; self.counts['duplicate_phase_count']+=1
                return ProcessingResult()
            self.seen[key]=True
            while len(self.seen)>self.capacity: self.seen.popitem(last=False)
            state=self.contexts.get(e.event_id)
            if state is None:
                state={'phases':[],'complete':False,'time':monotonic(),'identity':(e.trace_id,e.device_id)}
                self.contexts[e.event_id]=state
            if state['identity']!=(e.trace_id,e.device_id):
                self.counts['correlation_mismatch_count']+=1
                return ProcessingResult(ProcessingStatus.PERMANENT_FAILURE,'ShadowIdentityMismatch')
            if len(self.contexts)>self.capacity:
                _,old=self.contexts.popitem(last=False)
                self.counts['audit_context_evictions']+=1
                if not old['complete']: self.counts['missing_phase_count']+=1
            expected={EventType.EVENT_PERSISTED:EventType.ACOUSTIC_EVENT_RECEIVED,
                EventType.POSITION_UPDATED:EventType.EVENT_PERSISTED,
                EventType.TRACK_UPDATED:EventType.POSITION_UPDATED,
                EventType.EVENT_PROCESSING_FAILED:EventType.EVENT_PERSISTED}
            previous=state['phases'][-1] if state['phases'] else None
            violation=(e.event_type in expected and previous!=expected[e.event_type]) or (e.event_type==EventType.ACOUSTIC_EVENT_RECEIVED and previous is not None)
            if violation:
                self.counts['ordering_violation_count']+=1
                return ProcessingResult(ProcessingStatus.PERMANENT_FAILURE,'ShadowPhaseOrder')
            state['phases'].append(e.event_type); state['time']=monotonic()
            terminal=e.event_type in (EventType.TRACK_UPDATED,EventType.EVENT_PROCESSING_FAILED) or (e.event_type==EventType.POSITION_UPDATED and not e.metadata.get('expected_track'))
            if terminal and not state['complete']:
                state['complete']=True; self.counts['complete_lifecycle_count']+=1
            self.counts['consume_success']+=1
            self.evidence.append({'event_id':e.event_id,'correlation_id':e.correlation_id,'trace_id':e.trace_id,
                'device_id':e.device_id,'event_type':e.event_type.value,'stream_id':delivery.message_id})
            return ProcessingResult()

    def snapshot(self):
        with self.lock:
            return {**{k:self.counts[k] for k in ('consume_success','duplicate_count','duplicate_phase_count',
                'ordering_violation_count','malformed_count','correlation_mismatch_count','unknown_or_invalid_schema_count',
                'unknown_event_type_count',
                'missing_phase_count','complete_lifecycle_count','audit_context_evictions')},
                'audit_context_count':len(self.contexts),'recent_observations':list(self.evidence),
                'missing_phase_scope':'expired/evicted incomplete lifecycles; queue rejections separately counted'}


class RedisShadow:
    def __init__(self, config, sampler, factory=None):
        self.config=config; self.sampler=sampler
        self.factory=factory or (lambda consumer: RedisStreamsEventBus.from_url(config.url,stream=config.stream,
            group=config.group,consumer=consumer,block_ms=100,max_reconnect_attempts=2))
        self.queue=Queue(config.capacity); self.lock=RLock(); self.stop_event=Event()
        self.counts=Counter(); self.boot=uuid4().hex; self.contexts=OrderedDict(); self.timelines=OrderedDict()
        self.audit=Audit(config.audit_capacity,config.lifecycle_timeout_s)
        self.threads=[]; self.buses=set(); self.connected=False; self.last_error_class=None
        self.pending=0; self.lag=0; self.stream_length=0; self.memory_bytes=None
        self.transport_probe=None
        self.last_rejection=None

    def inc(self,name,n=1):
        with self.lock: self.counts[name]+=n

    def record(self,key,start,end=None):
        self.sampler.record('redis_shadow_'+key,( (end if end is not None else monotonic_ns())-start)/1e6)

    def enqueue(self,context,phases):
        started=monotonic_ns()
        try:
            # Avoid retaining already enormous scalar identifiers/references in a queue.
            scalars=list(context.values())+[v for _,payload,_ in phases for v in payload.values()]
            if sum(len(v) for v in scalars if isinstance(v,str))>self.config.max_bytes:
                self.inc('oversize_rejected'); return False
            self.queue.put_nowait((dict(context),phases,started))
            with self.lock:
                self.counts['enqueue_success']+=1
                self.counts['peak_queue_depth']=max(self.counts['peak_queue_depth'],self.queue.qsize())
            return True
        except Full:
            self.inc('enqueue_rejected'); return False
        finally: self.record('enqueue_ms',started)

    def initial(self,event,result,received_ms,received_monotonic):
        identifier=event.event_id
        device_time=getattr(event,'device_event_time_ms',None)
        if type(device_time) not in (int,float) or not math.isfinite(device_time) or device_time<0:
            try:
                parsed=datetime.fromisoformat(event.timestamp.replace('Z','+00:00'))
                if parsed.tzinfo is None: parsed=parsed.replace(tzinfo=timezone.utc)
                device_time=int(parsed.timestamp()*1000)
            except (ValueError,AttributeError,OverflowError): device_time=received_ms
        context={'event_id':identifier,'correlation_id':identifier,'trace_id':getattr(event,'trace_id',None),
            'device_id':event.device_id,'event_time_ms':int(device_time) if type(device_time) in (int,float) and math.isfinite(device_time) and device_time>=0 else received_ms,
            'received_at_ms':received_ms,'t0_ns':int(received_monotonic*1e9),'partition_key':str(event.label)}
        with self.lock:
            self.contexts[identifier]=context
            self.contexts.move_to_end(identifier)
            while len(self.contexts)>self.config.audit_capacity:
                self.contexts.popitem(last=False); self.counts['publisher_context_evictions']+=1
        return self.enqueue(context,[(EventType.ACOUSTIC_EVENT_RECEIVED,project(event),{}),
            (EventType.EVENT_PERSISTED,project(result.get('saved_event') or {}),{})])

    def post_ingest(self,event_id,result):
        with self.lock: context=self.contexts.pop(event_id,None)
        if context is None: self.inc('missing_publisher_context'); return False
        group=result.get('event_group'); track=result.get('region_track') or result.get('active_alert_track')
        if not group:
            return self.enqueue(context,[(EventType.EVENT_PROCESSING_FAILED,{'reason':'CanonicalLegacyNoFusionResult'},{})])
        phases=[(EventType.POSITION_UPDATED,project(group),{'expected_track':bool(track)})]
        if track: phases.append((EventType.TRACK_UPDATED,project(track),{}))
        return self.enqueue(context,phases)

    def start(self):
        if self.threads: return
        self.threads=[Thread(target=self.publisher,name='redis-shadow-publisher',daemon=True),
            Thread(target=self.consumer,name='redis-shadow-audit',daemon=True)]
        for worker in self.threads: worker.start()

    def connect(self,name):
        transport=self.factory(name)
        try: transport.ensure_group()
        except Exception:
            transport.close(); raise
        with self.lock: self.buses.add(transport)
        return transport

    def disconnect(self,transport):
        if transport:
            transport.close()
            with self.lock: self.buses.discard(transport)

    def publisher(self):
        transport=None
        while not self.stop_event.is_set():
            try: job=self.queue.get(timeout=.1)
            except Empty: continue
            context,phases,t1=job
            try:
                for kind,payload,extra in phases:
                    freeze(context) # Reject credential URLs even in identifiers.
                    token=uuid4().hex
                    e=EventEnvelope(**{k:v for k,v in context.items() if k!='t0_ns'},event_type=kind,payload=payload,
                        metadata={'shadow':True,'boot_id':self.boot,'observation_id':token,'t0_ns':context['t0_ns'],
                            't1_ns':t1,'label':context['partition_key'],**extra})
                    from dataclasses import replace
                    from .partitioning import derive_partition_key
                    e=replace(e,partition_key=derive_partition_key(e))
                    size=len(e.to_json().encode('utf-8'))
                    if size>self.config.max_bytes:
                        self.inc('oversize_rejected')
                        with self.lock:
                            self.counts['last_rejected_size_bytes']=size
                            self.last_rejection={'event_id':e.event_id[:128],
                                'event_type':kind.value,'serialized_size_bytes':size}
                        continue
                    if transport is None: transport=self.connect('publisher')
                    started=monotonic_ns(); transport.publish(e); t2=monotonic_ns()
                    with self.lock:
                        self.timelines[token]=t2
                        while len(self.timelines)>self.config.audit_capacity: self.timelines.popitem(last=False)
                    self.inc('xadd_success'); self.record('publish_ms',started,t2)
                    self.record('publish_from_ingest_ms',context['t0_ns'],t2)
            except Exception as error:
                self.inc('xadd_failure'); self.inc('reconnect_count')
                self.last_error_class=type(error).__name__
                self.disconnect(transport)
                transport=None
                self.stop_event.wait(.2) # bounded lossy shadow, never indefinite requeue
            finally: self.queue.task_done()

    def consume_delivery(self,transport,delivery):
        t3=monotonic_ns(); e=delivery.event
        if e is None:
            # Inspect only the failed entry to distinguish unknown type from malformed JSON.
            rows=transport.client.xrange(self.config.stream,min=delivery.message_id,max=delivery.message_id,count=1)
            try:
                raw=rows[0][1].get('event','') if rows else ''
                if len(raw.encode())<=self.config.max_bytes:
                    value=json.loads(raw)
                    if isinstance(value,dict) and value.get('event_type') not in {k.value for k in EventType}:
                        self.audit.counts['unknown_event_type_count']+=1
            except (ValueError,TypeError): pass
        # malformed entries still pass through the audit counter before transport DLQ.
        result=self.audit.observe(delivery)
        started=monotonic_ns()
        transport.process(delivery,lambda _:result)
        t4=monotonic_ns(); self.inc('ack_success'); self.record('ack_ms',started,t4)
        if e and e.metadata.get('boot_id')==self.boot:
            self.record('end_to_end_ms',e.metadata['t0_ns'],t4)
            with self.lock: t2=self.timelines.pop(e.metadata.get('observation_id'),None)
            if t2 is not None and t3>=t2: self.record('consumer_lag_ms',t2,t3)
            else: self.inc('consumer_before_publish_reply_count')
        elif e: self.inc('clock_domain_unavailable_count')

    def consumer(self):
        transport=None; next_status=0; history_loaded=False
        if os.getenv('REDIS_SHADOW_TRANSPORT_PROBE','false').lower()=='true':
            # Staging-only runtime already gated at start(). Separate namespace
            # and sampler: synthetic rehearsal must not contaminate canary data.
            from .redis_shadow_probe import run
            from services.latency_diagnostics import LatencyDiagnostics
            self.transport_probe=run(self.config,LatencyDiagnostics())
        while not self.stop_event.is_set():
            try:
                if transport is None: transport=self.connect(self.config.consumer)
                if not history_loaded:
                    self.restore_audit_history(transport)
                    history_loaded=True
                self.connected=True
                # Claim abandoned PEL entries; one consumer, no domain side effects.
                _,recovered=transport.auto_claim(min_idle_ms=1000,count=100)
                for delivery in recovered:
                    self.consume_delivery(transport,delivery); self.inc('pending_recovered')
                for delivery in transport.consume(count=100): self.consume_delivery(transport,delivery)
                if monotonic()>=next_status:
                    groups=transport.client.xinfo_groups(self.config.stream)
                    group=next(g for g in groups if g['name']==self.config.group)
                    with self.lock:
                        self.pending=group['pending']; self.lag=group.get('lag')
                        self.stream_length=transport.client.xlen(self.config.stream)
                        self.counts['pending_peak']=max(self.counts['pending_peak'],self.pending)
                        self.counts['consumer_lag_peak']=max(self.counts['consumer_lag_peak'],self.lag or 0)
                    # Managed services can restrict INFO; failure must not stop audit.
                    try: self.memory_bytes=transport.client.info('memory').get('used_memory')
                    except Exception: self.inc('memory_info_unavailable')
                    self.audit.expire(); next_status=monotonic()+1
            except Exception as error:
                self.connected=False; self.last_error_class=type(error).__name__
                self.inc('consumer_failure'); self.inc('reconnect_count')
                self.disconnect(transport)
                transport=None; self.stop_event.wait(.5)

    def restore_audit_history(self,transport):
        """Rebuild prior ACKed phases after process restart, not domain effects.

        Retained history is read only and bounded. Do not call these entries new
        deliveries/ACKs or include them in latency samples. Pending recovery can
        otherwise falsely call a valid persisted/position phase out of order.
        """
        pending=transport.pending()
        group=next(g for g in transport.client.xinfo_groups(self.config.stream) if g['name']==self.config.group)
        boundary='('+pending['min'] if pending['pending'] else group['last-delivered-id']
        rows=transport.client.xrevrange(self.config.stream,max=boundary,min='-',count=self.config.audit_capacity)
        deliveries=transport._deliveries(list(reversed(rows)))
        with self.audit.lock:
            for delivery in deliveries:
                if delivery.event is not None: self.audit.observe(delivery)
            self.audit.counts.clear()
        self.inc('audit_history_replayed_count',len(deliveries))
        if len(rows)==self.config.audit_capacity: self.inc('audit_history_may_be_truncated')

    def close(self):
        self.stop_event.set()
        for worker in self.threads: worker.join(timeout=8)
        for transport in list(self.buses): self.disconnect(transport)

    def snapshot(self):
        with self.lock:
            values={key:self.counts[key] for key in ('enqueue_success','enqueue_rejected','peak_queue_depth',
                'xadd_success','xadd_failure','ack_success','reconnect_count','oversize_rejected',
                'pending_recovered','pending_peak','consumer_lag_peak','consumer_failure',
                'consumer_before_publish_reply_count','clock_domain_unavailable_count','missing_publisher_context',
                'publisher_context_evictions','last_rejected_size_bytes','observation_failure',
                'audit_history_replayed_count','audit_history_may_be_truncated')}
            return {'enabled':True,'connected':self.connected,'implementation':'redis-streams-shadow-audit',
                'stream':self.config.stream,'group':self.config.group,'consumer':self.config.consumer,'consumers':1,
                'queue_depth':self.queue.qsize(),'queue_max':self.config.capacity,'max_event_bytes':self.config.max_bytes,
                'pending':self.pending,'consumer_lag':self.lag,'stream_length':self.stream_length,
                'redis_memory_bytes':self.memory_bytes,'last_error_class':self.last_error_class,
                'transport_probe':self.transport_probe,
                'last_oversize_rejection':self.last_rejection,
                'legacy_authoritative':True,'redis_authoritative_processing':False,
                'consumer_db_writes':False,'consumer_ws_broadcast':False,**values,**self.audit.snapshot()}


_runtime=None
_configuration_error=None


def start(sampler):
    global _runtime,_configuration_error
    if not enabled(): return
    try:
        _runtime=RedisShadow(Config.environment(),sampler); _runtime.start()
    except Exception as error: _configuration_error=type(error).__name__


def stop():
    global _runtime
    if _runtime: _runtime.close(); _runtime=None


def observe(stage,*args):
    if not enabled() or _runtime is None: return
    try: getattr(_runtime,stage)(*args)
    except Exception: _runtime.inc('observation_failure')


def snapshot():
    if not enabled(): return None
    return _runtime.snapshot() if _runtime else {'enabled':True,'connected':False,
        'configuration_error_class':_configuration_error,'legacy_authoritative':True}
