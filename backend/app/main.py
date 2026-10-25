"""FastAPI entrypoint for SamadhaanOS — contract v1.0 (architecture.md section 8).

POST /evaluate-case runs the real engine (`backend.engine.evaluate`), which
assembles the response from the rule modules. The API layer owns the file reads,
the schema validation and the error envelope; it computes no legal number
itself (golden rule 6).
"""

import json
import os
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.app.config_loader import load_config, objection_window
from backend.app.schemas import (
    CONTRACT_VERSION,
    ArtifactGenerationRequest,
    ArtifactResponse,
    CaseEvaluationRequest,
    CaseEvaluationResponse,
    ErrorResponse,
    ExtractionResponse,
    SettlementSimulationRequest,
    SettlementSimulationResponse,
    Warning,
)
from backend.artifacts.generate import build_artifact
from backend.engine.config import ConfigError, StatuteConfig
from backend.engine.evaluate import evaluate_case as evaluate_case_engine
from backend.engine.settlement import evaluate_settlement
from backend.extraction.extract import extract_evidence as run_extraction
from backend.extraction.llm import settings_from_env
from backend.extraction.text import ExtractionInputError
from backend.app.schemas_v4 import component_schemas as v1_1_component_schemas

PRESETS_DIR = Path(__file__).resolve().parent.parent / "presets"

app = FastAPI(
    title="SamadhaanOS API",
    version=CONTRACT_VERSION,
    description=(
        "MSME payment-rights evaluation API. Contract v1.0; frozen and "
        "additive-only after the contract-v1 tag (architecture.md section 9). "
        "The v1.1 shapes for the v4 two-option model are published as "
        "unreferenced components until their routes land."
    ),
)


# ------------------------------------------------------ contract v1.1 ----
# The v1.1 schemas ship before their routes (architecture_v4 section 9). They
# are registered as components only, so `paths` is untouched and every v1.0
# operation stays byte-identical. A v1.1 model may never shadow a v1.0 name.

_BASE_OPENAPI = app.openapi


def _openapi_with_v1_1() -> dict:
    if app.openapi_schema is not None:
        return app.openapi_schema
    schema = _BASE_OPENAPI()
    components = schema.setdefault("components", {}).setdefault("schemas", {})
    v1_1, authored = v1_1_component_schemas()
    for name, sub in v1_1.items():
        if name in components:
            if name in authored:
                raise RuntimeError(
                    f"contract v1.1 schema {name!r} collides with the frozen v1.0 schema"
                )
            # A v1.0 model pulled in by reference: the frozen definition wins.
            continue
        components[name] = sub
    app.openapi_schema = schema
    return schema


app.openapi = _openapi_with_v1_1


# ------------------------------------------------------------- errors ----


def _error(code: str, message: str, status: int, field: str | None = None) -> JSONResponse:
    body = ErrorResponse(error={"code": code, "message": message, "field": field})
    return JSONResponse(status_code=status, content=body.model_dump())


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """HTTP 422 with the contract's error shape (section 8.1)."""
    errors = exc.errors()
    first = errors[0] if errors else {}
    loc = ".".join(str(p) for p in first.get("loc", []) if p != "body")
    return _error(
        code="VALIDATION_ERROR",
        message="Some fields in your request are missing or malformed.",
        status=422,
        field=loc or None,
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Reshape raised HTTPExceptions into the contract error shape (section 8.1)."""
    codes = {400: "RULE_VIOLATION", 404: "NOT_FOUND", 500: "INTERNAL_ERROR"}
    return _error(
        code=codes.get(exc.status_code, f"HTTP_{exc.status_code}"),
        message=str(exc.detail),
        status=exc.status_code,
    )


# ------------------------------------------------------------ routes ----


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    """Liveness plus config load status (section 8.1)."""
    cfg = load_config()
    return {
        "status": "ok",
        "contract_version": CONTRACT_VERSION,
        "config_load": "stub" if cfg.get("_stub") else "loaded",
    }


@app.get("/api/v1/config")
def get_config() -> dict:
    """The statute config with its verified flags, for the assumptions drawer.

    Returns a labelled stub when statute_config.json is absent so the offline
    demo still runs. No value here is treated as statutory by the API.
    """
    return load_config()


@app.get("/api/v1/presets")
def list_presets() -> dict:
    """List preset ids and titles (input-only files; section 8.1)."""
    items = []
    for path in sorted(PRESETS_DIR.glob("*.json")):
        data = _read_json(path)
        items.append({"id": path.stem, "title": data.get("title", path.stem)})
    return {"presets": items}


@app.get("/api/v1/presets/{preset_id}")
def get_preset(preset_id: str) -> dict:
    """Return a preset's request (input only). 404 if it does not exist."""
    if "/" in preset_id or "\\" in preset_id or ".." in preset_id:
        raise HTTPException(status_code=404, detail="Unknown preset")
    path = PRESETS_DIR / f"{preset_id}.json"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Unknown preset")
    data = _read_json(path)
    request = data.get("request", data)
    return {"id": preset_id, "title": data.get("title", preset_id), "request": request}


def _statute_config() -> StatuteConfig:
    """Load the statute config for one request; the API owns the file read.

    A config the loader cannot make sense of is a server-side problem, so it
    fails as 500 with the error envelope rather than blaming the caller.
    """
    try:
        return StatuteConfig.from_dict(load_config())
    except ConfigError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"The statute config could not be loaded: {exc}",
        ) from exc


