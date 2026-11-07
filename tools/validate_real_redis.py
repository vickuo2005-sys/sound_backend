"""Disposable loopback Redis validation. Never imports main or domain DB helpers.

Requires an explicitly supplied Redis server executable. Output contains no DSN.
All handlers/effects are synthetic; Redis SET NX is a test idempotency ledger,
not a claim about production PostgreSQL transaction atomicity.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import redis
from services.events import EventEnvelope, EventType
from services.events.redis_streams import RedisStreamsEventBus
from services.events.result import ProcessingResult, ProcessingStatus


def stamp():
    return {'utc': datetime.now(timezone.utc).isoformat(), 'monotonic_ns': time.monotonic_ns()}


def event(index, partition='site_A', size=0, nodes=4):
    now = int(time.time() * 1000)
    return EventEnvelope(event_id=str(index), correlation_id=str(index), trace_id='trace-'+str(index),
        event_type=EventType.ACOUSTIC_EVENT_RECEIVED, event_time_ms=now, received_at_ms=now,
        device_id='synthetic_node_'+str(int(index) % nodes), partition_key=partition,
        payload={'label':'Drone', 'object_key':'synthetic/reference-only'},
        metadata={'published_monotonic_ns':time.monotonic_ns(), 'synthetic_padding':'x'*size})


def save(name, value):
    (ROOT/'outputs'/name).write_text(json.dumps(value, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')


def percentile(values, p):
    ordered=sorted(values)
    point=(len(ordered)-1)*p
    low=int(point); high=min(low+1,len(ordered)-1)
    return ordered[low]+(ordered[high]-ordered[low])*(point-low) if ordered else None


def overload_window(samples, seconds):
    """Latter-half ingress/completion rates; small noise guard, no CPU criterion."""
    window=[s for s in samples if s['elapsed_s']>=seconds/2]
    if len(window)<2: return {'overload':False,'insufficient_samples':True}
    first,last=window[0],window[-1]
    duration=last['elapsed_s']-first['elapsed_s']
    ingest=(last['published']-first['published'])/duration
    consume=(last['completed']-first['completed'])/duration
    growth=(last['backlog']-first['backlog'])/duration
    # Ignore a <=2-entry fluctuation; do not hide marginal sustained growth
    # merely because ingress is less than 10% higher than consumption.
    increasing=last['backlog']-first['backlog']>2 and growth>1
    return {'overload':ingest>consume and increasing,'ingest_eps':ingest,'consume_eps':consume,
        'backlog_growth_eps':growth,'window_seconds':duration,'noise_guard':'net >2 entries and >1 eps'}


class Server:
    def __init__(self, binary):
        self.binary=Path(binary).resolve()
        self.directory=tempfile.TemporaryDirectory(prefix='codex-redis-v2a-')
        self.base=Path(self.directory.name)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0)); self.port=sock.getsockname()[1]
        self.url=f'redis://127.0.0.1:{self.port}/0'
        self.process=None
        (self.base/'redis.conf').write_text(f'bind 127.0.0.1\nprotected-mode yes\nport {self.port}\n'
            'daemonize no\nsave ""\nappendonly yes\nappendfsync always\n'
            'dir .\nmaxmemory 128mb\nmaxmemory-policy noeviction\nlogfile server.log\n',encoding='utf-8')

    def start(self):
        self.process=subprocess.Popen([str(self.binary),'redis.conf'],cwd=self.base,
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        self.client=redis.Redis.from_url(self.url,decode_responses=True,socket_timeout=.3,socket_connect_timeout=.3)
        deadline=time.monotonic()+15
        while time.monotonic()<deadline:
            try:
                if self.client.ping(): return
            except (redis.ConnectionError, redis.TimeoutError): pass
            if self.process.poll() is not None:
                raise RuntimeError('Isolated Redis startup failed: '+(self.base/'server.log').read_text(errors='replace')[-1500:])
            time.sleep(.05)
        raise RuntimeError('Isolated Redis startup timeout')

    def stop(self, crash=False):
        if self.process and self.process.poll() is None:
            if crash: self.process.kill()
            else:
                try: self.client.shutdown(nosave=True)
                except (redis.ConnectionError, redis.TimeoutError):
                    self.process.kill()
            self.process.wait(timeout=15)
        if hasattr(self,'client'): self.client.close()

    def close(self):
        self.stop(); self.directory.cleanup()


def bus(server, stream=None, consumer='first', max_attempts=2):
    result=RedisStreamsEventBus.from_url(server.url,stream=stream or 'v2a-'+uuid.uuid4().hex,
        group='validation',consumer=consumer,block_ms=10,max_attempts=max_attempts)
    result.ensure_group()
    return result


def effect(client, stream, envelope):
    # SET NX is a test-only durable dedupe marker; no domain side effect is implied.
    return bool(client.set(stream+':effect:'+envelope.event_id,'synthetic_effect',nx=True))


def crash_child(port, stream, marker):
    class Config: url=f'redis://127.0.0.1:{port}/0'
    consumer=bus(Config(),stream,'crash-A')
    delivery=consumer.consume(1)[0]
    Path(marker).write_text(json.dumps({'first_delivery_time':stamp(),'message_id':delivery.message_id,
        'effect_applied':effect(consumer.client,stream,delivery.event)}),encoding='utf-8')
    # Explicitly remain alive after effect, before ACK, until parent kills process.
    while True: time.sleep(.1)


def crash_recovery(server):
    first=bus(server); published=stamp(); message=first.publish(event(1))
    marker=server.base/'consumer-marker.json'
    child=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--crash-child',str(server.port),first.stream,str(marker)],
        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    try:
        deadline=time.monotonic()+10
        while not marker.exists() and time.monotonic()<deadline:
            assert child.poll() is None, 'Consumer child failed before delivery'
            time.sleep(.01)
        assert marker.exists()
        received=json.loads(marker.read_text())
        child.kill(); child.wait(timeout=5); failure=stamp()
        before=first.pending(); assert before['pending']==1
        replacement=bus(server,first.stream,'crash-B')
        _,claimed=replacement.auto_claim(min_idle_ms=0); claim_time=stamp()
        assert len(claimed)==1 and claimed[0].message_id==message
        duplicate=not effect(replacement.client,first.stream,claimed[0].event)
        replacement.process(claimed[0],lambda e:None)
        assert duplicate and received['effect_applied'] and replacement.pending()['pending']==0
        assert replacement.client.xlen(first.stream)==1
        save('redis_crash_recovery.json',{'publish_time':published,**received,'consumer_failure_time':failure,
            'claim_time':claim_time,'recovery_complete_time':stamp(),'consumer_A_killed':True,
            'pending_before':before,'pending_after':replacement.pending(),'duplicate_observed':duplicate,
            'effect_count':1,'message_retained':True,'xdel_used':False,'ledger':'Redis SET NX, synthetic only'})
        replacement.close(); first.close()
    finally:
        if child.poll() is None: child.kill(); child.wait()


def ambiguous_ack(server):
    findings=[]
    for executed in (False,True):
        current=bus(server); current.publish(event(2)); delivery=current.consume(1)[0]
        assert effect(current.client,current.stream,delivery.event)
        original=current.client.xack
        def lost_ack(*args,**kwargs):
            if executed: original(*args,**kwargs)
            raise redis.ConnectionError('Injected ACK transport ambiguity')
        current.client.xack=lost_ack
        try:
            current.ack(delivery)
            raise AssertionError('Expected ambiguous ACK exception')
        except redis.ConnectionError: pass
        finally: current.client.xack=original
        pending=current.pending()['pending']
        if executed:
            assert pending==0
            current.publish(delivery.event) # semantic replay after lost successful ACK response
            replay=current.consume(1)
        else:
            assert pending==1
            _,replay=current.auto_claim(min_idle_ms=0)
        assert len(replay)==1
        duplicate=not effect(current.client,current.stream,replay[0].event)
        current.process(replay[0],lambda e:None)
        assert duplicate and current.pending()['pending']==0
        findings.append({'ack_executed_on_server':executed,'pending_after_uncertain_ack':pending,
            'replay_mode':'explicit semantic republish' if executed else 'pending claim',
            'duplicate_observed':True,'effect_count':1,'final_pending':0})
        current.close()
    save('redis_ambiguous_ack.json',{'cases':findings,'exactly_once_claim':False,
        'fault':'real Redis command with injected redis-py ConnectionError before/after ACK',
        'idempotency_scope':'synthetic Redis SET NX ledger; production DB idempotency still required'})


def restart(server):
    current=bus(server); current.publish(event(3)); delivery=current.consume(1)[0]
    server.stop(crash=True)
    start=time.monotonic(); error=None
    try: current.publish(event(4))
    except (redis.ConnectionError, redis.TimeoutError) as exc: error=type(exc).__name__
    assert error
    bounded_ms=(time.monotonic()-start)*1000
    server.start()
    assert current.client.ping()
    assert current.pending()['pending']==1
    _,claimed=current.auto_claim(min_idle_ms=0)
    assert claimed[0].message_id==delivery.message_id
    current.process(claimed[0],lambda e:None)
    current.publish(event(5)); current.process(current.consume(1)[0],lambda e:None)
    save('redis_restart_recovery.json',{'restart_mode':'forced server process kill + same AOF directory',
        'appendonly':True,'appendfsync':'always','connection_recovered':True,'pending_survived_restart':True,
        'original_message_recovered':True,'new_publish_consume_ack_passed':True,'final_pending':0,
        'outage_error_class':error,'bounded_failure_elapsed_ms':bounded_ms,
        'nonpersistent_durability_tested':False,'power_loss_durability_claim':False})
    current.close()


def retention(server):
    current=bus(server)
    ids=[current.publish(event(i)) for i in range(6)]
    deliveries=current.consume(6)
    for item in deliveries[:3]: current.ack(item)
    assert current.pending()['pending']==3 and current.client.xlen(current.stream)==6
    # All entries have been delivered; single group, trim strictly below oldest PEL.
    oldest=current.pending()['min']
    removed=current.client.xtrim(current.stream,minid=oldest,approximate=False)
    _,claimed=current.auto_claim(min_idle_ms=0)
    assert removed==3 and [d.message_id for d in claimed]==ids[3:]
    for item in claimed: current.ack(item)
    save('redis_retention_validation.json',{'length_after_ack':6,'pending_before_trim':3,
        'trim_policy':'isolated single-group exact MINID below oldest pending; all entries delivered',
        'acknowledged_removed':removed,'pending_recovered':3,'final_pending':0,
        'automatic_retention_enabled':False})
    current.close()


def ordering(server):
    current=bus(server)
    for i in range(3): current.publish(event(i))
    delivered=current.consume(3); order=[]
    for item in delivered: current.process(item,lambda e:order.append(e.event_id))
    assert order==['0','1','2']
    # Deterministic counterexample: group gives first event to A, second to B;
    # B completes before A. Redis group does not fence a logical partition.
    other=bus(server,current.stream,'second')
    current.publish(event(10)); current.publish(event(11))
    a=current.consume(1)[0]; b=other.consume(1)[0]; completion=[]
    other.process(b,lambda e:completion.append(e.event_id))
    current.process(a,lambda e:completion.append(e.event_id))
    assert completion==['11','10']
    isolated=bus(server); intervals={}; barrier=threading.Barrier(3)
    for i,key in enumerate(('site_A','site_B','site_C')): isolated.publish(event(i,partition=key))
    workers=[bus(server,isolated.stream,'parallel-'+str(i)) for i in range(3)]
    def run(worker):
        item=worker.consume(1)[0]
        def handle(e):
            barrier.wait(timeout=5); start=time.monotonic_ns(); time.sleep(.03)
            intervals[e.partition_key]=[start,time.monotonic_ns()]
        worker.process(item,handle); worker.close()
    with ThreadPoolExecutor(3) as pool: list(pool.map(run,workers))
    overlap=max(v[0] for v in intervals.values())<min(v[1] for v in intervals.values())
    assert overlap and isolated.pending()['pending']==0
    save('redis_ordering_validation.json',{'single_consumer_same_partition_order':order,
        'multi_consumer_same_partition_completion_counterexample':completion,
        'independent_partition_intervals_monotonic_ns':intervals,'independent_partitions_overlap':overlap,
        'strict_per_partition_multi_consumer_guarantee':False,'ORDERING_MODEL_VERIFIED':'PARTIAL',
        'blocker':'No partition ownership/fencing dispatcher exists in V1 adapter'})
    isolated.close(); other.close(); current.close()


def dlq(server):
    findings=[]
    for kind in ('malformed','permanent','retry_exhausted','transaction_retry'):
        current=bus(server)
        if kind=='malformed': current.client.xadd(current.stream,{'event':'invalid-json'})
        else: current.publish(event(99))
        delivery=current.consume(1)[0]
        failure=ProcessingResult(ProcessingStatus.RETRYABLE_FAILURE if kind=='retry_exhausted' else
            ProcessingStatus.PERMANENT_FAILURE,'SyntheticFailure')
        handler=lambda e:failure
        if kind=='retry_exhausted':
            current.process(delivery,handler); assert current.pending()['pending']==1
            delivery=current.claim([delivery.message_id],min_idle_ms=0)[0]
        original=current.client.pipeline; injections=[]
        if kind=='transaction_retry':
            def pipeline(*args,**kwargs):
                pipe=original(*args,**kwargs); execute=pipe.execute
                def flaky(*a,**kw):
                    if not injections:
                        injections.append('before EXEC'); raise redis.ConnectionError('Synthetic pre-EXEC failure')
                    return execute(*a,**kw)
                pipe.execute=flaky
                return pipe
            current.client.pipeline=pipeline
        current.process(delivery,handler)
        rows=current.client.xrange(current.stream+':dlq')
        assert len(rows)==1 and current.pending()['pending']==0
        record=rows[0][1]
        assert set(record)=={'source_id','event_id','trace_id','error_class'}
        if kind!='malformed': assert record['event_id']=='99' and record['trace_id']=='trace-99'
        findings.append({'case':kind,'dlq_record':record,'final_pending':0,
            'delivery_attempts':2 if kind=='retry_exhausted' else 1,'injected_transaction_errors':len(injections)})
        current.close()
    save('redis_dlq_validation.json',{'cases':findings,'atomic_scope':'Redis MULTI/EXEC DLQ append plus ACK',
        'malformed_identity':'Unknown; invalid JSON cannot safely supply validated identity',
        'ambiguous_EXEC_duplicate_DLQ_possible':True,'credential_or_audio_payload_stored':False})


def payloads(server):
    findings=[]
    for name,size in [('small',0),('normal',1024),('large',65536),('oversized_synthetic',1048576)]:
        current=bus(server); e=event(7,size=size)
        before=current.client.info('memory')['used_memory']
        for _ in range(10): current.publish(e)
        after=current.client.info('memory')['used_memory']
        findings.append({'case':name,'serialized_bytes':len(e.to_json().encode()),'metadata_padding_bytes':size,
            'samples':10,'memory_usage_stream_bytes':current.client.memory_usage(current.stream),
            'server_memory_delta_bytes':after-before})
        current.client.delete(current.stream); current.close()
    save('redis_payload_size.json',{'cases':findings,'recommendation_max_envelope_bytes':65536,
        'recommendation_only_not_enforced':True,'expected_metadata_budget_bytes':8192,
        'actual_application_max_metadata_size':'not established by synthetic tests',
        'audio':'references only; no raw WAV/base64'})


def load(server,nodes,rate,seconds=3,consumers=1,delay=.005):
    current=bus(server); started=time.monotonic(); stop=threading.Event()
    lock=threading.Lock(); counts={}; seen=set(); duplicates=0; lags=[]; sequences={}; inversions=0
    workers=[bus(server,current.stream,'load-'+str(i)) for i in range(consumers)]
    failures=[]
    def work(worker):
        nonlocal duplicates,inversions
        count=0
        try:
            while not stop.is_set():
                for delivery in worker.consume(1):
                    def handle(e):
                        nonlocal duplicates,inversions
                        time.sleep(delay)
                        with lock:
                            if e.event_id in seen: duplicates+=1
                            seen.add(e.event_id)
                            number=int(e.event_id)
                            last=sequences.get(e.partition_key,-1)
                            if number<last: inversions+=1
                            sequences[e.partition_key]=number
                            lags.append((time.monotonic_ns()-e.metadata['published_monotonic_ns'])/1e6)
                    worker.process(delivery,handle); count+=1
        except Exception as error: failures.append(type(error).__name__)
        finally: counts[worker.consumer]=count; worker.close()
    threads=[threading.Thread(target=work,args=(w,)) for w in workers]
    for thread in threads: thread.start()
    cpu_before=current.client.info('cpu'); mem_before=current.client.info('memory')['used_memory']
    samples=[]; published=0; next_sample=started
    try:
        while time.monotonic()-started<seconds:
            due=started+published/rate
            if time.monotonic()<due: time.sleep(min(due-time.monotonic(),.01)); continue
            current.publish(event(published,partition='site_'+str(published%3),nodes=nodes)); published+=1
            now=time.monotonic()
            if now>=next_sample:
                group=current.client.xinfo_groups(current.stream)[0]
                with lock: completed=len(lags)
                samples.append({'elapsed_s':now-started,'published':published,'completed':completed,
                    'pending':group['pending'],'lag':group['lag'],'backlog':group['pending']+group['lag'],
                    'used_memory_bytes':current.client.info('memory')['used_memory']})
                next_sample=now+.2
        producer_stop=time.monotonic()
        with lock: completed_at_stop=len(lags)
        g=current.client.xinfo_groups(current.stream)[0]
        backlog_at_stop=g['pending']+g['lag']
        deadline=producer_stop+30
        while time.monotonic()<deadline:
            g=current.client.xinfo_groups(current.stream)[0]
            if g['pending']==0 and g['lag']==0: break
            assert not failures, failures
            time.sleep(.01)
        drained=time.monotonic(); assert g['pending']==0 and g['lag']==0
    finally:
        stop.set()
        for thread in threads: thread.join(timeout=5); assert not thread.is_alive()
    assert not failures and sum(counts.values())==published and duplicates==0
    cpu_after=current.client.info('cpu'); duration=producer_stop-started
    cpu_seconds=sum(cpu_after[k]-cpu_before[k] for k in ('used_cpu_sys','used_cpu_user'))
    overload=overload_window(samples,seconds)
    slope=overload['backlog_growth_eps']
    ingest=published/duration; consume=completed_at_stop/duration
    overloaded=overload['overload']
    result={'nodes':nodes,'consumer_count':consumers,'handler_delay_ms':delay*1000,
        'offered_rate_eps':rate,'producer_rate_eps':ingest,'consumer_rate_during_production_eps':consume,
        'consumer_rate_with_drain_eps':published/(drained-started),'published':published,'processed':sum(counts.values()),
        'stream_length_retained_after_ack':current.client.xlen(current.stream),'pending_final':g['pending'],'lag_final':g['lag'],
        'backlog_at_producer_stop':backlog_at_stop,'backlog_peak':max([backlog_at_stop]+[s['backlog'] for s in samples]),
        'pending_peak':max([g['pending']]+[s['pending'] for s in samples]),'backlog_growth_eps_latter_half':slope,
        'processing_lag_ms':{f'p{p}':percentile(lags,p/100) for p in (50,95,99)},
        'drain_time_ms':(drained-producer_stop)*1000,'overload':overloaded,'overload_observation':overload,
        'producer_duration_s':duration,'duplicates':duplicates,'retry_count':0,
        'retry_rate':0,'duplicate_rate':0,'distribution':counts,'same_partition_completion_inversions':inversions,
        'redis_cpu_seconds':cpu_seconds,'redis_cpu_one_core_percent':cpu_seconds/(drained-started)*100,
        'redis_memory_before_bytes':mem_before,'redis_memory_after_bytes':current.client.info('memory')['used_memory'],
        'samples':samples,'scope':'synthetic transport + 5ms simulated handler; not Fusion/Tracking capacity'}
    current.client.delete(current.stream); current.close()
    return result


def regression(server, label):
    env=os.environ.copy(); env['EVENT_DRIVEN_TEST_REDIS_URL']=server.url
    env.pop('DATABASE_URL',None); env.pop('CRITICAL_PATH_TEST_PG_DSN',None)
    xml=server.base/(label+'.xml')
    completed=subprocess.run([sys.executable,'-m','pytest','-q','--junitxml='+str(xml)],cwd=ROOT,env=env,
        capture_output=True,text=True)
    print(completed.stdout,flush=True)
    assert completed.returncode==0, 'Python regression failed'
    suite=ET.parse(xml).getroot().find('testsuite')
    stats={k:int(suite.attrib[k]) for k in ('tests','failures','errors','skipped')}
    stats['passed']=stats['tests']-stats['failures']-stats['errors']-stats['skipped']
    checks=[]
    for file in sorted((ROOT/'tests/js').glob('test_*.js')):
        run=subprocess.run(['node',str(file)],cwd=ROOT,capture_output=True)
        checks.append({'file':file.name,'exit_code':run.returncode}); assert run.returncode==0,file.name
    html=(ROOT/'templates/dashboard_v2_4.html').read_text(encoding='utf-8')
    inline=[]
    for i,source in enumerate(re.findall(r'<script\b[^>]*>(.*?)</script>',html,re.S)):
        if not source.strip(): continue
        file=server.base/f'inline-{i}.js'; file.write_text(source,encoding='utf-8')
        run=subprocess.run(['node','--check',str(file)],capture_output=True)
        inline.append(run.returncode); assert run.returncode==0,run.stderr.decode(errors='replace')
    for command in ([sys.executable,'-m','compileall','-q','main.py','services/events','tools/validate_real_redis.py'],['git','diff','--check']):
        assert subprocess.run(command,cwd=ROOT,capture_output=True).returncode==0
    save(label+'.json',{'python':stats,'js':checks,'inline_js_exit_codes':inline,'compileall':True,'diff_check':True,
        'real_redis_url_logged':False})


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--server-binary'); parser.add_argument('--crash-child',nargs=3)
    args=parser.parse_args()
    if args.crash_child: crash_child(*args.crash_child); return
    assert args.server_binary, 'Explicit isolated server binary required'
    server=Server(args.server_binary)
    try:
        server.start()
        info=server.client.info()
        save('redis_environment.json',{'redis_version':info['redis_version'],'client_version':redis.__version__,
            'host_mode':'local Windows Cygwin community Redis port (not official Linux binary)',
            'binary_release':'https://github.com/redis-windows/redis-windows/releases/tag/7.2.10',
            'archive_sha256':'15f13366dab1f302a78acf82770bcc4d6379310ae32bee597f6c667dc9ea4020',
            'bind':'127.0.0.1','tls':False,'authentication':'loopback isolated test only',
            'persistence':'AOF appendfsync always','memory_limit_bytes':info['maxmemory'],
            'eviction_policy':info['maxmemory_policy'],'ping':server.client.ping(),'started':stamp(),
            'required_commands_supported':{c:bool(server.client.execute_command('COMMAND','INFO',c))
                for c in ['XADD','XREADGROUP','XGROUP','XACK','XPENDING','XAUTOCLAIM','XCLAIM']}})
        print('Real Redis environment started',flush=True)
        regression(server,'redis_initial_regression')
        for name,operation in [('crash',crash_recovery),('ambiguous ACK',ambiguous_ack),('restart',restart),
                ('retention',retention),('ordering',ordering),('DLQ',dlq),('payload',payloads)]:
            operation(server); print(name+' PASS',flush=True)
        for nodes in (4,20,50,100):
            trials=[load(server,nodes,rate) for rate in (50,150,400)]
            save(f'redis_load_{nodes}_nodes.json',{'trials':trials})
            print(f'{nodes} nodes loads PASS',flush=True)
        scaling=[load(server,20,600,consumers=count) for count in (1,2,4)]
        save('redis_consumer_scaling.json',{'trials':scaling,'strict_partition_ordering':'not guaranteed'})
        regression(server,'redis_final_regression')
    finally: server.close()
    print('Disposable Redis stopped and directory removed',flush=True)


if __name__=='__main__': main()
