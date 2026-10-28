from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.auth import HASHER, LoginLimiter, token_digest
from app.auth_store import AuthConflict, Principal, User
from app.config import Settings
from app.main import create_app

PASSWORD = 'Only-A-Synthetic-Password!2026'
NEW_PASSWORD = 'Different-Synthetic-Passphrase!2026'


class MemoryAuthStore:
    def __init__(self, password_hash):
        self.user=User('test-user','admin',password_hash,True,True,1)
        self.sessions={}
        self.failures=0
    def get_user(self, username): return self.user if self.user.username==username else None
    def record_failure(self,user):
        self.failures+=1
        if self.failures>=5: self.user=replace(self.user,locked=True)
    def create_session(self,user,digest,csrf,hours,replacement_hash=None):
        if user.version != self.user.version or user.password_hash!=self.user.password_hash or not self.user.enabled or self.user.locked: raise AuthConflict()
        if replacement_hash: self.user=replace(self.user,password_hash=replacement_hash)
        self.failures=0
        now=datetime.now(timezone.utc)
        self.sessions[digest]={'csrf':csrf,'version':user.version,'expires':now+timedelta(hours=hours),'last':now}
    def lookup_session(self,digest,idle_minutes):
        session=self.sessions.get(digest)
        now=datetime.now(timezone.utc)
        if not session or not self.user.enabled or session['version']!=self.user.version or session['expires']<=now or session['last']<=now-timedelta(minutes=idle_minutes): return None
        session['last']=now
        return Principal(self.user.id,self.user.username,self.user.must_change_password,session['csrf'],digest)
    def change_password(self,user,new_hash,digest,csrf,hours):
        if user.version!=self.user.version or user.password_hash!=self.user.password_hash: raise AuthConflict()
        self.user=replace(user,password_hash=new_hash,must_change_password=False,version=user.version+1)
        self.sessions.clear()
        self.create_session(self.user,digest,csrf,hours)
    def logout(self,digest): self.sessions.pop(digest,None)


@pytest.fixture(scope='module')
def password_hash(): return HASHER.hash(PASSWORD)


@pytest.fixture
def auth_app(password_hash):
    settings=Settings(_env_file=None,db_dsn='',db_password='')
    store=MemoryAuthStore(password_hash)
    return create_app(settings,auth_store=store),store


@pytest.fixture
def auth_client(auth_app):
    with TestClient(auth_app[0],headers={'Origin':'http://localhost:8025'}) as client:
        yield client


def login(client,password=PASSWORD):
    return client.post('/api/auth/login',json={'username':'admin','password':password})


@pytest.mark.parametrize('path', ['/api/auth/me','/api/models/template','/api/models','/api/sources','/api/system','/api/graph/products'])
def test_all_business_reads_require_login(auth_client,path):
    assert auth_client.get(path).status_code==401


def test_unauthenticated_write_and_private_docs(auth_client):
    assert auth_client.post('/api/models/validate',json={'source':'invalid'}).status_code==401
    assert auth_client.post('/api/models/import',json={'filename':'x.md','content_base64':'IyBY'}).status_code==401
    assert auth_client.post('/api/models/draft',json={}).status_code==401
    assert auth_client.get('/docs').status_code==404
    assert auth_client.get('/openapi.json').status_code==404
    assert auth_client.get('/api/health').json()=={'status':'ok'}


def test_login_cookie_and_first_password_barrier(auth_client,auth_app):
    response=login(auth_client)
    assert response.status_code==200
    assert response.json()['user']['must_change_password'] is True
    cookie=response.headers['set-cookie'].lower()
    assert 'httponly' in cookie and 'samesite=strict' in cookie
    assert 'domain=' not in cookie
    token=auth_client.cookies.get('fastonto_session')
    assert token_digest(token) in auth_app[1].sessions and token not in auth_app[1].sessions
    assert auth_client.get('/api/auth/me').status_code==200
    blocked=auth_client.get('/api/models/template')
    assert blocked.status_code==403 and blocked.json()['detail']['code']=='password_change_required'


