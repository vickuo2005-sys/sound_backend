"""Optional transport primitives; never instantiated by the FastAPI/shadow path."""
from dataclasses import dataclass
from time import sleep
from .envelope import EventEnvelope
from .result import ProcessingResult, ProcessingStatus, classify_error


@dataclass(frozen=True)
class RedisDelivery:
    message_id: str
    event: EventEnvelope | None
    error_class: str | None = None


def text(value):
    return value.decode('utf-8') if isinstance(value, bytes) else value


class RedisStreamsEventBus:
    def __init__(self, client, *, stream='acoustic_events', group='event_driven_v1', consumer='local',
                 block_ms=100, max_reconnect_attempts=3, max_attempts=3):
        if not 1 <= block_ms <= 1000 or min(max_reconnect_attempts, max_attempts) < 1:
            raise ValueError('Bounded reads and attempts required')
        if not all(isinstance(value,str) and value for value in (stream,group,consumer)):
            raise ValueError('Stream/group/consumer names required')
        self.client, self.stream, self.group, self.consumer = client, stream, group, consumer
        self.block_ms, self.max_reconnect_attempts, self.max_attempts = block_ms, max_reconnect_attempts, max_attempts
        self._closed = False

    @classmethod
    def from_url(cls, url, **kwargs):
        # redis-py is intentionally absent from default requirements/import path.
        import redis
        return cls(redis.Redis.from_url(url, socket_connect_timeout=2, socket_timeout=2, decode_responses=True), **kwargs)

    def _call(self, operation, *args, **kwargs):
        if self._closed:
            raise RuntimeError('Transport closed')
        for attempt in range(self.max_reconnect_attempts):
            try:
                return operation(*args, **kwargs)
            except Exception as error:
                if type(error).__name__ not in ('ConnectionError', 'TimeoutError') or attempt+1 == self.max_reconnect_attempts:
                    raise
                sleep(min(.01 * 2**attempt, .1))

    def ensure_group(self):
        try:
            return self._call(self.client.xgroup_create, self.stream, self.group, id='0-0', mkstream=True)
        except Exception as error:
            if 'BUSYGROUP' not in str(error):
                raise
            return False

    def publish(self, event):
        if not isinstance(event, EventEnvelope):
            raise ValueError('Validated envelope required')
        # No XDEL, MAXLEN or trimming. Ambiguous network failure can duplicate XADD.
        return text(self._call(self.client.xadd, self.stream, {'event':event.to_json()}))

    def _deliveries(self, entries):
        result = []
        for message_id, data in entries:
            try:
                normalized = {text(key):text(value) for key,value in data.items()}
                event = EventEnvelope.from_json(normalized['event'])
                result.append(RedisDelivery(text(message_id), event))
            except (ValueError, TypeError, KeyError, UnicodeError) as error:
                result.append(RedisDelivery(text(message_id), None, type(error).__name__))
        return result

    def consume(self, count=100):
        if self._closed:
            return []
        if not 1 <= count <= 1000:
            raise ValueError('Bounded batch required')
        rows = self._call(self.client.xreadgroup, self.group, self.consumer,
                          {self.stream:'>'}, count=count, block=self.block_ms)
        return [delivery for _,entries in rows for delivery in self._deliveries(entries)]

    def ack(self, delivery):
        return self._call(self.client.xack, self.stream, self.group, delivery.message_id)

    def pending(self):
        return self._call(self.client.xpending, self.stream, self.group)

    def claim(self, ids, min_idle_ms=1000):
        if not ids or len(ids)>1000 or min_idle_ms<0:
            raise ValueError('Bounded recovery IDs/idle time required')
        entries = self._call(self.client.xclaim, self.stream, self.group, self.consumer, min_idle_ms, ids)
        return self._deliveries(entries)

    def auto_claim(self, min_idle_ms=1000, start_id='0-0', count=100):
        if min_idle_ms<0 or not 1 <= count <= 1000:
            raise ValueError('Bounded recovery required')
        rows = self._call(self.client.xautoclaim, self.stream, self.group, self.consumer,
                          min_idle_ms, start_id=start_id, count=count)
        return text(rows[0]), self._deliveries(rows[1])

    def process(self, delivery, handler):
        """ACK success; leave bounded retryable failures pending; DLQ + ACK terminal.

        Handler must supply durable domain idempotency. This transport cannot guarantee
        exactly-once DB/WS effects. No mutating production handler is wired here.
        """
        if delivery.event is None:
            result = ProcessingResult(ProcessingStatus.PERMANENT_FAILURE, delivery.error_class)
        else:
            try:
                result = handler(delivery.event)
                if result is None:
                    result = ProcessingResult()
                if not isinstance(result,ProcessingResult):
                    raise ValueError('Invalid handler result')
            except Exception as error:
                result = classify_error(error)
        if result.status == ProcessingStatus.SUCCESS:
            self.ack(delivery)
            return result
        pending = self._call(self.client.xpending_range, self.stream, self.group,
                             min=delivery.message_id, max=delivery.message_id, count=1)
        attempts = int(pending[0].get('times_delivered', 1)) if pending else 1
        if result.status == ProcessingStatus.RETRYABLE_FAILURE and attempts < self.max_attempts:
            return result # Redis PEL remains authoritative; recovery is explicit/bounded.
        # Atomic within Redis only. No distributed DB transaction implied.
        def terminal_transaction():
            # redis-py resets a Pipeline after execute errors; reconstruct commands on retry.
            with self.client.pipeline(transaction=True) as pipe:
                pipe.xadd(self.stream+':dlq', {'source_id':delivery.message_id,
                    'event_id':delivery.event.event_id if delivery.event else '',
                    'error_class':result.error_class or 'ProcessingFailure'})
                pipe.xack(self.stream, self.group, delivery.message_id)
                return pipe.execute()
        self._call(terminal_transaction)
        return result

    def close(self):
        self._closed = True
        self.client.close()
