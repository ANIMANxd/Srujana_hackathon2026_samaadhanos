"""FastAPI entrypoint for SamadhaanOS — contract v1.0 (architecture.md section 8).

Legal logic lives in the engine, which does not exist yet. Until it lands,
POST /evaluate-case returns a fixed, schema-valid sample labelled with a
PLACEHOLDER_DATA warning (golden rule 7). Nothing here computes law.
"""

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.app.config_loader import load_config
from backend.app.placeholder import placeholder_evaluation
from backend.app.schemas import (
    CONTRACT_VERSION,
    CaseEvaluationRequest,
    CaseEvaluationResponse,
    ErrorResponse,
)

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
    """Reshape raised HTTPExceptions (e.g. 404 preset) into the contract error shape."""
    return _error(
        code="NOT_FOUND" if exc.status_code == 404 else f"HTTP_{exc.status_code}",
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


@app.post("/api/v1/evaluate-case", response_model=CaseEvaluationResponse)
def evaluate_case(request: CaseEvaluationRequest) -> CaseEvaluationResponse:
    """Evaluate a case.

    PLACEHOLDER: the engine is not built yet, so this returns a fixed sample
    response flagged with a PLACEHOLDER_DATA warning. It evaluates nothing.
    """
    return placeholder_evaluation(request)


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