def test_password_rotation_revokes_other_sessions(auth_client,auth_app):
    first=login(auth_client).json()
    original=auth_client.cookies.get('fastonto_session')
    with TestClient(auth_app[0],headers={'Origin':'http://localhost:8025'}) as other:
        assert login(other).status_code==200
        changed=auth_client.post('/api/auth/password',headers={'X-CSRF-Token':first['csrf_token']},
                                json={'current_password':PASSWORD,'new_password':NEW_PASSWORD})
        assert changed.status_code==200
        assert changed.json()['user']['must_change_password'] is False
        assert changed.json()['csrf_token'] != first['csrf_token']
        assert auth_client.cookies.get('fastonto_session') != original
        assert other.get('/api/auth/me').status_code==401
        assert login(other).status_code==401
        assert login(other,NEW_PASSWORD).status_code==200
    assert auth_client.get('/api/models/template').status_code==200
    stored=auth_app[1].user.password_hash
    assert stored.startswith('$argon2id$') and NEW_PASSWORD not in stored
    assert HASHER.verify(stored,NEW_PASSWORD)


def test_csrf_and_origin_guards(auth_client):
    first=login(auth_client).json()
    payload={'current_password':PASSWORD,'new_password':NEW_PASSWORD}
    assert auth_client.post('/api/auth/password',json=payload).status_code==403
    assert auth_client.post('/api/auth/password',json=payload,headers={'X-CSRF-Token':'wrong'}).status_code==403
    assert auth_client.post('/api/models/import',json={'filename':'x.md','content_base64':'IyBY'}).status_code==403
    assert auth_client.post('/api/auth/password',json=payload,headers={'Origin':'http://evil.invalid','X-CSRF-Token':first['csrf_token']}).status_code==403
    assert auth_client.post('/api/auth/logout',json={},headers={'X-CSRF-Token':first['csrf_token']}).status_code==200
    assert auth_client.get('/api/auth/me').status_code==401


def test_login_requires_origin(auth_app):
    with TestClient(auth_app[0]) as client:
        assert login(client).status_code==403


def test_wrong_password_and_lockout_are_generic(auth_client):
    for _ in range(5):
        result=login(auth_client,'wrong')
        assert result.status_code==401
        assert PASSWORD not in result.text
    assert login(auth_client).status_code==401


def test_rate_limit_for_unknown_user(auth_client):
    for _ in range(10):
        assert auth_client.post('/api/auth/login',json={'username':'unknown','password':'wrong'}).status_code==401
    assert auth_client.post('/api/auth/login',json={'username':'unknown','password':'wrong'}).status_code==429


@pytest.mark.parametrize('field',['expires','last'])
def test_absolute_and_idle_expiration(auth_client,auth_app,field):
    login(auth_client)
    session=next(iter(auth_app[1].sessions.values()))
    session[field]=datetime.now(timezone.utc)-timedelta(hours=9)
    assert auth_client.get('/api/auth/me').status_code==401


def test_disabled_account_revokes_access(auth_client,auth_app):
    login(auth_client)
    auth_app[1].user=replace(auth_app[1].user,enabled=False)
    assert auth_client.get('/api/auth/me').status_code==401


def test_validation_does_not_echo_password(auth_client):
    too_long='SecretDoNotEcho'*100
    r=auth_client.post('/api/auth/login',json={'username':'admin','password':too_long})
    assert r.status_code==422 and 'SecretDoNotEcho' not in r.text


def test_secure_cookie_for_https(password_hash):
    settings=Settings(_env_file=None,db_dsn='',db_password='',public_origin='https://ontology.example:8025')
    app=create_app(settings,auth_store=MemoryAuthStore(password_hash))
    with TestClient(app,base_url='https://ontology.example:8025',headers={'Origin':settings.public_origin}) as client:
        response=login(client)
        cookie=response.headers['set-cookie']
        assert '__Host-fastonto_session=' in cookie and 'Secure' in cookie and 'HttpOnly' in cookie
        assert client.get('/api/auth/me').status_code==200


def test_remote_http_needs_explicit_opt_in():
    with pytest.raises(ValueError): Settings(_env_file=None,public_origin='http://192.0.2.10:8025',allow_insecure_http=False)
    assert not Settings(_env_file=None,public_origin='http://192.0.2.10:8025',allow_insecure_http=True).secure_cookie


def test_salted_hashes_differ(password_hash):
    assert HASHER.hash(PASSWORD) != password_hash
