from collections.abc import Mapping
from dataclasses import dataclass, field, fields, replace
import json
import math
from types import MappingProxyType
from urllib.parse import urlsplit

from .types import EventType

SECRET_KEYS = frozenset({'password', 'authorization', 'credentials', 'token', 'api_key',
                         'database_url', 'redis_stream_url', 'dsn', 'secret', 'private_key'})


def freeze(value):
    """Validate/copy JSON data and recursively freeze; no caller-owned mutable references."""
    if value is None or type(value) in (bool, int):
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError('Nonfinite JSON number')
        return value
    if isinstance(value, str):
        if '://' in value:
            parsed = urlsplit(value)
            if parsed.username is not None or parsed.password is not None:
                raise ValueError('Credential-bearing URL not allowed')
        return value
    if isinstance(value, Mapping):
        result = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError('JSON keys must be strings')
            normalized = key.lower().replace('-', '_')
            if normalized in SECRET_KEYS or normalized.endswith(('_password', '_token', '_secret', '_api_key')):
                raise ValueError('Credential field not allowed')
            result[key] = freeze(item)
        return MappingProxyType(result)
    if isinstance(value, (list, tuple)):
        return tuple(freeze(item) for item in value)
    raise ValueError('Only JSON data allowed; binary audio must remain a reference')


def thaw(value):
    if isinstance(value, Mapping):
        return {key: thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [thaw(item) for item in value]
    return value


@dataclass(frozen=True)
class EventEnvelope:
    event_id: str
    event_type: EventType
    correlation_id: str
    event_time_ms: int
    received_at_ms: int
    device_id: str | None = None
    trace_id: str | None = None
    site_id: str | None = None
    partition_key: str | None = None
    schema_version: int = 1
    payload: Mapping = field(default_factory=dict)
    metadata: Mapping = field(default_factory=dict)
    extensions: Mapping = field(default_factory=dict)

    def __post_init__(self):
        for key in ('event_id', 'correlation_id'):
            value = getattr(self, key)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f'{key} must be a nonempty string')
        for key in ('device_id', 'trace_id', 'site_id', 'partition_key'):
            value = getattr(self, key)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f'{key} must be null or a nonempty string')
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise ValueError('Unsupported schema version')
        for key in ('event_time_ms', 'received_at_ms'):
            if type(getattr(self, key)) is not int or getattr(self, key) < 0:
                raise ValueError(f'{key} must be nonnegative integer epoch milliseconds')
        object.__setattr__(self, 'event_type', EventType(self.event_type))
        for key in ('payload', 'metadata', 'extensions'):
            if not isinstance(getattr(self, key), Mapping):
                raise ValueError(f'{key} must be an object')
            object.__setattr__(self, key, freeze(getattr(self, key)))

    @property
    def idempotency_key(self):
        return (self.schema_version, self.event_type.value, self.event_id)

    def to_dict(self):
        return {f.name: thaw(getattr(self, f.name)) for f in fields(self)}

    def to_json(self):
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            raise ValueError('Envelope must be an object')
        names = {f.name for f in fields(cls)}
        kwargs = {key: value for key, value in data.items() if key in names}
        extension = dict(kwargs.get('extensions', {}))
        extension.update({key: value for key, value in data.items() if key not in names})
        kwargs['extensions'] = extension
        try:
            return cls(**kwargs)
        except TypeError as error:
            raise ValueError('Missing/invalid envelope fields') from error

    @classmethod
    def from_json(cls, text):
        return cls.from_dict(json.loads(text))

    def transition(self, event_type, payload):
        return replace(self, event_type=event_type, payload=payload)
