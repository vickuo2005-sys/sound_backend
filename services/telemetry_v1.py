from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from threading import Lock
from time import monotonic
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator

MAX_TIMESTAMP_MS = 253_402_300_799_999
TimestampMs = Annotated[int, Field(strict=True, ge=0, le=MAX_TIMESTAMP_MS)]
Identifier = Annotated[str, Field(strict=True, min_length=1, max_length=160)]


class TelemetryV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[1]
    device_id: Identifier
    sequence: Annotated[int, Field(strict=True, ge=1, le=2**53 - 1)]
    gps_time_ms: TimestampMs | None
    latitude: Annotated[float, Field(strict=True, ge=-90, le=90)] | None
    longitude: Annotated[float, Field(strict=True, ge=-180, le=180)] | None
    detected: StrictBool
    event_id: Identifier | None
    event_time_ms: TimestampMs | None
    label: Annotated[str, Field(strict=True, min_length=1, max_length=80)] | None
    confidence: Annotated[float, Field(strict=True, ge=0, le=1)] | None
    battery: Annotated[int, Field(strict=True, ge=0, le=100)] | None

    @field_validator("version", mode="before")
    @classmethod
    def validate_version(cls, version):
        if type(version) is not int or version != 1:
            raise ValueError("version must be the integer 1")
        return version

    @model_validator(mode="after")
    def validate_groups(self):
        if not self.device_id.strip():
            raise ValueError("device_id must not be blank")
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude and longitude must be supplied together")
        if self.latitude is None and self.gps_time_ms is not None:
            raise ValueError("GPS timestamp requires coordinates")
        if self.detected:
            if not self.event_id or not self.event_id.strip() or self.event_time_ms is None or not self.label or not self.label.strip():
                raise ValueError("detected packets require event_id, event_time_ms and label")
        elif any(value is not None for value in (self.event_id, self.event_time_ms, self.label, self.confidence)):
            raise ValueError("periodic packets require null event fields")
        return self


def telemetry_timestamp(ms: int) -> str:
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    return (epoch + timedelta(milliseconds=ms)).isoformat(timespec="milliseconds")


class LatestTelemetry:
    """Recent status is bounded and expendable. Event IDs are deduplicated in the event database."""

    def __init__(self, *, ttl_seconds: float = 30, limit: int = 1024):
        self.ttl_seconds = ttl_seconds
        self.limit = limit
        self._rows = OrderedDict()
        self._lock = Lock()

    def record(self, packet: TelemetryV1) -> None:
        with self._lock:
            now = monotonic()
            self._prune(now)
            current = self._rows.get(packet.device_id)
            if current is None or packet.sequence > current[2].sequence:
                self._rows[packet.device_id] = (
                    now, datetime.now(timezone.utc).isoformat(), packet,
                )
                self._rows.move_to_end(packet.device_id)
            while len(self._rows) > self.limit:
                self._rows.popitem(last=False)

    def _prune(self, now: float) -> None:
        while self._rows and now - next(iter(self._rows.values()))[0] > self.ttl_seconds:
            self._rows.popitem(last=False)

    def snapshot(self) -> dict[str, tuple[str, TelemetryV1]]:
        with self._lock:
            self._prune(monotonic())
            return {key: (value[1], value[2]) for key, value in self._rows.items()}
