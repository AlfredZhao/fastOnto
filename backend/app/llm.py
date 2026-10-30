"""Encrypted OpenAI-compatible LLM configuration and bounded document analysis."""
import base64
import json
import os
import re
import uuid
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

import oracledb
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .document_import import CandidateClass, DocumentInput
from .modeling import InvalidModel

CODE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,79}$")


class LLMError(ValueError):
    pass


def _id(): return str(uuid.uuid4())
def _text(value): return value.read() if hasattr(value, "read") else value
def _table_error(exc):
    code = getattr(exc.args[0], "code", None)
    if code == 942:
        raise LLMError("LLM 配置表不可用；请确认迁移 008 已在 FASTONTO / ORCLPDB1 成功执行。") from exc
    suffix = str(code) if isinstance(code, int) else "unknown"
    raise LLMError(f"LLM 配置操作失败（Oracle 错误代码 {suffix}）；请检查 FASTONTO 连接用户、迁移和表权限。") from exc
def _value(value, name, limit):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit:
        raise LLMError(f"{name} 必须是 1 至 {limit} 字符。")
    return value.strip()
def _code(value):
    value = _value(value, "技术标识", 80)
    if not CODE.fullmatch(value): raise LLMError("技术标识只能包含 ASCII 字母、数字和下划线，且不能以数字开头。")
    return value
def _base_url(value):
    value = _value(value, "LLM 地址", 1000).rstrip("/")
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise LLMError("LLM 地址必须是无凭据、无查询参数的 HTTP(S) 基础地址。")
    return value


class ApiKeyCipher:
    def __init__(self, settings): self.settings = settings
    aad = b"fastonto:llm-api-key:v1"
    def key(self):
        raw = self.settings.source_master_key.get_secret_value()
        try: key = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
        except ValueError as exc: raise LLMError("本机 SOURCE_MASTER_KEY 格式无效。") from exc
        if len(key) != 32: raise LLMError("本机 SOURCE_MASTER_KEY 必须是 base64url 编码的 32 字节密钥。")
        return key
    def encrypt(self, api_key):
        nonce = os.urandom(12)
        cipher = AESGCM(self.key()).encrypt(nonce, _value(api_key, "API Key", 1000).encode(), self.aad)
        return "v1." + base64.urlsafe_b64encode(nonce).decode().rstrip("=") + "." + base64.urlsafe_b64encode(cipher).decode().rstrip("=")
    def decrypt(self, payload):
        try:
            version, nonce, cipher = _text(payload).split(".")
            if version != "v1": raise ValueError()
            decode = lambda value: base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
            return AESGCM(self.key()).decrypt(decode(nonce), decode(cipher), self.aad).decode()
        except Exception as exc: raise LLMError("无法解密 LLM API Key；请检查本机主密钥。") from exc


def list_models(db):
    try:
        with db.connection() as conn, conn.cursor() as c:
            c.execute("select llm_id,code,title,base_url,model_name,credential_key_version,enabled,is_default from FO_LLM_MODELS order by is_default desc,title")
            return [{"id": row[0], "code": row[1], "title": row[2], "base_url": row[3], "model_name": row[4], "credential_key_version": row[5], "enabled": bool(row[6]), "is_default": bool(row[7])} for row in c]
    except oracledb.Error as exc: _table_error(exc)


def create_model(db, settings, code, title, base_url, model_name, api_key, make_default):
    item = {"id": _id(), "code": _code(code), "title": _value(title, "模型名称", 200), "base_url": _base_url(base_url),
            "model_name": _value(model_name, "模型标识", 200), "cipher": ApiKeyCipher(settings).encrypt(api_key),
            "version": settings.source_master_key_version, "is_default": 1 if make_default else 0}
    try:
        with db.connection(readonly=False) as conn, conn.cursor() as c:
            if item["is_default"]:
                c.execute("update FO_LLM_MODELS set is_default=0,updated_at=systimestamp where is_default=1")
            c.setinputsizes(cipher=oracledb.DB_TYPE_CLOB)
            c.execute("insert into FO_LLM_MODELS(llm_id,code,title,base_url,model_name,api_key_ciphertext,credential_key_version,is_default) values(:id,:code,:title,:base_url,:model_name,:cipher,:version,:is_default)", item)
            conn.commit()
    except oracledb.Error as exc: _table_error(exc)
    return {"id": item["id"], "code": item["code"], "title": item["title"], "base_url": item["base_url"], "model_name": item["model_name"], "enabled": True, "is_default": bool(item["is_default"])}


