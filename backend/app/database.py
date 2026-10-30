from contextlib import contextmanager
from threading import Lock

import oracledb

from .config import Settings

# Keep NUMBER values exact through the driver; API explicitly serializes decimals.
oracledb.defaults.fetch_decimals = True


class DatabaseUnavailable(Exception):
    pass


class Database:
    """Lazy bounded pool. Never auto-migrates or retrieves SQLcl credentials."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._pool = None
        self._lock = Lock()

    @contextmanager
    def connection(self, *, readonly: bool = True):
        if not self.settings.database_configured:
            raise DatabaseUnavailable("请在本机 .env 配置 FASTONTO 数据库连接。")
        if self.settings.db_user.upper() != "FASTONTO":
            raise DatabaseUnavailable("后端只允许使用 FASTONTO 应用账号。")
        try:
            with self._lock:
                if self._pool is None:
                    self._pool = oracledb.create_pool(
                        user=self.settings.db_user,
                        password=self.settings.db_password.get_secret_value(),
                        dsn=self.settings.db_dsn,
                        min=0, max=self.settings.db_pool_max, increment=1,
                        getmode=oracledb.POOL_GETMODE_TIMEDWAIT, wait_timeout=5000,
                        tcp_connect_timeout=5,
                    )
            conn = self._pool.acquire()
            conn.call_timeout = self.settings.db_timeout_ms
            conn.autocommit = False
            with conn.cursor() as cursor:
                cursor.execute("select sys_context('USERENV','SESSION_USER'), "
                               "sys_context('USERENV','CURRENT_SCHEMA') from dual")
                if cursor.fetchone() != ("FASTONTO", "FASTONTO"):
                    raise DatabaseUnavailable("连接身份不符合 FASTONTO 隔离要求。")
            conn.rollback()
            if readonly:
                with conn.cursor() as cursor:
                    cursor.execute("set transaction read only")
        except DatabaseUnavailable:
            if 'conn' in locals(): conn.close()
            raise
        except oracledb.Error as exc:
            if 'conn' in locals(): conn.close()
            raise DatabaseUnavailable("FASTONTO Oracle 连接不可用；请检查本机 .env 的 FASTONTO_DB_DSN、网络可达性和应用账号配置。") from exc
        try:
            yield conn
        finally:
            try: conn.rollback()
            finally: conn.close()

    def close(self):
        if self._pool is not None:
            self._pool.close(force=True)
