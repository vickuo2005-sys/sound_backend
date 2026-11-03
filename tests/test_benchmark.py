import json
import os
import sqlite3
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from services import benchmark as b


@pytest.fixture(params=['sqlite', 'postgres'])
def client(tmp_path, monkeypatch, request):
    db = tmp_path / 'benchmark.db'
    sql = Path('migrations/v7_benchmark.sql').read_text()
    if request.param == 'postgres':
        url = os.getenv('BENCHMARK_TEST_POSTGRES_URL')
        if not url:
            pytest.skip('dedicated local PostgreSQL test URL not supplied')
        import psycopg2
        with psycopg2.connect(url) as conn:
            with conn.cursor() as cursor:
                cursor.execute('DROP TABLE IF EXISTS benchmark_runs; DROP TABLE IF EXISTS benchmark_sessions;')
                cursor.execute(sql)
        monkeypatch.setenv('BENCHMARK_DATABASE_URL', url)
    else:
        with sqlite3.connect(db) as conn:
            conn.executescript(sql)
        monkeypatch.setenv('BENCHMARK_DATABASE_URL', 'sqlite:///'+str(db))
    monkeypatch.setenv('BENCHMARK_ENABLED', 'true')
    monkeypatch.setenv('BENCHMARK_ADMIN_TOKEN', 'a'*64)
    b._limits.clear()
    app = FastAPI()
    app.include_router(b.router)
    app.add_middleware(b.BenchmarkBodyLimit)
    return TestClient(app)


def session():
    return dict(session_id=str(uuid4()), brand='=formula', model='test fixture',
                android_version='14', abi='arm64', cores=8, memory_mb=4096,
                app_version='test', model_id='preclassifier', model_version='1',
                model_sha256='0'*64, model_metadata_sha256='0'*64,
                pipeline_version='native-wav-ai.v1', inference_settings='tflite_flutter-0.12.1-default-options',
                input_shape=[1,1,128,256], output_shape=[1,2], started_at='2026-11-04T00:00:00Z')


def run(n=60, **overrides):
    r = dict(run_id=str(uuid4()), hop_ms=100, window_ms=3000, phase='confirmation',
             duration_ms=120000, generated=n, processed=n, dropped=0, max_backlog=2,
             thermal_max=0, cpu_ms=5000, errors=[], samples=[dict(sequence=i,
             ready_native_ms=1000+i*100, native_queue_ms=1, native_save_ms=2,
             bridge_upper_ms=3, flutter_queue_ms=0, preprocess_ms=5,
             inference_ms=10, pipeline_upper_ms=30, success=True) for i in range(n)])
    r.update(overrides)
    return r


HEADERS = {'Authorization': 'Bearer '+'b'*64}


def test_storage_retry_ownership_and_export(client):
    s = session()
    for _ in range(2):
        assert client.post('/benchmark/sessions', json=s, headers=HEADERS).json()['stored']
    assert client.post('/benchmark/sessions', json=s, headers={'Authorization':'Bearer '+'c'*64}).status_code == 403
    batch = dict(session_id=s['session_id'], completed_at='2026-11-04T00:10:00Z',
                 status='completed', reason='completed', criteria_version='benchmark.v1', runs=[run()])
    for _ in range(2):
        response = client.post('/benchmark/results/batch', json=batch, headers=HEADERS)
        assert response.status_code == 200, response.text
        assert response.json()['lowest_stable_hop'] == 100
    batch['reason'] = 'changed'
    assert client.post('/benchmark/results/batch', json=batch, headers=HEADERS).status_code == 409
    assert client.get('/benchmark/admin/export.csv', headers=HEADERS).status_code == 403
    export = client.get('/benchmark/admin/export.csv', headers={'Authorization': 'Bearer '+'a'*64})
    assert export.status_code == 200
    assert "'=formula" in export.text
    assert len(export.text.splitlines()) == 2
    with b.database() as execute:
        assert execute('SELECT COUNT(*) FROM benchmark_runs').fetchone()[0] == 1


@pytest.mark.parametrize('change,reason', [
    ({'samples':[], 'processed':0, 'dropped':60}, 'insufficient_samples'),
    ({'duration_ms':119999}, 'confirmation_too_short'),
    ({'thermal_max':3}, 'thermal'), ({'max_backlog':3}, 'backlog'),
    ({'errors':['microphone_silenced']}, 'interrupted_or_error'),
])
def test_failure_criteria(change, reason):
    assert reason in b.evaluate(b.Run.model_validate(run(**change)))['reasons']


def test_percentiles_and_strict_budget():
    assert b.summary([]) is None
    assert b.summary(range(1,101)) == dict(p50=50,p95=95,p99=99,average=50.5,maximum=100)
    r = run()
    for s in r['samples']: s['pipeline_upper_ms'] = 100
    assert 'pipeline_budget' in b.evaluate(b.Run.model_validate(r))['reasons']
    for s in r['samples']: s['pipeline_upper_ms'] = 80
    assert b.evaluate(b.Run.model_validate(r))['passed']
    assert not b.evaluate(b.Run.model_validate(r))['recommended']


def test_validation_privacy_and_limits(client, monkeypatch):
    s = session()
    assert client.post('/benchmark/sessions', json=s).status_code == 401
    assert client.post('/benchmark/sessions', json={**s,'gps':123}, headers=HEADERS).status_code == 422
    assert client.post('/benchmark/sessions', content=b'x'*(4*1024*1024+1)).status_code == 413
    assert client.post('/benchmark/sessions', json={**s, 'cores':-1}, headers=HEADERS).status_code == 422
    monkeypatch.setenv('BENCHMARK_ENABLED', 'false')
    assert client.post('/benchmark/sessions', json=s, headers=HEADERS).status_code == 503


def test_rate_limit(client):
    for _ in range(60):
        assert client.post('/benchmark/sessions', json=session(), headers=HEADERS).status_code == 200
    assert client.post('/benchmark/sessions', json=session(), headers=HEADERS).status_code == 429


def test_invalid_counts_and_nan():
    for change in [{'processed':3}, {'generated':99}, {'hop_ms':42}]:
        with pytest.raises(ValueError): b.Run.model_validate(run(**change))
    r=run(); r['samples'][0]['inference_ms']=float('nan')
    with pytest.raises(ValueError): b.Run.model_validate(r)


def test_unconfirmed_hop_never_stable():
    batch = b.Batch.model_validate(dict(session_id=str(uuid4()), completed_at='2026-11-04T00:10:00Z',
        status='completed', reason='test', criteria_version='benchmark.v1', runs=[run(phase='survey')]))
    assert b.decisions(batch)['lowest_stable_hop'] is None


def test_pipeline_versions_remain_distinguishable():
    old = b.Session.model_validate(session())
    new = b.Session.model_validate({**session(), 'pipeline_version':'native-wav-ai.v2',
                                  'protocol_version':'benchmark.protocol.v1.1'})
    assert old.pipeline_version != new.pipeline_version
    assert old.protocol_version == 'benchmark.protocol.v1'
    assert new.protocol_version == 'benchmark.protocol.v1.1'
