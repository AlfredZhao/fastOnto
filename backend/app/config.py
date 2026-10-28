from pathlib import Path
from urllib.parse import urlsplit
import ipaddress
import re
import base64

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="FASTONTO_", env_file=ROOT / ".env", extra="ignore"
    )
    db_user: str = "FASTONTO"
    db_password: SecretStr = SecretStr("")
    db_dsn: str = ""
    db_pool_max: int = Field(4, ge=1, le=16)
    db_timeout_ms: int = Field(10000, ge=1000, le=60000)
    public_origin: str = "http://127.0.0.1:8025"
    allow_insecure_http: bool = False
    session_hours: int = Field(8, ge=1, le=24)
    session_idle_minutes: int = Field(30, ge=5, le=120)
    tls_cert_file: str = ""
    tls_key_file: str = ""
    source_master_key: SecretStr = SecretStr("")
    source_master_key_version: str = "v1"

    @model_validator(mode="after")
    def validate_public_origin(self):
        url = urlsplit(self.public_origin)
        if url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password or url.path not in {"", "/"} or url.query or url.fragment:
            raise ValueError("PUBLIC_ORIGIN 必须是完整的 http(s) 来源地址，不含路径或凭据。")
        host = url.hostname
        if not re.fullmatch(r"[A-Za-z0-9.-]+", host):
            raise ValueError("当前 PUBLIC_ORIGIN 仅支持 IPv4 或 ASCII 域名。")
        is_loopback = host == "localhost"
        try:
            is_loopback = is_loopback or ipaddress.ip_address(host).is_loopback
        except ValueError:
            pass
        if url.scheme == "http" and not is_loopback and not self.allow_insecure_http:
            raise ValueError("非本机 HTTP 需要显式设置 ALLOW_INSECURE_HTTP=true；建议使用 HTTPS。")
        # Validate port eagerly and canonicalize the origin used for CSRF checks.
        _ = url.port
        self.public_origin = f"{url.scheme}://{url.netloc}".rstrip("/")
        return self

    @property
    def secure_cookie(self) -> bool:
        return self.public_origin.startswith("https://")

    @property
    def cookie_name(self) -> str:
        return "__Host-fastonto_session" if self.secure_cookie else "fastonto_session"

    @property
    def allowed_origins(self) -> set[str]:
        return {self.public_origin, "http://127.0.0.1:8025", "http://localhost:8025"}

    @property
    def database_configured(self) -> bool:
        return bool(self.db_dsn and self.db_password.get_secret_value())

    @property
    def source_master_key_configured(self) -> bool:
        value = self.source_master_key.get_secret_value()
        if not value: return False
        try:
            return len(base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))) == 32
        except ValueError:
            return False
