"""Encrypted, read-only Oracle business-source registration and metadata discovery."""
import base64
import hashlib
import json
import re
import uuid

import yaml

import oracledb
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .database import Database, DatabaseUnavailable
from .sources import serialize

IDENT = re.compile(r"^[A-Z][A-Z0-9_$#]{0,127}$")


class BusinessSourceError(ValueError): pass


def _text(value): return value.read() if hasattr(value, "read") else value
def _id(): return str(uuid.uuid4())
def _identifier(value, label):
    value = value.upper() if isinstance(value, str) else ""
    if not IDENT.fullmatch(value): raise BusinessSourceError(f"{label} 必须是 Oracle 未加引号标识符。")
    return value
def _value(value, label, limit=200):
    if not isinstance(value, str) or not value.strip() or len(value) > limit: raise BusinessSourceError(f"{label} 必须是 1 至 {limit} 字符。")
    return value.strip()


class CredentialCipher:
    def __init__(self, settings): self.settings = settings
    def key(self):
        raw = self.settings.source_master_key.get_secret_value()
        try: key = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
        except ValueError as exc: raise BusinessSourceError("本机 SOURCE_MASTER_KEY 格式无效。") from exc
        if len(key) != 32: raise BusinessSourceError("本机 SOURCE_MASTER_KEY 必须是 base64url 编码的 32 字节密钥。")
        return key
    def encrypt(self, dsn, username, password):
        nonce = __import__('os').urandom(12)
        plain = json.dumps({"dsn": _value(dsn,"DSN",1000), "username": _value(username,"用户名",128), "password": _value(password,"密码",1000)}, separators=(",", ":")).encode()
        cipher = AESGCM(self.key()).encrypt(nonce, plain, None)
        return "v1." + base64.urlsafe_b64encode(nonce).decode().rstrip("=") + "." + base64.urlsafe_b64encode(cipher).decode().rstrip("=")
    def decrypt(self, payload):
        try:
            version, nonce, cipher = _text(payload).split(".")
            if version != "v1": raise ValueError()
            decode = lambda value: base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
            return json.loads(AESGCM(self.key()).decrypt(decode(nonce), decode(cipher), None))
        except Exception as exc: raise BusinessSourceError("无法解密业务数据源凭据；请检查本机主密钥。") from exc


def list_sources(db: Database):
    with db.connection() as conn, conn.cursor() as c:
        c.execute("select source_id,domain_id,code,title,owner_schema,enabled,credential_key_version from FO_BUSINESS_SOURCES order by title")
        return [{"id": r[0], "domain_id": r[1], "code": r[2], "title": r[3], "owner_schema": r[4], "enabled": bool(r[5]), "credential_key_version": r[6], "readonly": True} for r in c]


def create_source(db: Database, settings, domain_id, code, title, owner_schema, dsn, username, password):
    cipher = CredentialCipher(settings)
    item = {"id": _id(), "domain_id": domain_id, "code": _identifier(code,"技术标识"), "title": _value(title,"数据源名称"), "owner_schema": _identifier(owner_schema,"Schema"), "ciphertext": cipher.encrypt(dsn,username,password), "version": settings.source_master_key_version}
    with db.connection(readonly=False) as conn, conn.cursor() as c:
        c.setinputsizes(ciphertext=oracledb.DB_TYPE_CLOB)
        c.execute("insert into FO_BUSINESS_SOURCES(source_id,domain_id,code,title,owner_schema,credentials_ciphertext,credential_key_version) values(:id,:domain_id,:code,:title,:owner_schema,:ciphertext,:version)", item)
        conn.commit()
    return {"id": item["id"], "domain_id": domain_id, "code": item["code"], "title": item["title"], "owner_schema": item["owner_schema"], "readonly": True, "enabled": True, "credential_key_version": item["version"]}


def update_source(db: Database, settings, source_id, title, owner_schema, dsn, username, password):
    cipher = CredentialCipher(settings)
    binds = {"id": source_id, "title": _value(title,"数据源名称"), "owner_schema": _identifier(owner_schema,"Schema"),
             "ciphertext": cipher.encrypt(dsn,username,password), "version": settings.source_master_key_version}
    with db.connection(readonly=False) as conn, conn.cursor() as c:
        c.setinputsizes(ciphertext=oracledb.DB_TYPE_CLOB)
        c.execute("update FO_BUSINESS_SOURCES set title=:title,owner_schema=:owner_schema,credentials_ciphertext=:ciphertext,credential_key_version=:version,updated_at=systimestamp where source_id=:id", binds)
        if c.rowcount != 1: raise BusinessSourceError("业务数据源不存在。")
        conn.commit()
    return {"id": source_id, "title": binds["title"], "owner_schema": binds["owner_schema"], "readonly": True, "credential_key_version": binds["version"]}


def _credentials(db, settings, source_id):
    with db.connection() as conn, conn.cursor() as c:
        c.execute("select owner_schema,credentials_ciphertext,enabled from FO_BUSINESS_SOURCES where source_id=:id", {"id": source_id})
        row = c.fetchone()
    if row is None or not row[2]: raise BusinessSourceError("业务数据源不存在或已停用。")
    return row[0], CredentialCipher(settings).decrypt(row[1])


