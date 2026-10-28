"""Version-safe governance metadata. Definitions are declarative records, never executable SQL/SPARQL."""
import json
import re
import uuid

import oracledb

from .database import Database
from .modeling import parse_model
from .sources import SOURCES
from . import business_sources

CODE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,79}$")
SOURCE_CODES = set(SOURCES)
DEFAULT_WORKSPACE_ID = "00000000-0000-0000-0000-000000000005"
LIFECYCLES = {"workspace": {"ACTIVE", "ARCHIVED"}, "ontology": {"DRAFT", "PUBLISHED", "DEPRECATED"},
              "mapping": {"DRAFT", "RETIRED"}, "asset": {"DRAFT", "PUBLISHED", "RETIRED"}}


class GovernanceError(ValueError):
    pass


def _id(): return str(uuid.uuid4())


def _required(value: str, field: str, limit: int = 200):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise GovernanceError(f"{field} 必须是 1 至 {limit} 字符的文本。")
    return value.strip()


def _code(value: str):
    if not isinstance(value, str) or not CODE.fullmatch(value):
        raise GovernanceError("技术标识只能包含 ASCII 字母、数字和下划线，且不能以数字开头。")
    return value


def _definition(value):
    if not isinstance(value, dict) or len(json.dumps(value, ensure_ascii=False).encode()) > 32768:
        raise GovernanceError("定义必须是最多 32 KiB 的 JSON 对象。")
    # It is intentionally data-only: no SQL, SPARQL, scripts, or generated code are accepted here.
    forbidden = {"sql", "sparql", "script", "command", "expression"}
    def visit(item):
        if isinstance(item, dict):
            if forbidden & set(item):
                raise GovernanceError("首版定义不能包含可执行 SQL、SPARQL、脚本或表达式字段。")
            for child in item.values(): visit(child)
        elif isinstance(item, list):
            for child in item: visit(child)
    visit(value)
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _text(value):
    return value.read() if hasattr(value, "read") else value


def validate_mapping_definition(definition, source_code, report, *, source_columns=None):
    """Accept only column-to-term mappings; joins, expressions, and raw R2RML wait for reviewed publishing."""
    _definition(definition)
    if set(definition) != {"version", "class", "subject", "properties"} or definition.get("version") != 1:
        raise GovernanceError("映射定义必须包含 version=1、class、subject 和 properties。")
    classes = {item["name"]: item for item in report["classes"]}
    cls = classes.get(definition.get("class"))
    if cls is None: raise GovernanceError("映射类不在关联的 LinkML 模型中。")
    if source_columns is None:
        if source_code not in SOURCE_CODES: raise GovernanceError("数据源必须来自当前 SH 只读白名单。")
        source_columns = SOURCES[source_code].columns
    source_columns = set(source_columns)
    subject = definition.get("subject")
    if not isinstance(subject, dict) or set(subject) != {"column", "iri_template"}:
        raise GovernanceError("subject 必须只包含 column 和 iri_template。")
    column = subject.get("column")
    template = subject.get("iri_template")
    if column not in source_columns or not isinstance(template, str) or len(template) > 1000 or f"{{{column}}}" not in template:
        raise GovernanceError("主体必须使用当前源表字段，并在 IRI 模板中引用该字段。")
    properties = definition.get("properties")
    if not isinstance(properties, list) or not properties or len(properties) > 100:
        raise GovernanceError("properties 必须是 1 至 100 项的映射列表。")
    slots = {slot["name"]: slot for slot in cls["slots"]}
    seen = set()
    for item in properties:
        if not isinstance(item, dict) or set(item) != {"property", "column"}:
            raise GovernanceError("每个属性映射只能包含 property 和 column。")
        prop, source_column = item.get("property"), item.get("column")
        if prop not in slots or source_column not in source_columns or prop in seen:
            raise GovernanceError("属性映射必须引用一次模型属性和当前源表字段。")
        if slots[prop]["range"] in classes:
            raise GovernanceError("首版映射只支持标量属性；对象关系请在后续关联映射中发布。")
        seen.add(prop)
    return {"class": cls["name"], "class_uri": cls["uri"], "source_columns": sorted(source_columns)}


