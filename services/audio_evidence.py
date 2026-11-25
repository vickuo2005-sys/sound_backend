"""Bounded, generation-consistent reads of an event's recorded GCS object."""
from fastapi import HTTPException
from google.api_core.exceptions import NotFound, PreconditionFailed

MAX_EVIDENCE_BYTES = 8 * 1024 * 1024


def read_audio_evidence(bucket, audio_path: str) -> bytes:
    try:
        blob = bucket.blob(audio_path)
        blob.reload(timeout=10, retry=None)
        size = blob.size
        if size is None or not blob.generation:
            raise HTTPException(503, detail="audio_metadata_unavailable")
        if size > MAX_EVIDENCE_BYTES:
            raise HTTPException(413, detail="audio_too_large")
        if size <= 0:
            raise HTTPException(422, detail="audio_empty")
        content = blob.download_as_bytes(
            start=0, end=MAX_EVIDENCE_BYTES, raw_download=True,
            if_generation_match=int(blob.generation), timeout=20, retry=None,
        )
        if len(content) > MAX_EVIDENCE_BYTES:
            raise HTTPException(413, detail="audio_too_large")
        if len(content) != size:
            raise HTTPException(502, detail="audio_incomplete")
        return content
    except HTTPException:
        raise
    except NotFound as exc:
        raise HTTPException(404, detail="audio_object_missing") from exc
    except PreconditionFailed as exc:
        raise HTTPException(409, detail="audio_changed_retry") from exc
    except Exception as exc:
        raise HTTPException(503, detail="audio_storage_unavailable") from exc
