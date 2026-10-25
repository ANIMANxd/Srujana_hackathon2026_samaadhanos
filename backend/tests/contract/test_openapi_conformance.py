"""Every endpoint's real response, and every committed fixture, against openapi.json.

Architecture section 9.4: `make test` validates the contract so drift fails
loudly. Two layers do that here:

- **live responses** - each declared path in `contracts/openapi.json` is called
  for real and its JSON body is validated against the response schema the
  document declares for it (jsonschema over the OpenAPI 3.1 document, refs
  resolved through a registry, so `$ref`s inside the spec resolve correctly);
- **fixtures** - `contracts/fixtures/*.request.json` and `*.response.json` are
  validated against the same document's component schemas.

Error responses are checked against section 8.1's envelope structurally rather
than against the OpenAPI document: the document still declares FastAPI's
default `HTTPValidationError` for 422 and declares no 404 for
`/presets/{id}`, while the app returns `{error: {code, message, field?}}`.
That declaration gap is CQ-48 in docs/open-questions.md; the envelope test
below pins the runtime behaviour until the declaration is corrected.
"""

import json
from pathlib import Path

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from backend.app.main import app

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "contracts" / "fixtures"
SPEC = json.loads((ROOT / "contracts" / "openapi.json").read_text(encoding="utf-8"))
REGISTRY = Registry().with_resource(
    "urn:openapi", Resource(contents=SPEC, specification=DRAFT202012)
)

client = TestClient(app)

# Which paths each test group exercises, so a new endpoint in the contract
# fails here until something calls it.
READ_PATHS = {
    "/api/v1/health",
    "/api/v1/config",
    "/api/v1/presets",
    "/api/v1/presets/{preset_id}",
    "/api/v1/cases",
    "/api/v1/cases/{case_id}",
    "/api/v1/cases/{case_id}/events",
    "/api/v1/cases/{case_id}/events/verify",
}
WRITE_PATHS = {
    "/api/v1/evaluate-case",
    "/api/v1/simulate-settlement",
    "/api/v1/generate-artifact",
    "/api/v1/cases",
}
UPLOAD_PATHS = {"/api/v1/extract-evidence"}


def _escape(segment: str) -> str:
    return segment.replace("~", "~0").replace("/", "~1")


def _response_pointer(path: str, method: str, status: int = 200) -> str:
    # OpenAPI keys the operations in lowercase ("get", "post").
    return (
        f"#/paths/{_escape(path)}/{method.lower()}/responses/{status}"
        f"/content/{_escape('application/json')}/schema"
    )


def _assert_matches(pointer: str, body, label: str) -> None:
    validator = Draft202012Validator(
        {"$ref": f"urn:openapi{pointer}"}, registry=REGISTRY
    )
    errors = sorted(validator.iter_errors(body), key=lambda e: list(e.absolute_path))
    detail = "\n".join(
        f"at {list(error.absolute_path)}: {error.message[:300]}" for error in errors[:5]
    )
    assert not errors, f"{label} does not match {pointer}:\n{detail}"


def _preset_request() -> dict:
    data = json.loads(
        (ROOT / "backend" / "presets" / "case_01.json").read_text(encoding="utf-8")
    )
    return data["request"]


# ------------------------------------------------------------- live calls ----


def test_every_declared_path_is_exercised():
    """A new path in openapi.json must come with a test that calls it."""
    declared = set(SPEC["paths"])
    exercised = READ_PATHS | WRITE_PATHS | UPLOAD_PATHS
    assert declared == exercised, (
        f"undeclared-but-exercised: {sorted(exercised - declared)}; "
        f"declared-but-never-called: {sorted(declared - exercised)}"
    )


def test_read_endpoints_match_the_contract():
    """Every declared GET answers in the shape the contract declares.

    The case routes need a case, so one is created here; `POST /cases` is also
    declared as a write path and is exercised by the create test.
    """
    created = client.post("/api/v1/cases", json=_preset_request())
    assert created.status_code == 201, created.text[:300]
    case_id = created.json()["case"]["id"]

    responses = [
        ("GET", "/api/v1/health", client.get("/api/v1/health")),
        ("GET", "/api/v1/config", client.get("/api/v1/config")),
        ("GET", "/api/v1/presets", client.get("/api/v1/presets")),
        ("GET", "/api/v1/presets/{preset_id}", client.get("/api/v1/presets/case_01")),
        ("GET", "/api/v1/cases", client.get("/api/v1/cases")),
        ("GET", "/api/v1/cases/{case_id}", client.get(f"/api/v1/cases/{case_id}")),
        ("GET", "/api/v1/cases/{case_id}/events", client.get(f"/api/v1/cases/{case_id}/events")),
        (
            "GET",
            "/api/v1/cases/{case_id}/events/verify",
            client.get(f"/api/v1/cases/{case_id}/events/verify"),
        ),
    ]
    for method, path, response in responses:
        assert response.status_code == 200, f"{method} {path}: {response.text[:300]}"
        _assert_matches(
            _response_pointer(path, method), response.json(), f"{method} {path}"
        )


