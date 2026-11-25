import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from google.api_core.exceptions import NotFound, PreconditionFailed

import main
from services.audio_evidence import MAX_EVIDENCE_BYTES, read_audio_evidence


class Blob:
    size = 4
    generation = '17'

    def __init__(self):
        self.calls = []
        self.data = b'RIFF'

    def reload(self, **kwargs):
        self.calls.append(('reload', kwargs))

    def download_as_bytes(self, **kwargs):
        self.calls.append(('download', kwargs))
        return self.data


class Bucket:
    def __init__(self, blob):
        self.object = blob
        self.path = None

    def blob(self, path):
        self.path = path
        return self.object


def test_audio_read_is_bounded_and_pinned_to_object_generation():
    blob = Blob()
    bucket = Bucket(blob)
    assert read_audio_evidence(bucket, 'events/old.mp3') == b'RIFF'
    assert bucket.path == 'events/old.mp3'
    options = blob.calls[-1][1]
    assert options == dict(start=0, end=MAX_EVIDENCE_BYTES, raw_download=True, if_generation_match=17, timeout=20, retry=None)


@pytest.mark.parametrize('size,code', [(MAX_EVIDENCE_BYTES+1,413), (0,422), (None,503)])
def test_invalid_object_size_never_downloads(size, code):
    blob = Blob()
    blob.size = size
    with pytest.raises(HTTPException) as error:
        read_audio_evidence(Bucket(blob), 'event.wav')
    assert error.value.status_code == code
    assert [call[0] for call in blob.calls] == ['reload']


def test_audio_incomplete_is_not_served_as_a_valid_recording():
    blob = Blob()
    blob.data = b'RI'
    with pytest.raises(HTTPException, match='audio_incomplete') as error:
        read_audio_evidence(Bucket(blob), 'event.wav')
    assert error.value.status_code == 502


@pytest.mark.parametrize('failure,code,detail', [
    (NotFound('private object name'),404,'audio_object_missing'),
    (PreconditionFailed('changed'),409,'audio_changed_retry'),
    (RuntimeError('private credential diagnostic'),503,'audio_storage_unavailable')])
def test_storage_failures_have_distinct_public_reasons(failure, code, detail):
    class FailingBlob(Blob):
        def reload(self, **kwargs):
            raise failure
    with pytest.raises(HTTPException) as error:
        read_audio_evidence(Bucket(FailingBlob()), 'event.wav')
    assert error.value.status_code == code
    assert error.value.detail == detail


def test_audio_content_route_reads_only_persisted_path(monkeypatch):
    monkeypatch.setattr(main, 'get_event_by_event_id', lambda event_id: {'audio_path':'recorded.wav','audio_format':'wav'})
    bucket = Bucket(Blob())
    monkeypatch.setattr(main, 'get_gcs_bucket', lambda: bucket)
    response = TestClient(main.app).get('/events/example/audio-content?url=https://untrusted.invalid')
    assert response.status_code == 200
    assert response.content == b'RIFF'
    assert bucket.path == 'recorded.wav'
    assert response.headers['cache-control'] == 'no-store'
    assert response.headers['x-content-type-options'] == 'nosniff'
    assert response.headers['content-type'].startswith('audio/wav')


@pytest.mark.parametrize('event,detail', [(None,'event_not_found'), ({},'event_not_found'),
                                       ({'event_id':'example'},'audio_not_uploaded')])
def test_missing_event_or_recording_does_not_access_storage(monkeypatch, event, detail):
    monkeypatch.setattr(main, 'get_event_by_event_id', lambda event_id: event)
    monkeypatch.setattr(main, 'get_gcs_bucket', lambda: pytest.fail('unexpected storage access'))
    response = TestClient(main.app).get('/events/example/audio-content')
    assert response.status_code == 404
    assert response.json()['detail'] == detail


def test_unconfigured_storage_is_not_exposed_to_client(monkeypatch):
    monkeypatch.setattr(main, 'get_event_by_event_id', lambda event_id: {'audio_path':'recorded.wav'})
    def unavailable():
        raise HTTPException(500, detail='private configuration error')
    monkeypatch.setattr(main, 'get_gcs_bucket', unavailable)
    response = TestClient(main.app).get('/events/example/audio-content')
    assert response.status_code == 503
    assert response.json()['detail'] == 'audio_storage_unavailable'
