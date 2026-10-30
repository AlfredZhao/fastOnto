from contextlib import asynccontextmanager
from typing import Literal
from uuid import UUID

import oracledb
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import repository
from .config import ROOT, Settings
from .database import Database, DatabaseUnavailable
from .modeling import InvalidModel, parse_model
from .document_import import DocumentInput, DraftInput, MAX_REQUEST, inspect_document, generate_draft
from .sources import SOURCES, preview, source_catalog
from .graph import products as graph_products
from . import governance
from . import business_sources
from . import llm
from . import analytics
from .auth import AuthService, require_user, router as auth_router
from .auth_store import OracleAuthStore
from urllib.parse import urlsplit


class ModelInput(BaseModel):
    source: str = Field(min_length=1, max_length=65536)


class ModelSave(ModelInput):
    id: UUID | None = None
    expected_revision: int = Field(0, ge=0)


class WorkspaceInput(BaseModel):
    code: str = Field(max_length=80)
    title: str = Field(max_length=200)
    description: str = Field(default="", max_length=1000)


class DomainInput(WorkspaceInput):
    pass


class OntologyInput(WorkspaceInput):
    domain_id: UUID


class MappingInput(WorkspaceInput):
    ontology_id: UUID
    source_code: str | None = Field(default=None, max_length=80)
    source_id: UUID | None = None
    source_object_name: str | None = Field(default=None, max_length=128)
    mapping_kind: Literal["R2RML_DRAFT", "VIEW_R2RML_DRAFT"]
    definition: dict


class EntityLinkInput(WorkspaceInput):
    ontology_id: UUID
    left_mapping_id: UUID
    right_mapping_id: UUID
    definition: dict


class SemanticAssetInput(WorkspaceInput):
    ontology_id: UUID
    asset_kind: Literal["RULE", "METRIC", "ACTION"]
    definition: dict


class AnalyticsQuery(BaseModel):
    metric_code: str = Field(min_length=1, max_length=80)
    dimension: Literal["month", "product", "category", "customer", "channel", "promotion"] | None = None
    year: str | None = Field(default=None, max_length=4)
    period: Literal["CURRENT_WEEK", "CURRENT_MONTH", "CURRENT_QUARTER", "CURRENT_YEAR", "PREVIOUS_WEEK", "PREVIOUS_MONTH", "PREVIOUS_QUARTER", "PREVIOUS_YEAR"] | None = None
    limit: int = Field(default=20, ge=1, le=100)


class AnalyticsQuestion(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    mode: Literal["governed", "explore"] = "governed"


class PresentationInput(BaseModel):
    order: Literal["LAST_FIRST", "FIRST_LAST"]
    separator: str = Field(default="", max_length=10)


class OntologyModelInput(BaseModel):
    model_id: UUID
    model_revision: int = Field(ge=1)


class BusinessSourceInput(BaseModel):
    domain_id: UUID
    code: str = Field(max_length=128)
    title: str = Field(max_length=200)
    owner_schema: str = Field(max_length=128)
    dsn: str = Field(min_length=1, max_length=1000)
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=1000)


class BusinessSourceUpdate(BaseModel):
    title: str = Field(max_length=200)
    owner_schema: str = Field(max_length=128)
    dsn: str = Field(min_length=1, max_length=1000)
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=1000)


class LLMModelInput(BaseModel):
    code: str = Field(max_length=80)
    title: str = Field(max_length=200)
    base_url: str = Field(max_length=1000)
    model_name: str = Field(max_length=200)
    api_key: str = Field(min_length=1, max_length=1000)
    make_default: bool = True