def set_default(db, llm_id):
    with db.connection(readonly=False) as conn, conn.cursor() as c:
        c.execute("select count(*) from FO_LLM_MODELS where llm_id=:id and enabled=1", {"id": llm_id})
        if c.fetchone()[0] != 1: raise LLMError("LLM 不存在或已停用。")
        c.execute("update FO_LLM_MODELS set is_default=0,updated_at=systimestamp where is_default=1")
        c.execute("update FO_LLM_MODELS set is_default=1,updated_at=systimestamp where llm_id=:id", {"id": llm_id})
        conn.commit()
    return {"id": llm_id, "is_default": True}


def _model(db, settings, llm_id=None):
    with db.connection() as conn, conn.cursor() as c:
        if llm_id:
            c.execute("select llm_id,title,base_url,model_name,api_key_ciphertext from FO_LLM_MODELS where llm_id=:id and enabled=1", {"id": llm_id})
        else:
            c.execute("select llm_id,title,base_url,model_name,api_key_ciphertext from FO_LLM_MODELS where is_default=1 and enabled=1")
        row = c.fetchone()
    if row is None:
        raise LLMError("没有可用的默认 LLM；请在 LLM 配置页新增并设为默认模型，或选择一个可用模型。")
    return {"id": row[0], "title": row[1], "base_url": row[2], "model_name": row[3], "api_key": ApiKeyCipher(settings).decrypt(row[4])}


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl): return None


def _chat(model, messages, max_tokens=1200):
    request = Request(model["base_url"] + "/chat/completions", data=json.dumps({"model": model["model_name"], "messages": messages, "temperature": 0, "max_tokens": max_tokens}, ensure_ascii=False).encode(), method="POST", headers={"Authorization": f"Bearer {model['api_key']}", "Content-Type": "application/json", "Accept": "application/json"})
    try:
        with build_opener(_NoRedirect).open(request, timeout=30) as response:
            payload = json.loads(response.read(2 * 1024 * 1024).decode())
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        raise LLMError("LLM 连通性或响应校验失败；请检查 HTTPS 地址、模型标识和 API Key。") from exc
    try:
        return payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError("LLM 未返回兼容的 chat completion 内容。") from exc


def test_model(db, settings, llm_id):
    model = _model(db, settings, llm_id)
    result = _chat(model, [{"role": "user", "content": "Reply with exactly: OK"}], 8)
    return {"id": model["id"], "ok": True, "notice": "LLM 已通过 HTTPS 连通性测试。", "sample": result[:80]}


def _json_content(content):
    value = content.strip()
    if value.startswith("```"):
        value = re.sub(r"^```(?:json)?\s*|\s*```$", "", value, flags=re.I)
    try: return json.loads(value)
    except ValueError as exc: raise LLMError("LLM 未返回可解析的 JSON 候选；请重试或更换模型。") from exc


def analyze_document(db, settings, payload: DocumentInput, local_result: dict):
    if local_result.get("kind") != "document" or payload.llm_id is None: return local_result
    model = _model(db, settings, str(payload.llm_id))
    context = {"filename": payload.filename, "local_candidates": local_result.get("classes", [])}
    # Plain-text formats can contribute bounded source text; Office formats remain represented by safely parsed candidates.
    if payload.filename.lower().endswith((".md", ".txt")):
        try: context["text"] = base64.b64decode(payload.content_base64).decode("utf-8-sig")[:120000]
        except UnicodeError: pass
    prompt = """You are an ontology analyst. Return JSON only: {\"classes\":[{\"name\":\"ASCII_identifier\",\"title\":\"Chinese name\",\"evidence\":\"short source location\",\"fields\":[{\"name\":\"ASCII_identifier\",\"title\":\"field name\",\"range\":\"string|integer|decimal|float|double|boolean|date|datetime|uriorcurie\",\"required\":false,\"multivalued\":false,\"description\":\"short\",\"evidence\":\"short source location\"}]}]}. Return 1 to 30 classes and at most 120 fields total. Never return an empty classes array: if the document is too unstructured, return one cautious Document class with a summary string field. Infer cautiously; do not invent business facts, executable rules, SQL, or identifiers.\n\nDocument context:\n""" + json.dumps(context, ensure_ascii=False)
    output = _json_content(_chat(model, [{"role": "system", "content": "You produce bounded LinkML candidate structures, not executable code."}, {"role": "user", "content": prompt}], 3000))
    try:
        values = output.get("classes", []) if isinstance(output, dict) else []
        classes = [CandidateClass.model_validate(value).model_dump() for value in values]
    except Exception:
        classes = []
    if not classes or len(classes) > 30 or sum(len(value["fields"]) for value in classes) > 120:
        local_result.setdefault("warnings", []).insert(0, f"LLM“{model['title']}”未返回可用范围内的候选，已保留本地预处理候选；可手动补充后生成草稿。")
        local_result["analysis"] = "llm_fallback"
        local_result["llm_id"] = model["id"]
        return local_result
    local_result["classes"] = classes
    local_result.setdefault("warnings", []).insert(0, f"候选由已配置 LLM“{model['title']}”分析生成；请逐项审核后再生成 LinkML 草稿。")
    local_result["analysis"] = "llm"
    local_result["llm_id"] = model["id"]
    return local_result


