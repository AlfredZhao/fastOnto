import hashlib
import re
import secrets
from collections import OrderedDict, deque
from dataclasses import dataclass
from threading import BoundedSemaphore, Lock
from time import monotonic

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from .auth_store import AuthConflict, OracleAuthStore, Principal
from .config import Settings

HASHER = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2, type=Type.ID)
DUMMY_HASH = HASHER.hash(secrets.token_urlsafe(32))
HASH_SLOTS = BoundedSemaphore(2)
USERNAME = re.compile(r"^[a-z][a-z0-9_.-]{2,63}$")
PUBLIC_PATHS = {"/api/health", "/api/auth/login"}
CHANGE_ALLOWED = {"/api/auth/me", "/api/auth/logout", "/api/auth/password"}


def failure(status: int, message: str, code: str):
    return HTTPException(status, detail={"message": message, "code": code})


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def password_ok(stored: str, candidate: str) -> bool:
    try:
        return HASHER.verify(stored, candidate)
    except (VerificationError, InvalidHashError):
        return False


class LoginLimiter:
    """Bounded per-process protection, combined with persistent account lockouts."""
    def __init__(self):
        self.lock = Lock()
        self.clients = OrderedDict()
        self.global_events = deque()

    def take(self, address: str):
        now = monotonic()
        with self.lock:
            for queue in (self.global_events,):
                while queue and queue[0] < now-60: queue.popleft()
            events = self.clients.setdefault(address, deque())
            self.clients.move_to_end(address)
            while events and events[0] < now-60: events.popleft()
            while len(self.clients)>4096: self.clients.popitem(last=False)
            if len(events)>=10 or len(self.global_events)>=120:
                raise failure(429,"尝试过于频繁，请稍后重试。","rate_limited")
            events.append(now)
            self.global_events.append(now)


@dataclass(frozen=True)
class LoginResult:
    principal: Principal
    token: str


class AuthService:
    def __init__(self, store: OracleAuthStore, settings: Settings):
        self.store, self.settings = store, settings
        self.limiter = LoginLimiter()

    def login(self, username: str, password: str, address: str) -> LoginResult:
        self.limiter.take(address)
        if not HASH_SLOTS.acquire(blocking=False):
            raise failure(429,"认证服务繁忙，请稍后重试。","rate_limited")
        try:
            user = self.store.get_user(username)
            valid = password_ok(user.password_hash if user else DUMMY_HASH,password)
            if not user or not valid or not user.enabled or user.locked:
                if user and user.enabled and not user.locked:
                    self.store.record_failure(user)
                raise failure(401,"用户名或密码错误，或账号暂时不可用。","invalid_credentials")
            token, csrf = secrets.token_urlsafe(32), secrets.token_hex(32)
            replacement = HASHER.hash(password) if HASHER.check_needs_rehash(user.password_hash) else None
            try:
                self.store.create_session(user,token_digest(token),csrf,self.settings.session_hours,replacement)
            except AuthConflict:
                raise failure(401,"账号状态已变化，请重新登录。","invalid_credentials")
            return LoginResult(Principal(user.id,user.username,user.must_change_password,csrf,token_digest(token)),token)
        finally:
            HASH_SLOTS.release()

    def authenticate(self, token: str | None) -> Principal:
        if not token or not re.fullmatch(r"[A-Za-z0-9_-]{40,64}",token):
            raise failure(401,"请先登录。","unauthenticated")
        result = self.store.lookup_session(token_digest(token),self.settings.session_idle_minutes)
        if result is None:
            raise failure(401,"登录已失效，请重新登录。","unauthenticated")
        return result

    def change_password(self, principal: Principal, current: str, new: str, address: str) -> LoginResult:
        self.limiter.take(address)
        if len(new)<15 or len(new)>128 or len(new.encode())>512:
            raise failure(422,"新密码需为 15–128 个字符，最多 512 字节；建议使用不复用的长口令。","weak_password")
        if new == current or new.lower() == principal.username.lower() or not new.strip() or new.lower() in {'passwordpassword','123456789012345','1234567890123456'}:
            raise failure(422,"新密码不能与当前密码或用户名相同。","weak_password")
        if not HASH_SLOTS.acquire(blocking=False):
            raise failure(429,"认证服务繁忙，请稍后重试。","rate_limited")
        try:
            user = self.store.get_user(principal.username)
            if not user or user.locked or not password_ok(user.password_hash,current):
                if user and not user.locked: self.store.record_failure(user)
                raise failure(400,"当前密码不正确或账号暂时不可用。","invalid_password")
            token, csrf = secrets.token_urlsafe(32), secrets.token_hex(32)
            try:
                self.store.change_password(user,HASHER.hash(new),token_digest(token),csrf,self.settings.session_hours)
            except AuthConflict:
                raise failure(409,"密码已在其他会话变更，请重新登录。","credential_conflict")
            return LoginResult(Principal(user.id,user.username,False,csrf,token_digest(token)),token)
        finally:
            HASH_SLOTS.release()