def create_app(settings: Settings | None = None, *, auth_store=None):
    settings = settings or Settings()
    db = Database(settings)

    @asynccontextmanager
    async def lifespan(app):
        yield
        db.close()

    app = FastAPI(title="fastOnto", version="0.2.0", lifespan=lifespan,
                  dependencies=[Depends(require_user)], docs_url=None,redoc_url=None,openapi_url=None)
    app.state.database = db
    app.state.auth = AuthService(auth_store if auth_store is not None else OracleAuthStore(db),settings)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "testserver", urlsplit(settings.public_origin).hostname])
    app.include_router(auth_router)

    @app.middleware("http")
    async def local_boundary(request: Request, call_next):
        origin = request.headers.get("origin")
        if (origin and origin not in settings.allowed_origins) or (request.method not in {"GET","HEAD","OPTIONS"} and not origin):
            return JSONResponse({"detail": "请求来源不在允许范围内。", "code": "origin_denied"}, status_code=403)
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                bound = (8192 if request.url.path.startswith('/api/auth/') else
                         MAX_REQUEST if request.url.path == '/api/models/import' else 131072)
                if len(body) > bound:
                    return JSONResponse({"detail": "请求体超过允许大小。"}, status_code=413)
            request._body = bytes(body)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.exception_handler(RequestValidationError)
    async def request_error(request,exc):
        # Never echo password fields (Pydantic's default includes invalid input values).
        return JSONResponse({"detail": "请求参数不符合要求，请检查必填字段和长度。", "code": "invalid_request"},status_code=422)

    @app.exception_handler(DatabaseUnavailable)
    async def unavailable(request, exc):
        return JSONResponse({"detail": str(exc), "code": "database_unavailable"}, status_code=503)

    @app.exception_handler(oracledb.Error)
    async def oracle_error(request, exc):
        # Do not return DSN, SQL text, credentials, or raw Oracle exceptions.
        return JSONResponse({"detail": "数据库操作失败，请检查连接、迁移状态或稍后重试。", "code": "database_error"}, status_code=503)

    @app.exception_handler(InvalidModel)
    async def model_error(request, exc):
        return JSONResponse({"detail": str(exc), "code": "invalid_model"}, status_code=422)

    @app.exception_handler(governance.GovernanceError)
    async def governance_error(request, exc):
        return JSONResponse({"detail": str(exc), "code": "invalid_governance_asset"}, status_code=422)

    @app.exception_handler(business_sources.BusinessSourceError)
    async def source_error(request, exc):
        return JSONResponse({"detail": str(exc), "code": "invalid_business_source"}, status_code=422)

    @app.exception_handler(llm.LLMError)
    async def llm_error(request, exc):
        return JSONResponse({"detail": str(exc), "code": "invalid_llm"}, status_code=422)

    @app.exception_handler(analytics.AnalyticsError)
    async def analytics_error(request, exc):
        return JSONResponse({"detail": str(exc), "code": "invalid_analytics_request"}, status_code=422)

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/system")
    def system_info():
        return {"status": "ok", "mode": "authenticated", "database_configured": settings.database_configured,
                "source_policy": "SH-readonly-no-copy", "version": "0.2.0", "insecure_http": not settings.secure_cookie}

    @app.get("/api/database/status")
    def database_status():
        with db.connection() as conn, conn.cursor() as cursor:
            cursor.execute("select sys_context('USERENV','SESSION_USER'), sys_context('USERENV','CON_NAME') from dual")
            user, container = cursor.fetchone()
            cursor.execute("select count(*) from user_tables where table_name in ('FO_MODELS','FO_MODEL_VERSIONS')")
            metadata = cursor.fetchone()[0] == 2
            cursor.execute("select count(*) from user_tables where table_name='FO_NET#RDF_PARAMETER'")
            network = cursor.fetchone()[0] == 1
            cursor.execute("select count(*) from SH.PRODUCTS")
            product_count = cursor.fetchone()[0]
        return {"status": "connected", "user": user, "container": container,
                "metadata_ready": metadata, "rdf_network_ready": network, "source_product_count": product_count,
                "notice": "连接检查不等于虚拟图查询验收；请运行 db/verification/001_virtual_rdf.sql。"}

    @app.get("/api/models/template")
    def template(name: Literal["sales", "standards", "blank"] = "sales"):
        filenames = {"sales": "sales.yaml", "standards": "standards-tutorial.yaml", "blank": "blank.yaml"}
        source = (ROOT / "models" / filenames[name]).read_text(encoding="utf-8")
        return {"source": source, "saved": False, "origin": "bundled-example"}

    @app.post("/api/models/import")
    def import_document(payload: DocumentInput):
        result = inspect_document(payload)
        return llm.analyze_document(db, settings, payload, result)

    @app.post("/api/models/draft")
    def draft(payload: DraftInput):
        return generate_draft(payload)

    @app.post("/api/models/validate")
    def validate(payload: ModelInput):
        return parse_model(payload.source)[1]

    @app.post("/api/models/export/{format}")
    def export(format: Literal["jsonschema", "owl", "shacl"], payload: ModelInput):
        schema, report = parse_model(payload.source)
        if format == "jsonschema":
            from linkml.generators.jsonschemagen import JsonSchemaGenerator
            content = JsonSchemaGenerator(schema).serialize()
        elif format == "owl":
            from linkml.generators.owlgen import OwlSchemaGenerator
            content = OwlSchemaGenerator(
                schema, metaclasses=False, type_objects=False,
                skip_vacuous_min_zero_cardinality_axioms=True,
                skip_vacuous_local_range_axioms=True, consolidate_cardinality_axioms=True,
            ).serialize()
        else:
            from linkml.generators.shaclgen import ShaclGenerator
            content = ShaclGenerator(schema).serialize()
        return {"format": format, "content": content, "sha256": report["sha256"],
                "notice": "生成产物不保证覆盖所有目标语言语义；源码仍是唯一模型主源。"}

    @app.get("/api/models")
    def models():
        return {"items": repository.list_models(db)}

    @app.get("/api/models/{model_id}")
    def model(model_id: UUID):
        result = repository.get_model(db, str(model_id))
        if result is None:
            raise HTTPException(404, "模型不存在。")
        return result

    @app.post("/api/models")
    def save(payload: ModelSave):
        _, report = parse_model(payload.source)
        try:
            return repository.save_model(db, payload.source, report["title"], report["sha256"],
                                         str(payload.id) if payload.id else None, payload.expected_revision)
        except repository.RevisionConflict:
            raise HTTPException(409, "模型版本已变化或不存在。请保留草稿，重新加载并比较；不会覆盖服务端版本。")

    @app.get("/api/sources")
    def sources():
        return {"items": source_catalog(), "mode": "configured-catalog", "live_verified": False}

    def require_source_tls():
        if not settings.secure_cookie:
            raise HTTPException(403, "业务数据源凭据仅允许通过 HTTPS 配置；当前临时 HTTP 环境不能提交或修改凭据。")
        if not settings.source_master_key_configured:
            raise HTTPException(503, "本机未配置有效的 FASTONTO_SOURCE_MASTER_KEY，不能保存业务数据源凭据。")

    def require_llm_tls():
        if not settings.secure_cookie:
            raise HTTPException(403, "LLM 配置与文档分析仅允许通过 HTTPS。")

    @app.get("/api/llm-models")
    def llm_models():
        return {"items": llm.list_models(db), "credential_storage": "encrypted-database", "https_required": True}

    @app.post("/api/llm-models")
    def create_llm_model(payload: LLMModelInput):
        require_llm_tls()
        return llm.create_model(db, settings, payload.code, payload.title, payload.base_url, payload.model_name, payload.api_key, payload.make_default)

    @app.put("/api/llm-models/{llm_id}/default")
    def set_default_llm_model(llm_id: UUID):
        require_llm_tls()
        return llm.set_default(db, str(llm_id))

    @app.post("/api/llm-models/{llm_id}/test")
    def test_llm_model(llm_id: UUID):
        require_llm_tls()
        return llm.test_model(db, settings, str(llm_id))

    @app.get("/api/business-sources")
    def business_source_catalog():
        return {"items": business_sources.list_sources(db), "credential_storage": "encrypted-database", "readonly": True}

    @app.post("/api/business-sources")
    def create_business_source(payload: BusinessSourceInput):
        require_source_tls()
        return business_sources.create_source(db, settings, str(payload.domain_id), payload.code, payload.title, payload.owner_schema, payload.dsn, payload.username, payload.password)

    @app.put("/api/business-sources/{source_id}")
    def update_business_source(source_id: UUID, payload: BusinessSourceUpdate):
        require_source_tls()
        return business_sources.update_source(db, settings, str(source_id), payload.title, payload.owner_schema, payload.dsn, payload.username, payload.password)

    @app.post("/api/business-sources/{source_id}/discover")
    def discover_business_source(source_id: UUID):
        require_source_tls()
        return business_sources.discover(db, settings, str(source_id))

    @app.get("/api/business-sources/{source_id}/objects/{object_name}/metadata")
    def business_source_metadata(source_id: UUID, object_name: str):
        require_source_tls()
        return business_sources.metadata(db, settings, str(source_id), object_name)

    @app.get("/api/business-sources/{source_id}/objects/{object_name}/preview")
    def business_source_preview(source_id: UUID, object_name: str, offset: int = Query(0, ge=0, le=10000), limit: int = Query(20, ge=1, le=100)):
        require_source_tls()
        return business_sources.preview(db, settings, str(source_id), object_name, offset, limit)

    @app.post("/api/business-sources/{source_id}/objects/{object_name}/draft")
    def business_source_draft(source_id: UUID, object_name: str):
        require_source_tls()
        return business_sources.draft(db, settings, str(source_id), object_name)

    @app.get("/api/governance/catalog")
    def governance_catalog():
        return governance.catalog(db)

    @app.post("/api/governance/domains")
    def governance_domain(payload: DomainInput):
        return governance.create_domain(db, payload.code, payload.title, payload.description)

    @app.post("/api/governance/ontologies")
    def governance_ontology(payload: OntologyInput):
        return governance.create_ontology(db, str(payload.domain_id), payload.code, payload.title, payload.description)

    @app.post("/api/governance/mappings")
    def governance_mapping(payload: MappingInput):
        if payload.source_id is not None:
            require_source_tls()
        return governance.create_mapping(db, settings, str(payload.ontology_id), payload.code, payload.title, payload.mapping_kind, payload.definition, source_code=payload.source_code, source_id=str(payload.source_id) if payload.source_id else None, source_object_name=payload.source_object_name)

    @app.post("/api/governance/entity-links")
    def governance_entity_link(payload: EntityLinkInput):
        return governance.create_entity_link(db, str(payload.ontology_id), payload.code, payload.title,
                                             str(payload.left_mapping_id), str(payload.right_mapping_id), payload.definition)

    @app.put("/api/governance/ontologies/{ontology_id}/model")
    def governance_ontology_model(ontology_id: UUID, payload: OntologyModelInput):
        return governance.attach_model(db, str(ontology_id), str(payload.model_id), payload.model_revision)

    @app.post("/api/governance/assets")
    def governance_asset(payload: SemanticAssetInput):
        return governance.create_semantic_asset(db, str(payload.ontology_id), payload.asset_kind, payload.code, payload.title, payload.description, payload.definition)

    @app.get("/api/analytics/catalog")
    def analytics_catalog():
        return {"scenarios": analytics.scenario_catalog(), "metrics": analytics.metric_catalog(),
                "notice": "仅暴露审阅过的 SH 聚合指标；不接受用户或 LLM 提供的 SQL。"}

    @app.get("/api/analytics/presentations")
    def analytics_presentations():
        return analytics.presentations(db)

    @app.put("/api/analytics/presentations/{dimension}")
    def save_analytics_presentation(dimension: str, payload: PresentationInput):
        return analytics.save_presentation(db, dimension, payload.model_dump())

    @app.post("/api/analytics/query")
    def analytics_query(payload: AnalyticsQuery):
        return analytics.execute(db, payload.metric_code, dimension=payload.dimension, year=payload.year, period=analytics.period_from_selector(payload.period) if payload.period else None, limit=payload.limit, presentations=analytics.presentations(db))

    @app.post("/api/analytics/ask")
    def analytics_ask(payload: AnalyticsQuestion):
        resolved = analytics.resolve_with_llm(db, settings, payload.question, mode=payload.mode, classifier=llm.classify_analytics_question)
        items = analytics.execute_many(db, resolved["metric_codes"], dimension=resolved["dimension"], period=resolved["period"], limit=resolved["limit"], mode=payload.mode, presentations=analytics.presentations(db))
        result = {**items[0], "question": payload.question, "resolution": resolved["resolution"], "items": items}
        if resolved["resolution"].startswith("LLM") and len(items) == 1:
            try: result["narrative"] = llm.summarize_analytics_result(db, settings, items[0])
            except llm.LLMError: result["narrative"] = analytics.fallback_answers(items)
        else:
            result["narrative"] = analytics.fallback_answers(items)
        return result

    @app.get("/api/graph/products")
    def virtual_products():
        return graph_products(db)

    @app.get("/api/sources/{name}/preview")
    def source_preview(name: str, offset: int = Query(0, ge=0, le=10000), limit: int = Query(20, ge=1, le=100)):
        if name not in SOURCES:
            raise HTTPException(404, "数据源不在只读白名单内。")
        return preview(db, name, offset, limit)

    return app


app = create_app()
