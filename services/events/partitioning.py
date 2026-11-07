from .envelope import EventEnvelope


def derive_partition_key(event: EventEnvelope) -> str:
    # Same normalization as event_fusion.normalize_label; no new grouping algorithm.
    from services.event_fusion import normalize_label
    label = event.payload.get('label')
    if label is None:
        label = event.metadata.get('label')
    return normalize_label(label)
