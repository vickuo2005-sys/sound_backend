from enum import StrEnum


class EventType(StrEnum):
    ACOUSTIC_EVENT_RECEIVED = 'acoustic_event_received'
    EVENT_PERSISTED = 'event_persisted'
    EVENT_FUSED = 'event_fused'
    POSITION_UPDATED = 'position_updated'
    TRACK_UPDATED = 'track_updated'
    EVENT_PROCESSING_FAILED = 'event_processing_failed'
