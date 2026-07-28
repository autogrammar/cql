"""FastAPI app exposing the CQL/DSL runtime as REST endpoints.

Mounts every route under ``/api/cql`` so the cql nginx image (which already
proxies ``/api/*`` to the backend) can forward traffic without changes.

Endpoint maturity:
    - ``/api/cql/quote`` / ``unquote`` / ``format-literal``
      → full Python ports of ``runtime/dsl.quotes.ts``.
    - ``/api/cql/canonicalize`` / ``normalize``
      → full ports.
    - ``/api/cql/highlight``
      → partial port (keyword/string/number/comment highlighting). Good
      enough for protocol view read-only rendering.
    - ``/api/cql/parse`` / ``serialize`` / ``validate`` / ``exec`` /
      ``scenario-build`` → ``501 Not Implemented`` stubs with a clear
      follow-up task note. Callers receive a structured error so they can
      detect the missing capability at runtime.
"""

from __future__ import annotations

import os
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .api_models import (
    AstIn,
    AstOnlyIn,
    ExecIn,
    HighlightIn,
    QuotedTokenIn,
    ScenarioBuildIn,
    TextIn,
    ValueIn,
    XmlIn,
    XmlMigrateIn,
)
from .clients import maskservice_client
from .highlight import highlight_dsl
from .quotes import (
    canonicalize_dsl_quotes,
    format_dsl_literal,
    normalize_dsl_text_quotes,
    quote_dsl_value,
    read_quoted_token,
)
from .parser import parse_dsl
from .serializer import ast_to_dsl_text
from .validator import validate_dsl_format
from .exec_runtime import execute_dsl
from .scenario_builders import DslScenarioBuilders
from .schema import get_json_schema, validate_ast
from .migrate_xml import migrate_legacy_xml_to_dsl, split_legacy_xml_to_scenarios
from .validate_db import validate_dsl_text
from .xml_codec import ast_to_xml, dsl_to_xml, xml_to_ast
from .xsd import DSL_XSD
from .scenario_files import router as scenario_files_router


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Wire outbound HTTP clients to their env-configured upstream; close on exit."""
    maskservice_url = os.environ.get("MASKSERVICE_API_URL")
    if maskservice_url:
        maskservice_client.configure_maskservice_client(base_url=maskservice_url)
    try:
        yield
    finally:
        await maskservice_client.close_maskservice_client()


def _resolve_cors_origins() -> list[str]:
    defaults = [
        "http://localhost:8100",
        "http://identification.localhost:8100",
        "http://localhost:8091",
    ]
    raw = os.environ.get("CORS_ORIGINS", "").strip()
    if not raw:
        return defaults

    loaded: list[str] = []
    try:
        decoded = json.loads(raw)
        if isinstance(decoded, str):
            loaded = [decoded]
        elif isinstance(decoded, list):
            loaded = [str(item) for item in decoded]
    except json.JSONDecodeError:
        loaded = [item.strip() for item in raw.split(",") if item.strip()]

    if not loaded:
        return defaults
    if "*" in loaded:
        return defaults

    seen: set[str] = set()
    merged: list[str] = []
    for origin in [*defaults, *loaded]:
        value = origin.strip()
        if not value or value in seen:
            continue
        seen.add(value)
        merged.append(value)
    return merged


app = FastAPI(
    title="CQL Backend",
    description=(
        "Decoupled CQL/DSL runtime. Replaces the direct TypeScript imports "
        "from maskservice's components/dsl/ with HTTP endpoints."
    ),
    version=__version__,
    lifespan=_lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_resolve_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(scenario_files_router)


# ── Health / meta ──────────────────────────────────────────────────────


@app.get("/health", tags=["meta"])
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "cql-backend", "version": __version__}


@app.get("/health/full", tags=["meta"])
async def health_full() -> dict[str, object]:
    """Composite health report: this service + reachable neighbours.

    Reports the upstream maskservice backend status alongside our own so
    orchestration / dashboards can see the inter-backend link in a single
    roundtrip.
    """
    upstream: dict[str, object] = {
        "base_url": maskservice_client.get_maskservice_base_url(),
        "status": "unknown",
    }
    try:
        payload = await maskservice_client.health()
        upstream["status"] = "ok"
        upstream["payload"] = payload
    except maskservice_client.MaskserviceUnavailable as exc:
        upstream["status"] = "unreachable"
        upstream["error"] = str(exc)
    except maskservice_client.MaskserviceError as exc:  # pragma: no cover
        upstream["status"] = "error"
        upstream["error"] = str(exc)
    return {
        "self": {"status": "ok", "service": "cql-backend", "version": __version__},
        "maskservice": upstream,
    }


@app.get("/api/cql/scenarios/{scenario_id}", tags=["bridge"])
async def bridge_scenario(scenario_id: str) -> dict[str, object]:
    """Fetch a scenario record from maskservice backend by ID.

    Primarily used by the (still-stubbed) ``/api/cql/exec`` endpoint and
    by ad-hoc debugging. Returns a 404 when maskservice reports the same,
    503 on network failure.
    """
    try:
        record = await maskservice_client.fetch_scenario(scenario_id)
    except maskservice_client.MaskserviceUnavailable as exc:
        raise HTTPException(
            status_code=503, detail={"error": "maskservice unreachable", "detail": str(exc)}
        ) from exc
    except maskservice_client.MaskserviceError as exc:
        raise HTTPException(
            status_code=exc.status or 502,
            detail={"error": "maskservice error", "detail": exc.detail},
        ) from exc
    if record is None:
        raise HTTPException(
            status_code=404, detail={"error": "scenario not found", "id": scenario_id}
        )
    return {"source": "maskservice", "scenario": record}


@app.get("/api/cql/capabilities", tags=["meta"])
async def capabilities() -> dict[str, object]:
    """Report which endpoints are implemented vs stubbed.

    Frontend callers can use this to feature-detect before swapping a
    direct TS import for the remote call.
    """
    return {
        "implemented": [
            "/api/cql/quote",
            "/api/cql/unquote",
            "/api/cql/format-literal",
            "/api/cql/canonicalize",
            "/api/cql/normalize",
            "/api/cql/highlight",
            "/api/cql/parse",
            "/api/cql/serialize",
            "/api/cql/validate",
            "/api/cql/exec",
            "/api/cql/scenario-build",
            "/api/cql/xsd",
            "/api/cql/json-schema",
            "/api/cql/validate-ast",
            "/api/cql/dsl-to-xml",
            "/api/cql/ast-to-xml",
            "/api/cql/xml-to-ast",
            "/api/cql/validate-dsl-text",
            "/api/cql/xml-migrate",
            "/api/cql/xml-split",
        ],
        "stubbed_501": [],
    }


# ── Quotes / literals (full Python port) ────────────────────────────────


@app.post("/api/cql/quote", tags=["quotes"])
async def quote(payload: ValueIn) -> dict[str, str]:
    return {"quoted": quote_dsl_value(payload.value)}


@app.post("/api/cql/unquote", tags=["quotes"])
async def unquote(payload: QuotedTokenIn) -> dict[str, str]:
    return read_quoted_token(payload.token)


@app.post("/api/cql/format-literal", tags=["quotes"])
async def format_literal(payload: ValueIn) -> dict[str, str]:
    return {"literal": format_dsl_literal(payload.value)}


@app.post("/api/cql/canonicalize", tags=["quotes"])
async def canonicalize(payload: TextIn) -> dict[str, str]:
    return {"text": canonicalize_dsl_quotes(payload.text)}


@app.post("/api/cql/normalize", tags=["quotes"])
async def normalize(payload: TextIn) -> dict[str, str]:
    return {"text": normalize_dsl_text_quotes(payload.text)}


# ── Highlight (partial port; good enough for protocol view) ─────────────


@app.post("/api/cql/highlight", tags=["render"])
async def highlight(payload: HighlightIn) -> dict[str, str]:
    if payload.mode == "tokens":
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail={
                "message": "Token-stream highlight output is not yet ported.",
                "ts_reference": "oqlos/cql/runtime/dsl.highlight.ts",
                "tracking": "FOLLOW-UP in cql/backend/README.md",
            },
        )
    return {"html": highlight_dsl(payload.text)}


# ── Parser (full port) ──────────────────────────────────────────────────


@app.post("/api/cql/parse", tags=["runtime"])
async def parse_endpoint(payload: TextIn) -> dict[str, object]:
    """Parse DSL text into AST."""
    result = parse_dsl(payload.text)
    return {
        "ok": result.ok,
        "errors": result.errors,
        "ast": result.ast.model_dump(by_alias=True) if result.ast else None,
    }


# ── Serializer (full port) ────────────────────────────────────────────────


@app.post("/api/cql/serialize", tags=["runtime"])
async def serialize_endpoint(payload: AstIn) -> dict[str, str]:
    """Serialize DSL AST back to text."""
    return {"text": ast_to_dsl_text(payload.ast)}


# ── Validator (full port) ───────────────────────────────────────────────


@app.post("/api/cql/validate", tags=["runtime"])
async def validate_endpoint(payload: TextIn) -> dict[str, object]:
    """Validate DSL format and return errors/warnings with fix suggestions."""
    result = validate_dsl_format(payload.text)
    return {
        "ok": result.ok,
        "errors": result.errors,
        "warnings": result.warnings,
        "violations": [v.model_dump(by_alias=True) for v in result.violations],
        "fixedText": result.fixedText,
    }


# ── Exec (full port) ──────────────────────────────────────────────────────


@app.post("/api/cql/exec", tags=["runtime"])
async def exec_endpoint(payload: ExecIn) -> dict[str, object]:
    """Execute DSL and return execution plan.

    Note: The execution context (getParamValue, runTask) is not functional
    in the stateless HTTP endpoint - the plan shows what would execute.
    """
    result = execute_dsl(payload.text, payload.context)
    return {
        "ok": result.ok,
        "errors": result.errors,
        "ast": result.ast.model_dump(by_alias=True) if result.ast else None,
        "plan": result.plan,
    }


# ── Scenario Builders (full port) ────────────────────────────────────────


@app.post("/api/cql/scenario-build", tags=["runtime"])
async def scenario_build_endpoint(payload: ScenarioBuildIn) -> dict[str, object]:
    """Build DSL from scenario data.

    - source='test': Build from TestScenario (activities with criteria)
    - source='generic': Build from generic scenario structure
    """
    if payload.source == "test":
        dsl = DslScenarioBuilders.build_dsl_from_test_scenario(payload.data)
        goals = DslScenarioBuilders.build_goals_from_test_scenario(payload.data)
        return {"dsl": dsl, "goals": goals}
    else:
        dsl = DslScenarioBuilders.build_dsl_from_generic_scenario(payload.data)
        return {"dsl": dsl}


# ── Schema / XSD (full ports of dsl.schema.ts + dsl.xsd.ts) ─────────────


@app.get("/api/cql/xsd", tags=["schema"])
async def xsd_endpoint() -> dict[str, str]:
    """Return the static XSD describing the DSL XML representation.

    Mirrors `DslEngine.getXsd()` from `oqlos/cql/runtime/dsl.engine.ts`.
    """
    return {"xsd": DSL_XSD}


@app.get("/api/cql/json-schema", tags=["schema"])
async def json_schema_endpoint() -> dict[str, object]:
    """Return the DSL JSON Schema (draft-07).

    Mirrors `DslEngine.getJsonSchema()`.
    """
    return {"schema": get_json_schema()}


@app.post("/api/cql/validate-ast", tags=["schema"])
async def validate_ast_endpoint(payload: AstOnlyIn) -> dict[str, object]:
    """Validate a parsed DSL AST against the JSON Schema.

    Mirrors `DslEngine.validateAst(ast)`.
    """
    result = validate_ast(payload.ast)
    return {"ok": result["ok"], "errors": result["errors"]}


# ── XML codec (full port of dsl.xml.ts) ─────────────────────────


@app.post("/api/cql/dsl-to-xml", tags=["xml"])
async def dsl_to_xml_endpoint(payload: TextIn) -> dict[str, object]:
    """Parse DSL text and serialize the resulting AST as XML.

    Mirrors `DslEngine.toXml(text)`.
    """
    return dsl_to_xml(payload.text)


@app.post("/api/cql/ast-to-xml", tags=["xml"])
async def ast_to_xml_endpoint(payload: AstIn) -> dict[str, str]:
    """Render a DSL AST as canonical XML.

    Mirrors `DslEngine.astToXml(ast)`.
    """
    return {"xml": ast_to_xml(payload.ast)}


@app.post("/api/cql/xml-to-ast", tags=["xml"])
async def xml_to_ast_endpoint(payload: XmlIn) -> dict[str, object]:
    """Parse XML produced by `ast-to-xml` back into a DSL AST.

    Mirrors `DslEngine.xmlToAst(xml)`.
    """
    return xml_to_ast(payload.xml)


# ── Composite validation (port of dsl.validate.db.ts:validateDslText) ────


@app.post("/api/cql/validate-dsl-text", tags=["runtime"])
async def validate_dsl_text_endpoint(payload: TextIn) -> dict[str, object]:
    """Composite validation: normalize + format + parse + schema + XML.

    Mirrors `DslEngine.validateDslText(text)` from
    `oqlos/cql/runtime/dsl.engine.ts`.
    """
    return validate_dsl_text(payload.text)


# ── Legacy XML migration (port of dsl.migrate.xml.ts) ──────────────


@app.post("/api/cql/xml-migrate", tags=["xml"])
async def xml_migrate_endpoint(payload: XmlMigrateIn) -> dict[str, object]:
    """Convert any DSL-related XML (native or legacy report) into DSL text.

    Mirrors `DslEngine.migrateLegacyXmlToDsl(xml, nameHint)`.
    """
    return migrate_legacy_xml_to_dsl(payload.xml, payload.nameHint)


@app.post("/api/cql/xml-split", tags=["xml"])
async def xml_split_endpoint(payload: XmlMigrateIn) -> dict[str, object]:
    """Decode a multi-transaction legacy XML into one item per scenario.

    Mirrors `DslEngine.splitLegacyXmlToScenarios(xml, nameHint)`.
    """
    scenarios = split_legacy_xml_to_scenarios(payload.xml, payload.nameHint)
    return {"scenarios": scenarios, "count": len(scenarios)}
