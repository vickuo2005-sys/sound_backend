import pytest
from tools.collect_redis_shadow import SERVICE_ID, validate


def test_collector_accepts_only_exact_staging_version_without_urls():
    snapshot={'build':{'render_git_commit':'expected','render_service_id':SERVICE_ID},
              'redis_shadow':{'connected':True,'stream':'staging:acoustic-events:v1'}}
    assert validate(snapshot,'expected') is snapshot
    with pytest.raises(ValueError): validate(snapshot,'other')
    snapshot['build']['render_service_id']='production'
    with pytest.raises(ValueError): validate(snapshot,'expected')


@pytest.mark.parametrize('url',['rediss://example','redis://example','postgresql://example','postgres://example'])
def test_collector_refuses_credential_url_storage(url):
    with pytest.raises(ValueError):
        validate({'build':{'render_git_commit':'expected','render_service_id':SERVICE_ID},'secret':url},'expected')
