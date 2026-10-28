import pytest

from app import repository


def test_health_without_database(client):
    response = client.get('/api/health')
    assert response.status_code == 200
    assert response.json() == {'status': 'ok'}
    assert client.get('/api/system').json()['database_configured'] is False
    assert response.headers['cache-control'] == 'no-store'


def test_template_explicitly_unsaved(client):
    result = client.get('/api/models/template').json()
    assert result['saved'] is False
    assert result['origin'] == 'bundled-example'


@pytest.mark.parametrize('path', ['/api/database/status', '/api/models', '/api/sources/PRODUCTS/preview', '/api/graph/products'])
def test_no_fake_live_results(client, path):
    response = client.get(path)
    assert response.status_code == 503
    assert response.json()['code'] == 'database_unavailable'


def test_catalog_is_not_live_check(client):
    r = client.get('/api/sources').json()
    assert len(r['items']) == 8
    assert r['live_verified'] is False
    assert all(s['readonly'] for s in r['items'])


@pytest.mark.parametrize('url', ['/api/sources/SALES/preview?limit=101', '/api/sources/SALES/preview?offset=-1', '/api/sources/SALES/preview?offset=10001'])
def test_preview_bounds(client, url):
    assert client.get(url).status_code == 422


def test_table_allowlist(client):
    assert client.get('/api/sources/USER_USERS/preview').status_code == 404
    assert client.get('/api/sources/SALES%20UNION%20SELECT/preview').status_code == 404


def test_invalid_schema_is_actionable(client):
    r = client.post('/api/models/validate', json={'source': 'a: ['})
    assert r.status_code == 422
    assert 'YAML' in r.json()['detail']


def test_cross_origin_denied(client):
    assert client.get('/api/health', headers={'Origin': 'https://evil.invalid'}).status_code == 403
    assert client.get('/api/health', headers={'Origin': 'http://localhost:8025'}).status_code == 200
    assert client.get('/api/health', headers={'Host': 'evil.invalid'}).status_code == 400


def test_request_size_bound(client):
    assert client.post('/api/models/validate', content='x' * 131073).status_code == 413


def test_revision_conflict_never_overwrites(client, source, monkeypatch):
    def conflict(*args):
        raise repository.RevisionConflict()
    monkeypatch.setattr(repository, 'save_model', conflict)
    r = client.post('/api/models', json={'source': source, 'id': '00000000-0000-0000-0000-000000000001', 'expected_revision': 2})
    assert r.status_code == 409


def test_save_validates_before_repository(client, monkeypatch):
    def unexpected(*args):
        pytest.fail('invalid schema reached persistence')
    monkeypatch.setattr(repository, 'save_model', unexpected)
    assert client.post('/api/models', json={'source': 'invalid'}).status_code == 422
