from .base import DomainHandler
from services.events.types import EventType


class FusionHandler(DomainHandler):
    input_type = EventType.EVENT_PERSISTED
    output_type = EventType.EVENT_FUSED

    def call_domain(self, event):
        # Bind main.process_event_fusion_for_event; it owns its existing DB transaction.
        return self.domain_call(event.event_id)