def catalog(db: Database):
    with db.connection() as conn, conn.cursor() as c:
        c.execute("select domain_id,code,title,description,lifecycle from FO_DOMAINS order by title")
        domains = [dict(zip(("id", "code", "title", "description", "lifecycle"), map(_text, r))) for r in c]
        c.execute("select ontology_id,domain_id,code,title,description,lifecycle,model_id,model_revision from FO_ONTOLOGIES order by title")
        ontologies = [dict(zip(("id", "domain_id", "code", "title", "description", "lifecycle", "model_id", "model_revision"), map(_text, r))) for r in c]
        c.execute("select mapping_id,ontology_id,code,title,source_code,source_id,source_object_name,mapping_kind,lifecycle from FO_MAPPING_ASSETS order by title")
        mappings = [dict(zip(("id", "ontology_id", "code", "title", "source_code", "source_id", "source_object_name", "mapping_kind", "lifecycle"), map(_text, r))) for r in c]
        c.execute("select link_id,ontology_id,code,title,left_mapping_id,right_mapping_id,lifecycle from FO_ENTITY_LINK_ASSETS order by title")
        entity_links = [dict(zip(("id", "ontology_id", "code", "title", "left_mapping_id", "right_mapping_id", "lifecycle"), map(_text, r))) for r in c]
        c.execute("select asset_id,ontology_id,asset_kind,code,title,description,lifecycle from FO_SEMANTIC_ASSETS order by asset_kind,title")
        assets = [dict(zip(("id", "ontology_id", "asset_kind", "code", "title", "description", "lifecycle"), map(_text, r))) for r in c]
    return {"domains": domains, "ontologies": ontologies, "mappings": mappings, "entity_links": entity_links, "assets": assets,
            "notice": "一个业务域可绑定多个只读数据源；映射和跨源实体对齐均为未执行的声明式草稿。"}


def create_workspace(db: Database, code, title, description=""):
    item = (_id(), _code(code), _required(title, "工作空间名称"), description or None)
    with db.connection(readonly=False) as conn, conn.cursor() as c:
        c.execute("insert into FO_WORKSPACES(workspace_id,code,title,description) values(:id,:code,:title,:description)",
                  dict(zip(("id", "code", "title", "description"), item)))
        conn.commit()
    return {"id": item[0], "code": item[1], "title": item[2], "description": item[3], "lifecycle": "ACTIVE"}


def create_domain(db: Database, code, title, description=""):
    item = (_id(), DEFAULT_WORKSPACE_ID, _code(code), _required(title, "业务域名称"), description or None)
    with db.connection(readonly=False) as conn, conn.cursor() as c:
        c.execute("select count(*) from FO_WORKSPACES where workspace_id=:id and lifecycle='ACTIVE'", {"id": DEFAULT_WORKSPACE_ID})
        if c.fetchone()[0] != 1: raise GovernanceError("默认业务域范围不存在；请先执行迁移 005。")
        c.execute("insert into FO_DOMAINS(domain_id,workspace_id,code,title,description) values(:id,:workspace_id,:code,:title,:description)",
                  dict(zip(("id", "workspace_id", "code", "title", "description"), item)))
        conn.commit()
    return {"id": item[0], "workspace_id": item[1], "code": item[2], "title": item[3], "description": item[4], "lifecycle": "ACTIVE"}


def create_ontology(db: Database, domain_id, code, title, description=""):
    ontology_id = _id()
    with db.connection(readonly=False) as conn, conn.cursor() as c:
        c.execute("select workspace_id from FO_DOMAINS where domain_id=:domain_id and lifecycle='ACTIVE'", {"domain_id": domain_id})
        row = c.fetchone()
        if row is None: raise GovernanceError("业务域不存在或已归档。")
        workspace_id = row[0]
        item = (ontology_id, workspace_id, domain_id, _code(code), _required(title, "本体名称"), description or None)
        c.execute("insert into FO_ONTOLOGIES(ontology_id,workspace_id,domain_id,code,title,description) values(:id,:workspace_id,:domain_id,:code,:title,:description)",
                  dict(zip(("id", "workspace_id", "domain_id", "code", "title", "description"), item)))
        conn.commit()
    return {"id": item[0], "domain_id": item[2], "code": item[3], "title": item[4], "description": item[5], "lifecycle": "DRAFT", "model_id": None, "model_revision": None}