def classify_analytics_question(db, settings, question: str, *, mode: str, catalog: dict):
    """Ask an LLM only for a bounded query plan; it can never supply SQL or identifiers."""
    if mode not in {"governed", "explore"}:
        raise LLMError("不支持的问答模式。")
    model = _model(db, settings)
    prompt = """You classify a Chinese business question into a bounded analytics plan. Return JSON only with exactly these keys:
{"metric_code":"sales_amount|quantity_sold","dimension":"month|product|category|customer|channel|promotion|null","year":"YYYY|null","limit":1..100,"confidence":0..1,"reason":"short Chinese explanation"}.
Never return SQL, table names, column names, formulas, filters, or prose outside JSON. Select only from the supplied catalog. If the question requests a metric not in the catalog, return the closest metric only when it is unambiguous; otherwise set confidence below 0.70.

Catalog:\n""" + json.dumps(catalog, ensure_ascii=False) + "\n\nQuestion:\n" + question
    value = _json_content(_chat(model, [{"role": "system", "content": "You produce only bounded query plans, never executable code or SQL."}, {"role": "user", "content": prompt}], 300))
    if not isinstance(value, dict) or set(value) != {"metric_code", "dimension", "year", "limit", "confidence", "reason"}:
        raise LLMError("LLM 问答路由未返回受限计划。")
    metrics = {item["code"] for item in catalog["metrics"]}
    dimensions = {None, "month", "product", "category", "customer", "channel", "promotion"}
    metric, dimension, year, limit, confidence = value["metric_code"], value["dimension"], value["year"], value["limit"], value["confidence"]
    if metric not in metrics or dimension not in dimensions or (year is not None and (not isinstance(year, str) or not re.fullmatch(r"(?:19|20)\d{2}", year))) or isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100 or isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1 or not isinstance(value["reason"], str) or len(value["reason"]) > 240:
        raise LLMError("LLM 问答路由返回了范围外的计划。")
    if confidence < 0.70:
        raise LLMError("LLM 对该问题的指标匹配置信度不足。")
    return {"metric_codes": [metric], "dimension": dimension, "period": _analytics_period(year), "limit": limit,
            "resolution": f"LLM“{model['title']}”受限意图识别：{value['reason']}"}


def summarize_analytics_result(db, settings, result: dict):
    """Narrate a bounded aggregate result. The prompt excludes SQL, credentials, and raw source rows."""
    model = _model(db, settings)
    context = {
        "metric": result.get("metric"), "parameters": result.get("parameters"),
        "columns": result.get("columns"), "rows": (result.get("rows") or [])[:30],
        "lineage_mode": (result.get("lineage") or {}).get("mode"),
    }
    prompt = """You explain a controlled Chinese analytics result. Return JSON only with exactly:
{"answer":"one concise Chinese paragraph grounded only in supplied rows and metric definition","highlights":["up to three concise factual observations"]}.
Do not invent reasons, trends, currency conversion, missing values, SQL, tables, or recommendations. If there are no rows, say so. Use the stated metric and parameters exactly.

Result:\n""" + json.dumps(context, ensure_ascii=False, default=str)
    value = _json_content(_chat(model, [{"role": "system", "content": "You summarize bounded analytics results without adding facts."}, {"role": "user", "content": prompt}], 500))
    if not isinstance(value, dict) or set(value) != {"answer", "highlights"} or not isinstance(value["answer"], str) or not 1 <= len(value["answer"]) <= 1000 or not isinstance(value["highlights"], list) or len(value["highlights"]) > 3 or not all(isinstance(item, str) and 1 <= len(item) <= 300 for item in value["highlights"]):
        raise LLMError("LLM 未返回受限的结果解读。")
    return {"answer": value["answer"], "highlights": value["highlights"], "model": model["title"]}


def _analytics_period(year):
    if year is None: return None
    from .analytics import period_from_year
    return period_from_year(year)
