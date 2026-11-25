"""Internal V1 contracts. Importing this package never connects to a transport."""
from .envelope import EventEnvelope
from .types import EventType

__all__ = ['EventEnvelope', 'EventType']