def _run_engine(request: CaseEvaluationRequest) -> CaseEvaluationResponse:
    """Evaluate through the engine, mapping rule violations to 400 (section 8.1).

    A null statutory constant, an uncaptured Bank Rate epoch (CR-8) or an
    out-of-range figure means the rule cannot be applied — section 8.1's rule
    violation — and the engine's own plain-English message is what the caller
    reads, rather than an opaque 500.
    """
    try:
        return evaluate_case_engine(_statute_config(), request)
    except (ConfigError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/v1/evaluate-case", response_model=CaseEvaluationResponse)
def evaluate_case(request: CaseEvaluationRequest) -> CaseEvaluationResponse:
    """Evaluate a case with the real engine (sections 6.1-6.6)."""
    return _run_engine(request)


@app.post("/api/v1/simulate-settlement", response_model=SettlementSimulationResponse)
def simulate_settlement(payload: SettlementSimulationRequest) -> SettlementSimulationResponse:
    """Split a settlement offer against this case's own numbers (section 8.1).

    The claim is evaluated first, so the split always uses the engine's figures
    instead of numbers the client sends (golden rule 6). Nothing is combined
    with the buyer-cost lines, and nothing is assumed about time value.
    """
    evaluation = _run_engine(payload.request)
    if evaluation.financials is None:
        raise HTTPException(
            status_code=400,
            detail=(
                "This case has no computed claim to settle: the eligibility gate blocked "
                "it, or no appointed day fixes the due date yet. Resolve the case first "
                "and simulate again."
            ),
        )
    try:
        result = evaluate_settlement(
            principal_outstanding=evaluation.financials.principal_outstanding,
            interest_outstanding=evaluation.financials.interest_outstanding,
            upfront_pct=payload.upfront_pct,
            waiver_pct=payload.waiver_pct,
            days_to_second_payment=payload.days_to_second_payment,
        )
    except ValueError as exc:  # out-of-range percentages, negative amounts
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return SettlementSimulationResponse(contract_version=CONTRACT_VERSION, **result.to_dict())


@app.post("/api/v1/generate-artifact", response_model=ArtifactResponse)
def generate_artifact(payload: ArtifactGenerationRequest) -> ArtifactResponse:
    """Draft one artifact for this case (section 8.1).

    The case is evaluated first, so the draft is filled from the engine's own
    figures rather than from anything the client sends (golden rule 7). When the
    stage cannot be produced - the gate stopped the case, or a figure the draft
    needs was never computed - the response still carries markdown: an honest
    note saying why that stage is unavailable, never a half-filled document.
    Nothing is sent anywhere; the PDF is optional and its failure degrades to
    markdown plus a `warnings[]` entry rather than an error.
    """
    evaluation = _run_engine(payload.request)
    try:
        result = build_artifact(
            kind=payload.kind,
            request=payload.request,
            evaluation=evaluation,
            settlement=payload.settlement,
        )
    except (ConfigError, ValueError) as exc:  # out-of-range settlement terms
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ArtifactResponse(
        contract_version=CONTRACT_VERSION,
        kind=payload.kind,
        filename=result.filename,
        markdown=result.markdown,
        pdf_base64=result.pdf_base64,
        pdf_filename=result.pdf_filename,
        warnings=[Warning.model_validate(w) for w in result.warnings],
    )


_TRUTHY = {"1", "true", "yes", "on"}


@app.post("/api/v1/extract-evidence", response_model=ExtractionResponse)
async def extract_evidence(file: UploadFile = File(...)) -> ExtractionResponse:
    """Extract machine-suggested candidates from an uploaded text file (B9).

    Regex and keyword first, offline: a WhatsApp .txt export is parsed into
    messages and tagged, invoice and PO text yields labelled fields - each with
    a line citation and a confidence - and a human confirms them into a
    `CaseEvaluationRequest` before anything is evaluated (nothing here calls the
    engine, and the engine never calls this module).

    Environment flags, read per request and never at import time:

    - `EXTRACTION_DEMO_CACHE=1` returns the prepared result stored for that
      exact text, with no network at all.
    - `EXTRACTION_LLM=1` plus `EXTRACTION_LLM_URL` enables the optional LLM
      layer, which only fills fields the regex path could not read; any failure
      falls back to the regex result untouched.

    The objection window comes from the statute config (the tagger holds no
    statutory number of its own); when it is absent, lateness is reported as
    *not assessed* rather than as "zero days".
    """
    raw = await file.read()
    window, window_ref, window_verified = objection_window(load_config())
    try:
        return run_extraction(
            raw=raw,
            objection_window_days=window,
            window_source_ref=window_ref,
            window_verified=window_verified,
            use_cache=os.environ.get("EXTRACTION_DEMO_CACHE", "").strip().lower()
            in _TRUTHY,
            llm=settings_from_env(os.environ),
        )
    except ExtractionInputError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
