"""Contract v1.0 tests (architecture.md section 11, tests/contract).

These prove the frozen contract holds: every fixture validates against the
models, the committed openapi.json matches the live app, and the evaluate-case
endpoint returns a schema-valid placeholder flagged PLACEHOLDER_DATA. They do
NOT test legal math — that is tests/spec's job, and the engine does not exist
yet.
"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.schemas import CaseEvaluationRequest, CaseEvaluationResponse

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "contracts" / "fixtures"
OPENAPI = ROOT / "contracts" / "openapi.json"

client = TestClient(app)


def _fixture_files(suffix: str) -> list[Path]:
    return sorted(p for p in FIXTURES.glob(f"*.{suffix}.json"))


def test_at_least_one_fixture_exists():
    assert _fixture_files("request"), "no *.request.json fixtures in contracts/fixtures"
    assert _fixture_files("response"), "no *.response.json fixtures in contracts/fixtures"


@pytest.mark.parametrize("path", _fixture_files("request"), ids=lambda p: p.stem)
def test_request_fixtures_validate(path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    CaseEvaluationRequest.model_validate(data)  # must not raise


@pytest.mark.parametrize("path", _fixture_files("response"), ids=lambda p: p.stem)
def test_response_fixtures_validate(path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    CaseEvaluationResponse.model_validate(data)  # must not raise


@pytest.mark.parametrize("path", _fixture_files("response"), ids=lambda p: p.stem)
def test_response_fixtures_are_labelled_placeholder(path: Path):
    """Golden rule 7: placeholder values must be visibly labelled."""
    data = json.loads(path.read_text(encoding="utf-8"))
    codes = {w["code"] for w in data.get("warnings", [])}
    assert "PLACEHOLDER_DATA" in codes, f"{path.name} is missing the PLACEHOLDER_DATA warning"


def test_openapi_matches_live_app():
    """The committed openapi.json must not drift from the app (section 9.4)."""
    committed = json.loads(OPENAPI.read_text(encoding="utf-8"))
    live = app.openapi()
    assert committed == live, (
        "contracts/openapi.json is out of date; run `make openapi` (and `make types`)"
    )


def test_evaluate_case_returns_valid_placeholder():
    request = json.loads((FIXTURES / "case_01.request.json").read_text(encoding="utf-8"))
    resp = client.post("/api/v1/evaluate-case", json=request)
    assert resp.status_code == 200
    body = resp.json()
    CaseEvaluationResponse.model_validate(body)  # must not raise
    assert "PLACEHOLDER_DATA" in {w["code"] for w in body["warnings"]}


def test_evaluate_case_rejects_malformed_request():
    resp = client.post("/api/v1/evaluate-case", json={"case_id": "x"})
    assert resp.status_code == 422
    err = resp.json()
    assert err["error"]["code"] == "VALIDATION_ERROR"


def test_health_and_config_respond():
    assert client.get("/api/v1/health").status_code == 200
    cfg = client.get("/api/v1/config").json()
    # Either the real config or the labelled stub must be present.
    assert isinstance(cfg, dict) and cfg


def test_presets_endpoints():
    listing = client.get("/api/v1/presets")
    assert listing.status_code == 200
    ids = [p["id"] for p in listing.json()["presets"]]
    assert "case_01" in ids
    detail = client.get("/api/v1/presets/case_01")
    assert detail.status_code == 200
    assert "request" in detail.json()
    assert client.get("/api/v1/presets/nope").status_code == 404
