from dataclasses import dataclass
from enum import StrEnum


class ProcessingStatus(StrEnum):
    SUCCESS = 'success'
    RETRYABLE_FAILURE = 'retryable_failure'
    PERMANENT_FAILURE = 'permanent_failure'


@dataclass(frozen=True)
class ProcessingResult:
    status: ProcessingStatus = ProcessingStatus.SUCCESS
    error_class: str | None = None


def classify_error(error: Exception) -> ProcessingResult:
    # No blanket replay of Fusion/tracking logic exceptions: commit state may be ambiguous.
    name = type(error).__name__
    if isinstance(error, (TimeoutError, ConnectionError)):
        return ProcessingResult(ProcessingStatus.RETRYABLE_FAILURE, name)
    # psycopg is optional here; only well-defined transaction-abort SQLSTATEs can retry.
    if getattr(error, 'pgcode', None) in ('40001', '40P01'):
        return ProcessingResult(ProcessingStatus.RETRYABLE_FAILURE, name)
    return ProcessingResult(ProcessingStatus.PERMANENT_FAILURE, name)