def test_create_case_matches_the_contract():
    """`POST /cases` declares 201, and the body is a CaseDetail."""
    created = client.post("/api/v1/cases", json=_preset_request())
    assert created.status_code == 201, created.text[:300]
    _assert_matches(
        _response_pointer("/api/v1/cases", "POST", 201), created.json(), "POST /api/v1/cases"
    )
    body = created.json()
    assert body["case"]["id"], "a server-issued id is required"
    assert body["latest_evaluation"]["case_id"] == body["case"]["id"]
    assert body["available_actions"], "a fresh case must offer an action"


def test_evaluate_and_settlement_match_the_contract():
    request = _preset_request()
    evaluate = client.post("/api/v1/evaluate-case", json=request)
    assert evaluate.status_code == 200, evaluate.text[:300]
    _assert_matches(
        _response_pointer("/api/v1/evaluate-case", "post"),
        evaluate.json(),
        "POST /api/v1/evaluate-case",
    )

    settlement = client.post(
        "/api/v1/simulate-settlement",
        json={
            "request": request,
            "upfront_pct": "50",
            "waiver_pct": "20",
            "days_to_second_payment": 30,
        },
    )
    assert settlement.status_code == 200, settlement.text[:300]
    _assert_matches(
        _response_pointer("/api/v1/simulate-settlement", "post"),
        settlement.json(),
        "POST /api/v1/simulate-settlement",
    )


def test_generate_artifact_matches_the_contract():
    response = client.post(
        "/api/v1/generate-artifact",
        json={"kind": "STAGE1_ACCEPTANCE_NOTE", "request": _preset_request()},
    )
    assert response.status_code == 200, response.text[:300]
    _assert_matches(
        _response_pointer("/api/v1/generate-artifact", "post"),
        response.json(),
        "POST /api/v1/generate-artifact",
    )


def test_extract_evidence_matches_the_contract():
    text = (
        ROOT / "backend" / "extraction" / "demo" / "chat_defect_day9.txt"
    ).read_bytes()
    response = client.post(
        "/api/v1/extract-evidence",
        files={"file": ("chat_defect_day9.txt", text, "text/plain")},
    )
    assert response.status_code == 200, response.text[:300]
    _assert_matches(
        _response_pointer("/api/v1/extract-evidence", "post"),
        response.json(),
        "POST /api/v1/extract-evidence",
    )


# --------------------------------------------------------------- fixtures ----


def _fixture_files(suffix: str) -> list[Path]:
    return sorted(FIXTURES.glob(f"*.{suffix}.json"))


def test_fixtures_exist():
    assert _fixture_files("request"), "no request fixtures to validate"
    assert _fixture_files("response"), "no response fixtures to validate"


def test_request_fixtures_match_the_contract():
    pointer = "#/components/schemas/CaseEvaluationRequest"
    paths = _fixture_files("request")
    assert paths
    for path in paths:
        _assert_matches(
            pointer, json.loads(path.read_text(encoding="utf-8")), path.name
        )


def test_response_fixtures_match_the_contract():
    pointer = "#/components/schemas/CaseEvaluationResponse"
    paths = _fixture_files("response")
    assert paths
    for path in paths:
        _assert_matches(
            pointer, json.loads(path.read_text(encoding="utf-8")), path.name
        )


def test_artifact_samples_are_marked_draft():
    """The committed CASE-01 samples are drafts, not something that snuck out."""
    samples = sorted(FIXTURES.glob("case_01.STAGE*.md"))
    assert len(samples) == 5, f"expected five artifact samples, found {len(samples)}"
    for path in samples:
        text = path.read_text(encoding="utf-8")
        assert text.startswith("# DRAFT"), f"{path.name} is not marked DRAFT"
        assert "not legal advice" in text.lower()


# ----------------------------------------------------------- error shape ----


def test_error_responses_use_the_contract_envelope():
    """Section 8.1's envelope at runtime: 404 and 422 both answer {error: ...}.

    Note: openapi.json still declares FastAPI's HTTPValidationError for 422 and
    declares no 404 for the preset lookup (CQ-48), so these bodies are checked
    against section 8.1 here rather than against the document.
    """
    missing = client.get("/api/v1/presets/no_such_preset")
    assert missing.status_code == 404
    missing_body = missing.json()
    assert set(missing_body) == {"error"}
    assert missing_body["error"]["code"] in {
        "NOT_FOUND",
        "VALIDATION_ERROR",
        "RULE_VIOLATION",
    }
    assert missing_body["error"]["message"]

    invalid = client.post("/api/v1/evaluate-case", json={"case_id": "x"})
    assert invalid.status_code == 422
    invalid_body = invalid.json()
    assert set(invalid_body) == {"error"}
    assert invalid_body["error"]["code"] == "VALIDATION_ERROR"
    assert invalid_body["error"]["message"]
