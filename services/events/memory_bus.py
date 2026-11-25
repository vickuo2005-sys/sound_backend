from collections import OrderedDict, deque
from dataclasses import dataclass
from threading import Lock, RLock
from time import monotonic

from .bus import QueueFull
from .envelope import EventEnvelope
from .result import ProcessingResult, ProcessingStatus, classify_error


@dataclass
class Delivery:
    event: EventEnvelope
    queued_at: float
    attempts: int = 0


class InMemoryEventBus:
    """Bounded single-dispatcher FIFO; successful drain ACKs, failures retry in place.

    Volatile, not durable. Dedupe terminal history is bounded; active keys are never evicted.
    Terminal failures remain observable in a bounded dead-letter inspection buffer.
    """
    def __init__(self, capacity=256, max_attempts=3, dedupe_capacity=1024, recorder=None):
        if min(capacity, max_attempts, dedupe_capacity) < 1:
            raise ValueError('Positive bounds required')
        self.capacity, self.max_attempts, self.dedupe_capacity = capacity, max_attempts, dedupe_capacity
        self.recorder = recorder or (lambda *_: None)
        self._queue = deque()
        self._active = set()
        self._terminal = OrderedDict()
        self._dead = deque(maxlen=capacity)
        self._lock = RLock()
        self._dispatcher = Lock()
        self._handlers = {}
        self._stats = dict(published=0, consumed=0, retries=0, failures=0, duplicates=0,
                           rejections=0, failed_attempts=0, peak_queue_depth=0)

    def subscribe(self, event_type, handler):
        with self._lock:
            self._handlers[event_type] = handler

    def publish(self, event):
        if not isinstance(event, EventEnvelope):
            raise ValueError('Validated envelope required')
        start = monotonic()
        with self._lock:
            key = event.idempotency_key
            if key in self._active or key in self._terminal:
                self._stats['duplicates'] += 1
                return False
            if len(self._active) >= self.capacity:
                self._stats['rejections'] += 1
                raise QueueFull('In-memory event queue at capacity')
            self._active.add(key)
            self._queue.append(Delivery(event, monotonic()))
            self._stats['published'] += 1
            self._stats['peak_queue_depth'] = max(self._stats['peak_queue_depth'], len(self._active))
        self.recorder('event_bus_publish', (monotonic()-start)*1000)
        return True

    def drain(self, limit=None):
        processed = 0
        with self._dispatcher:
            while limit is None or processed < limit:
                with self._lock:
                    if not self._queue:
                        break
                    delivery = self._queue.popleft()
                self.recorder('event_bus_queue_wait', (monotonic()-delivery.queued_at)*1000)
                # In-place retry preserves global FIFO and same-label order; no worker added.
                while True:
                    delivery.attempts += 1
                    start = monotonic()
                    try:
                        handler = self._handlers.get(delivery.event.event_type)
                        if handler is None:
                            raise ValueError('No subscriber')
                        result = handler(delivery.event)
                        if result is None:
                            result = ProcessingResult()
                        if not isinstance(result, ProcessingResult):
                            raise ValueError('Invalid processing result')
                    except Exception as error:
                        result = classify_error(error)
                    finally:
                        self.recorder('event_bus_handler_duration', (monotonic()-start)*1000)
                    with self._lock:
                        if result.status == ProcessingStatus.SUCCESS:
                            self._stats['consumed'] += 1
                            break
                        self._stats['failed_attempts'] += 1
                        if result.status == ProcessingStatus.RETRYABLE_FAILURE and delivery.attempts < self.max_attempts:
                            self._stats['retries'] += 1
                            continue
                        self._stats['failures'] += 1
                        self._dead.append({'event_id': delivery.event.event_id, 'event_type': delivery.event.event_type.value,
                                           'attempts': delivery.attempts, 'error_class': result.error_class})
                        break
                with self._lock:
                    key = delivery.event.idempotency_key
                    self._active.remove(key)
                    self._terminal[key] = result.status
                    while len(self._terminal) > self.dedupe_capacity:
                        self._terminal.popitem(last=False)
                self.recorder('event_bus_end_to_end', (monotonic()-delivery.queued_at)*1000)
                processed += 1
        return processed

    def snapshot(self):
        with self._lock:
            return {**self._stats, 'implementation': 'memory', 'queue_depth': len(self._queue),
                    'inflight': len(self._active)-len(self._queue), 'terminal_history_size':len(self._terminal),
                    'dead_letters':list(self._dead)}
