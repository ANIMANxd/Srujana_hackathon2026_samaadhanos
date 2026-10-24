"""FastAPI entrypoint for SamadhaanOS — contract v1.0 (architecture.md section 8).

POST /evaluate-case runs the real engine (`backend.engine.evaluate`), which
assembles the response from the rule modules. The API layer owns the file reads,
the schema validation and the error envelope; it computes no legal number
itself (golden rule 6).
"""

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.app.config_loader import load_config
from backend.app.schemas import (
    CONTRACT_VERSION,
    CaseEvaluationRequest,
    CaseEvaluationResponse,
    ErrorResponse,
    SettlementSimulationRequest,
    SettlementSimulationResponse,
)
from backend.engine.config import ConfigError, StatuteConfig
from backend.engine.evaluate import evaluate_case as evaluate_case_engine
from backend.engine.settlement import evaluate_settlement

PRESETS_DIR = Path(__file__).resolve().parent.parent / "presets"

app = FastAPI(
    title="SamadhaanOS API",
    version=CONTRACT_VERSION,
    description=(
        "MSME payment-rights evaluation API. Contract v1.0; frozen and "
        "additive-only after the contract-v1 tag (architecture.md section 9)."
    ),
)


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


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