def attach_model(db: Database, ontology_id, model_id, model_revision):
    with db.connection(readonly=False) as conn, conn.cursor() as c:
        c.execute("select count(*) from FO_MODELS where model_id=:model_id and revision=:revision", {"model_id": model_id, "revision": model_revision})
        if c.fetchone()[0] != 1:
            raise GovernanceError("模型不存在，或指定的版本不是当前版本。请先保存 LinkML 模型。")
        c.execute("update FO_ONTOLOGIES set model_id=:model_id,model_revision=:revision,updated_at=systimestamp where ontology_id=:ontology_id", {"model_id": model_id, "revision": model_revision, "ontology_id": ontology_id})
        if c.rowcount != 1: raise GovernanceError("本体不存在。")
        conn.commit()
    return {"ontology_id": ontology_id, "model_id": model_id, "model_revision": model_revision,
            "notice": "已关联当前 LinkML 模型版本；发布及映射执行仍需后续审核流程。"}


def create_mapping(db: Database, settings, ontology_id, code, title, mapping_kind, definition, *, source_code=None, source_id=None, source_object_name=None):
    if mapping_kind not in {"R2RML_DRAFT", "VIEW_R2RML_DRAFT"}: raise GovernanceError("不支持的映射类型。")
    legacy = bool(source_code)
    external = bool(source_id or source_object_name)
    if legacy == external or (external and not (source_id and source_object_name)):
        raise GovernanceError("映射必须且只能选择一个 SH 白名单源，或一个业务数据源表/视图。")
    with db.connection(readonly=False) as conn, conn.cursor() as c:
        c.execute("select domain_id,model_id,model_revision from FO_ONTOLOGIES where ontology_id=:id", {"id": ontology_id})
        ontology = c.fetchone()
        if ontology is None: raise GovernanceError("本体不存在。")
        if not ontology[1]: raise GovernanceError("请先为本体关联一个已保存的 LinkML 模型版本。")
        c.execute("select source_yaml,revision from FO_MODELS where model_id=:id", {"id": ontology[1]})
        model = c.fetchone()
        if model is None or model[1] != ontology[2]: raise GovernanceError("关联模型版本已不存在或不再是当前版本；请重新关联。")
        source = _text(model[0])
        _, report = parse_model(source)
        if legacy:
            if source_code not in SOURCE_CODES: raise GovernanceError("数据源必须来自当前 SH 只读白名单。")
            validate_mapping_definition(definition, source_code, report)
            bound_source_id, object_name, stored_source_code = None, None, source_code
        else:
            c.execute("select domain_id,enabled from FO_BUSINESS_SOURCES where source_id=:id", {"id": source_id})
            row = c.fetchone()
            if row is None or not row[1]: raise GovernanceError("业务数据源不存在或已停用。")
            if row[0] != ontology[0]: raise GovernanceError("业务数据源必须与本体位于同一业务域。")
            # Reads only trusted dictionary metadata under the saved source credential; no business rows or user SQL.
            metadata = business_sources.metadata(db, settings, source_id, source_object_name)
            validate_mapping_definition(definition, None, report, source_columns=[item["name"] for item in metadata["columns"]])
            bound_source_id, object_name, stored_source_code = source_id, metadata["name"], "BUSINESS_SOURCE"
        item = (_id(), ontology_id, _code(code), _required(title, "映射名称"), stored_source_code, bound_source_id, object_name, mapping_kind, _definition(definition))
        c.setinputsizes(definition=oracledb.DB_TYPE_CLOB)
        c.execute("insert into FO_MAPPING_ASSETS(mapping_id,ontology_id,code,title,source_code,source_id,source_object_name,mapping_kind,definition_json) values(:id,:ontology_id,:code,:title,:source_code,:source_id,:source_object_name,:mapping_kind,:definition)",
                  dict(zip(("id", "ontology_id", "code", "title", "source_code", "source_id", "source_object_name", "mapping_kind", "definition"), item)))
        conn.commit()
    return {"id": item[0], "ontology_id": ontology_id, "code": item[2], "title": item[3], "source_code": source_code,
            "source_id": bound_source_id, "source_object_name": object_name, "mapping_kind": mapping_kind, "lifecycle": "DRAFT"}


