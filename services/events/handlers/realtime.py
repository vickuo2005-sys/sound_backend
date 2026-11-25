from .base import DomainHandler
from services.events.types import EventType


class RealtimeHandler(DomainHandler):
    input_type = EventType.TRACK_UPDATED
    output_type = EventType.TRACK_UPDATED

    async def execute_for_test(self, event):
        self._check(event)
        if self.domain_call is None:
            raise RuntimeError('Explicit existing realtime function required')
        # Inject a wrapper around main.broadcast_event_post_ingest_result in local tests only.
        await self.domain_call(event.payload)
        return self.observe(event, event.payload)
