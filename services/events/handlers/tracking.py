from .base import DomainHandler
from services.events.types import EventType


class TrackingHandler(DomainHandler):
    input_type = EventType.POSITION_UPDATED
    output_type = EventType.TRACK_UPDATED
    # Inject main.process_tracking_for_event_group_region; no math is copied here.