def create_entity_link(db: Database, ontology_id, code, title, left_mapping_id, right_mapping_id, definition):
    _definition(definition)
    if set(definition) != {"version", "kind", "left_key", "right_key"} or definition.get("version") != 1 or definition.get("kind") != "IDENTITY":
        raise GovernanceError("实体对齐定义必须只包含 version=1、kind=IDENTITY、left_key 和 right_key。")
    if not all(isinstance(definition[key], str) and CODE.fullmatch(definition[key]) for key in ("left_key", "right_key")):
        raise GovernanceError("实体对齐键必须是已映射的源字段名。")
    with db.connection(readonly=False) as conn, conn.cursor() as c:
        c.execute("select mapping_id,definition_json from FO_MAPPING_ASSETS where ontology_id=:ontology_id and mapping_id in (:left_id,:right_id)", {"ontology_id": ontology_id, "left_id": left_mapping_id, "right_id": right_mapping_id})
        mappings = {row[0]: json.loads(_text(row[1])) for row in c}
        if left_mapping_id == right_mapping_id or set(mappings) != {left_mapping_id, right_mapping_id}:
            raise GovernanceError("实体对齐必须引用同一本体下两个不同的映射草稿。")
        def mapped_columns(value):
            return {value["subject"]["column"]} | {item["column"] for item in value["properties"]}
        if definition["left_key"] not in mapped_columns(mappings[left_mapping_id]) or definition["right_key"] not in mapped_columns(mappings[right_mapping_id]):
            raise GovernanceError("实体对齐键必须已在对应映射草稿中使用。")
        item = (_id(), ontology_id, _code(code), _required(title, "实体对齐名称"), left_mapping_id, right_mapping_id, _definition(definition))
        c.setinputsizes(definition=oracledb.DB_TYPE_CLOB)
        c.execute("insert into FO_ENTITY_LINK_ASSETS(link_id,ontology_id,code,title,left_mapping_id,right_mapping_id,definition_json) values(:id,:ontology_id,:code,:title,:left_mapping_id,:right_mapping_id,:definition)",
                  dict(zip(("id", "ontology_id", "code", "title", "left_mapping_id", "right_mapping_id", "definition"), item)))
        conn.commit()
    return {"id": item[0], "ontology_id": ontology_id, "code": item[2], "title": item[3], "left_mapping_id": left_mapping_id, "right_mapping_id": right_mapping_id, "lifecycle": "DRAFT"}


def create_semantic_asset(db: Database, ontology_id, asset_kind, code, title, description, definition):
    if asset_kind not in {"RULE", "METRIC", "ACTION"}: raise GovernanceError("资产类型必须是 RULE、METRIC 或 ACTION。")
    item = (_id(), ontology_id, asset_kind, _code(code), _required(title, "资产名称"), description or None, _definition(definition))
    with db.connection(readonly=False) as conn, conn.cursor() as c:
        c.setinputsizes(definition=oracledb.DB_TYPE_CLOB)
        c.execute("insert into FO_SEMANTIC_ASSETS(asset_id,ontology_id,asset_kind,code,title,description,definition_json) values(:id,:ontology_id,:asset_kind,:code,:title,:description,:definition)",
                  dict(zip(("id", "ontology_id", "asset_kind", "code", "title", "description", "definition"), item)))
        conn.commit()
    return {"id": item[0], "ontology_id": ontology_id, "asset_kind": asset_kind, "code": item[3], "title": item[4], "description": item[5], "lifecycle": "DRAFT"}
