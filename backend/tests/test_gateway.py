import pytest
from app.config import Settings
from app.frontend_gateway import render


def test_gateway_serves_dist_not_repository(tmp_path):
    dist=tmp_path/'frontend/dist'
    dist.mkdir(parents=True)
    (dist/'index.html').write_text('test')
    settings=Settings(_env_file=None,public_origin='http://192.0.2.10:8025',allow_insecure_http=True)
    config=render(settings,tmp_path).read_text()
    assert 'listen 0.0.0.0:8025' in config
    assert 'proxy_pass http://127.0.0.1:8026' in config
    assert 'X-Forwarded-For $remote_addr' in config
    assert 'frontend/dist' in config and 'location ~ (^|/)\\.' in config
    assert 'limit_req' in config and 'frame-ancestors' in config
    assert 'access_log off' in config
    assert 'FASTONTO_DB_PASSWORD' not in config


def test_tls_never_silently_falls_back(tmp_path):
    dist=tmp_path/'frontend/dist';dist.mkdir(parents=True);(dist/'index.html').write_text('test')
    settings=Settings(_env_file=None,public_origin='https://ontology.example:8025')
    with pytest.raises(ValueError): render(settings,tmp_path)
