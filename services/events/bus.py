from typing import Protocol
from .envelope import EventEnvelope


class QueueFull(RuntimeError):
    """Publisher must explicitly account for/retry this rejection."""


class EventPublisher(Protocol):
    def publish(self, event: EventEnvelope) -> bool | str: ...