def require_user(request: Request):
    if request.url.path in PUBLIC_PATHS:
        return
    service = request.app.state.auth
    principal = service.authenticate(request.cookies.get(service.settings.cookie_name))
    if request.method not in {"GET","HEAD","OPTIONS"}:
        csrf = request.headers.get("x-csrf-token", "")
        if not secrets.compare_digest(csrf,principal.csrf_token):
            raise failure(403,"安全校验失败，请刷新后重试。","csrf_failed")
    if principal.must_change_password and request.url.path not in CHANGE_ALLOWED:
        raise failure(403,"首次登录必须修改临时密码。","password_change_required")
    request.state.principal = principal


class LoginInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=3,max_length=64)
    password: SecretStr = Field(min_length=1,max_length=1024)


class PasswordInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_password: SecretStr = Field(min_length=1,max_length=1024)
    new_password: SecretStr = Field(min_length=15,max_length=128)


def user_response(principal: Principal, settings: Settings):
    return {"user": {"id": principal.id,"username": principal.username,
                     "must_change_password": principal.must_change_password},
            "csrf_token": principal.csrf_token,"insecure_http": not settings.secure_cookie}


def set_session(response: Response,result: LoginResult,settings: Settings):
    response.set_cookie(settings.cookie_name,result.token,max_age=settings.session_hours*3600,
                        httponly=True,secure=settings.secure_cookie,samesite="strict",path="/")


router = APIRouter(prefix="/api/auth")


@router.post("/login")
def login(payload: LoginInput,request: Request,response: Response):
    username = payload.username.strip().lower()
    if not USERNAME.fullmatch(username):
        raise failure(401,"用户名或密码错误，或账号暂时不可用。","invalid_credentials")
    service = request.app.state.auth
    result = service.login(username,payload.password.get_secret_value(),request.client.host if request.client else "unknown")
    # Replace an existing session on explicit login; never carry over a supplied session ID.
    previous = request.cookies.get(service.settings.cookie_name)
    if previous: service.store.logout(token_digest(previous))
    set_session(response,result,service.settings)
    return user_response(result.principal,service.settings)


@router.get("/me")
def me(request: Request):
    return user_response(request.state.principal,request.app.state.auth.settings)


@router.post("/password")
def change_password(payload: PasswordInput,request: Request,response: Response):
    service = request.app.state.auth
    result = service.change_password(request.state.principal,payload.current_password.get_secret_value(),
                                     payload.new_password.get_secret_value(),request.client.host if request.client else "unknown")
    set_session(response,result,service.settings)
    return user_response(result.principal,service.settings)


@router.post("/logout")
def logout(request: Request,response: Response):
    service = request.app.state.auth
    service.store.logout(request.state.principal.token_hash)
    response.delete_cookie(service.settings.cookie_name,path="/",secure=service.settings.secure_cookie,
                           httponly=True,samesite="strict")
    return {"ok": True}
