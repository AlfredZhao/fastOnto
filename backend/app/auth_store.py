"""Oracle-backed users and revocable sessions. No plaintext passwords/session tokens."""
from dataclasses import dataclass

from .database import Database


@dataclass(frozen=True)
class User:
    id: str
    username: str
    password_hash: str
    enabled: bool
    must_change_password: bool
    version: int
    locked: bool = False


@dataclass(frozen=True)
class Principal:
    id: str
    username: str
    must_change_password: bool
    csrf_token: str
    token_hash: str


class AuthConflict(Exception):
    pass


class OracleAuthStore:
    def __init__(self, db: Database):
        self.db = db

    def get_user(self, username: str) -> User | None:
        with self.db.connection() as conn, conn.cursor() as c:
            c.execute("select user_id,username,password_hash,enabled,must_change_password,credential_version, "
                      "case when locked_until>systimestamp then 1 else 0 end from FO_USERS where username=:username",
                      {"username": username})
            r = c.fetchone()
            return User(r[0],r[1],r[2],bool(r[3]),bool(r[4]),int(r[5]),bool(r[6])) if r else None

    def record_failure(self, user: User):
        with self.db.connection(readonly=False) as conn, conn.cursor() as c:
            c.execute("update FO_USERS set "
                      "failed_attempts=case when failed_attempts>=4 then 0 else failed_attempts+1 end, "
                      "locked_until=case when failed_attempts>=4 then systimestamp+interval '15' minute else locked_until end "
                      "where user_id=:id and credential_version=:version "
                      "and (locked_until is null or locked_until<=systimestamp)",
                      {"id": user.id, "version": user.version})
            conn.commit()

    @staticmethod
    def _insert_session(c, user_id, version, token_hash, csrf, hours):
        c.execute("insert into FO_AUTH_SESSIONS(token_hash,user_id,csrf_token,credential_version,expires_at) "
                  "values(:token_hash,:user_id,:csrf,:version,systimestamp+numtodsinterval(:hours,'HOUR'))",
                  {"token_hash": token_hash, "user_id": user_id, "csrf": csrf, "version": version, "hours": hours})

    def create_session(self, user: User, token_hash: str, csrf: str, hours: int, replacement_hash: str | None = None):
        with self.db.connection(readonly=False) as conn, conn.cursor() as c:
            c.execute("select credential_version,password_hash,enabled, "
                      "case when locked_until>systimestamp then 1 else 0 end "
                      "from FO_USERS where user_id=:id for update wait 3", {"id": user.id})
            r = c.fetchone()
            if not r or int(r[0]) != user.version or r[1] != user.password_hash or not r[2] or r[3]:
                raise AuthConflict()
            if replacement_hash:
                c.execute("update FO_USERS set failed_attempts=0,locked_until=null,password_hash=:hash where user_id=:id",
                          {"hash": replacement_hash, "id": user.id})
            else:
                c.execute("update FO_USERS set failed_attempts=0,locked_until=null where user_id=:id", {"id": user.id})
            c.execute("delete from FO_AUTH_SESSIONS where expires_at<=systimestamp")
            self._insert_session(c,user.id,user.version,token_hash,csrf,hours)
            conn.commit()

    def lookup_session(self, token_hash: str, idle_minutes: int) -> Principal | None:
        with self.db.connection(readonly=False) as conn, conn.cursor() as c:
            c.execute("select u.user_id,u.username,u.must_change_password,s.csrf_token,s.credential_version "
                      "from FO_AUTH_SESSIONS s join FO_USERS u on u.user_id=s.user_id "
                      "where s.token_hash=:token_hash and s.expires_at>systimestamp "
                      "and s.last_seen_at>systimestamp-numtodsinterval(:idle,'MINUTE') "
                      "and u.enabled=1 and s.credential_version=u.credential_version",
                      {"token_hash": token_hash, "idle": idle_minutes})
            r = c.fetchone()
            if not r:
                return None
            c.execute("update FO_AUTH_SESSIONS set last_seen_at=systimestamp "
                      "where token_hash=:token_hash and credential_version=:version "
                      "and expires_at>systimestamp "
                      "and exists(select 1 from FO_USERS u where u.user_id=FO_AUTH_SESSIONS.user_id "
                      "and u.enabled=1 and u.credential_version=:version)",
                      {"token_hash": token_hash, "version": int(r[4])})
            if c.rowcount != 1:
                return None
            conn.commit()
            return Principal(r[0],r[1],bool(r[2]),r[3],token_hash)

    def change_password(self, user: User, new_hash: str, token_hash: str, csrf: str, hours: int):
        with self.db.connection(readonly=False) as conn, conn.cursor() as c:
            c.execute("update FO_USERS set password_hash=:new_hash,must_change_password=0, "
                      "credential_version=credential_version+1,failed_attempts=0,locked_until=null, "
                      "password_changed_at=systimestamp where user_id=:id and enabled=1 "
                      "and credential_version=:version and password_hash=:old_hash",
                      {"new_hash": new_hash, "id": user.id, "version": user.version, "old_hash": user.password_hash})
            if c.rowcount != 1:
                raise AuthConflict()
            c.execute("delete from FO_AUTH_SESSIONS where user_id=:id", {"id": user.id})
            self._insert_session(c,user.id,user.version+1,token_hash,csrf,hours)
            conn.commit()

    def logout(self, token_hash: str):
        with self.db.connection(readonly=False) as conn, conn.cursor() as c:
            c.execute("delete from FO_AUTH_SESSIONS where token_hash=:token_hash", {"token_hash": token_hash})
            conn.commit()
