from .base import DomainHandler
from services.events.types import EventType


class PersistenceHandler(DomainHandler):
    input_type = EventType.ACOUSTIC_EVENT_RECEIVED
    output_type = EventType.EVENT_PERSISTED

    def call_domain(self, event):
        # Bind a local test adapter to main.process_event_initial_submission(SoundEvent(...)).
        return super().call_domain(event)['saved_event']