def discover(db: Database, settings, source_id):
    owner, credential = _credentials(db, settings, source_id)
    try:
        with oracledb.connect(user=credential["username"], password=credential["password"], dsn=credential["dsn"], tcp_connect_timeout=5) as conn:
            conn.call_timeout = settings.db_timeout_ms
            with conn.cursor() as c:
                c.execute("set transaction read only")
                c.execute("select object_name,object_type from all_objects where owner=:owner and object_type in ('TABLE','VIEW') order by object_name fetch first 200 rows only", {"owner": owner})
                return {"owner_schema": owner, "items": [{"name": r[0], "type": r[1]} for r in c.fetchall()], "notice": "仅列出最多 200 个表/视图；不会读取业务行。"}
    except oracledb.Error as exc:
        raise DatabaseUnavailable("外部 Oracle 数据源无法连接、认证或读取元数据。") from exc


def _external(db, settings, source_id, object_name, operation):
    owner, credential = _credentials(db, settings, source_id)
    name = _identifier(object_name, "对象名")
    try:
        with oracledb.connect(user=credential["username"], password=credential["password"], dsn=credential["dsn"], tcp_connect_timeout=5) as conn:
            conn.call_timeout = settings.db_timeout_ms
            with conn.cursor() as c:
                c.execute("set transaction read only")
                c.execute("select object_type from all_objects where owner=:owner and object_name=:name and object_type in ('TABLE','VIEW')", {"owner": owner, "name": name})
                row = c.fetchone()
                if row is None: raise BusinessSourceError("对象不在该数据源可见的表/视图清单中。")
                c.execute("select column_name,data_type,nullable,column_id from all_tab_columns where owner=:owner and table_name=:name order by column_id", {"owner": owner, "name": name})
                columns = [{"name": r[0], "data_type": r[1], "nullable": r[2] == 'Y', "position": r[3]} for r in c.fetchall()]
                if not columns: raise BusinessSourceError("对象没有可读取的列。")
                return operation(c, owner, name, row[0], columns)
    except BusinessSourceError:
        raise
    except oracledb.Error as exc:
        raise DatabaseUnavailable("外部 Oracle 数据源无法读取元数据或预览数据。") from exc


def metadata(db: Database, settings, source_id, object_name):
    def read(c, owner, name, object_type, columns):
        c.execute("select cc.column_name from all_constraints ac join all_cons_columns cc on cc.owner=ac.owner and cc.constraint_name=ac.constraint_name where ac.owner=:owner and ac.table_name=:name and ac.constraint_type='P' order by cc.position", {"owner": owner, "name": name})
        return {"owner_schema": owner, "name": name, "type": object_type, "columns": columns, "primary_key": [r[0] for r in c.fetchall()], "notice": "字段信息实时读取自外部 Oracle 数据字典；不会推断业务唯一性。"}
    return _external(db, settings, source_id, object_name, read)


def _preview_value(value):
    if hasattr(value, "read"):
        value = value.read(4097)
        if isinstance(value, str) and len(value) > 4096: return value[:4096] + "…"
    return serialize(value)


def preview(db: Database, settings, source_id, object_name, offset, limit):
    def read(c, owner, name, object_type, columns):
        selected = ','.join(item["name"] for item in columns)
        # Identifiers were obtained from ALL_TAB_COLUMNS after strict validation; no user SQL is interpolated.
        c.execute(f"select {selected} from {owner}.{name} offset :row_offset rows fetch next :row_limit rows only", {"row_offset": offset, "row_limit": limit + 1})
        rows = c.fetchall()
        return {"source_id": source_id, "object": name, "columns": [item["name"] for item in columns], "rows": [[_preview_value(value) for value in row] for row in rows[:limit]], "offset": offset, "limit": limit, "has_more": len(rows) > limit, "notice": "外部源实时只读预览；未指定业务排序，跨页不保证稳定快照；长 LOB 文本最多返回 4096 字符。"}
    return _external(db, settings, source_id, object_name, read)


def draft(db: Database, settings, source_id, object_name):
    type_map = {"NUMBER": "decimal", "FLOAT": "double", "BINARY_FLOAT": "float", "BINARY_DOUBLE": "double", "DATE": "date", "TIMESTAMP": "datetime", "TIMESTAMP WITH TIME ZONE": "datetime", "CLOB": "string", "NCLOB": "string", "BLOB": "string"}
    def safe(value):
        value = re.sub(r"[^A-Za-z0-9_]", "_", value)
        return value if re.match(r"^[A-Za-z_]", value) else "Entity_" + value
    def camel(value): return ''.join(part.capitalize() for part in safe(value).lower().split('_')) or 'Entity'
    def snake(value): return safe(value).lower()
    def read(c, owner, name, object_type, columns):
        cls = camel(name)
        attributes = {snake(item["name"]): {"title": item["name"], "range": type_map.get(item["data_type"], "string"), "required": not item["nullable"]} for item in columns}
        data = {"id": f"https://example.org/ontology/{name.lower()}", "name": f"{name.lower()}_source", "title": f"{owner}.{name} 建模草稿", "description": "由外部 Oracle 表/视图字段生成的候选模型；需人工确认业务语义、标识、关系与约束。", "prefixes": {"model": "https://example.org/ontology/", "linkml": "https://w3id.org/linkml/"}, "default_prefix": "model", "default_range": "string", "imports": ["linkml:types"], "classes": {cls: {"title": name, "attributes": attributes}}}
        return {"source": yaml.safe_dump(data, allow_unicode=True, sort_keys=False), "notice": "仅根据字段名称、Oracle 类型和 NULLABLE 生成候选；不推断主键、对象关系、枚举或业务规则。"}
    return _external(db, settings, source_id, object_name, read)
