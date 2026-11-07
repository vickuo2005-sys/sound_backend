"""Opt-in staging transport rehearsal, in a separate retained Redis namespace.

Synthetic Redis observations only. Never calls the Android API, DB or WebSocket.
Disconnect-before-ACK models an abandoned consumer; it is not an OS kill test.
"""
from dataclasses import replace
from time import time_ns
from uuid import uuid4

from .envelope import EventEnvelope
from .types import EventType
from .redis_shadow import RedisShadow


def run(config, sampler, factory=None):
    probe_config = replace(config, stream='staging:shadow-probe:'+uuid4().hex,
                           group='staging-shadow-probe', consumer='probe-recovery')
    current = RedisShadow(probe_config, sampler, factory=factory)
    old = recovered = None
    evidence = {'status': 'RUNNING', 'population': 'synthetic_transport_only',
                'stream': probe_config.stream, 'group': probe_config.group,
                'method': 'consumer connection closed after read, before ACK',
                'os_process_killed': False, 'domain_db_writes': False,
                'websocket_broadcasts': False, 'entries_retained': True}
    try:
        old = current.connect('probe-abandoned')
        evidence['ping'] = bool(old.client.ping())
        evidence['server_version'] = old.client.info('server').get('redis_version')
        now = time_ns()//1_000_000
        identifier = 'synthetic-transport-'+uuid4().hex
        initial = EventEnvelope(event_id=identifier, correlation_id=identifier,
            trace_id=identifier, device_id='synthetic_transport_probe',
            event_type=EventType.ACOUSTIC_EVENT_RECEIVED,
            event_time_ms=now, received_at_ms=now, metadata={'synthetic': True})
        old.publish(initial)
        received = old.consume(1)[0]
        old.process(received, lambda _: None)
        old.publish(initial.transition(EventType.EVENT_PERSISTED, {'id': 1}))
        pending = old.consume(1)[0]
        evidence['pending_before_disconnect'] = old.pending()['pending']
        assert evidence['pending_before_disconnect'] == 1
        current.disconnect(old); old = None
        recovered = current.connect('probe-recovery')
        current.restore_audit_history(recovered)
        _, claimed = recovered.auto_claim(min_idle_ms=0, count=1)
        assert len(claimed) == 1 and claimed[0].message_id == pending.message_id
        current.consume_delivery(recovered, claimed[0])
        evidence.update(pending_final=recovered.pending()['pending'],
            claimed_count=len(claimed), ack_count=current.snapshot()['ack_success'],
            ordering_violations=current.snapshot()['ordering_violation_count'],
            history_replayed=current.snapshot()['audit_history_replayed_count'])
        assert evidence['pending_final'] == 0
        assert evidence['ordering_violations'] == 0
        assert evidence['ack_count'] == evidence['history_replayed'] == 1
        evidence['status'] = 'PASS'
    except Exception as error:
        evidence.update(status='FAIL', error_class=type(error).__name__)
    finally:
        current.close()
    return evidence
