import pytest
from fastapi.testclient import TestClient

from app.config import ROOT, Settings
from app.main import create_app
from app.auth import require_user
from app.auth_store import Principal
from fastapi import Request


@pytest.fixture
def source():
    return (ROOT / "models/sales.yaml").read_text(encoding="utf-8")


@pytest.fixture
def client():
    settings = Settings(_env_file=None, db_dsn="", db_password="")
    app = create_app(settings)
    def authenticated(request: Request):
        request.state.principal = Principal('test','tester',False,'test-csrf','test-token-hash')
    # Unit tests for modeling/storage inject a principal. Authentication has separate tests.
    app.dependency_overrides[require_user] = authenticated
    with TestClient(app, headers={'Origin': 'http://localhost:8025'}) as c:
        yield c
