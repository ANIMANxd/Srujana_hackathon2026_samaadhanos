"""Contract v1.0 tests (architecture.md section 11, tests/contract).

These prove the frozen contract holds: every fixture validates against the
models, the committed openapi.json matches the live app, every preset evaluates
through the real engine, and the blocked presets come back with null money
blocks plus a BLOCK warning rather than zeros.

They do NOT test legal arithmetic — that is tests/spec's job.
"""

import json
from decimal import Decimal as D
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.schemas import (
    CaseEvaluationRequest,
    CaseEvaluationResponse,
    SettlementSimulationResponse,
)

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "contracts" / "fixtures"
OPENAPI = ROOT / "contracts" / "openapi.json"
PRESETS = ROOT / "backend" / "presets"

# The preset ids this repo ships. case_05's two variants are blocked cases and
# case_06 is the stretch (no delivery proof); see docs/open-questions.md CQ-32.
PRESET_IDS = ["case_01", "case_02", "case_03", "case_04", "case_05a", "case_05b", "case_06"]
BLOCKED_IDS = ["case_05a", "case_05b"]
# Top-level keys a preset file may carry: descriptive text plus the input.
PRESET_KEYS = {"title", "note", "why_calculation_date", "request"}

client = TestClient(app)


def _fixture_files(suffix: str) -> list[Path]:
    return sorted(p for p in FIXTURES.glob(f"*.{suffix}.json"))


def _preset_request(preset_id: str) -> dict:
    data = json.loads((PRESETS / f"{preset_id}.json").read_text(encoding="utf-8"))
    return data["request"]


# ------------------------------------------------------------- fixtures ----


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
def test_response_fixture_is_what_the_engine_answers(path: Path):
    """A fixture is a recorded answer, so it must equal the live engine's.

    Golden rule 7 is satisfied by provenance rather than by a label: the
    response came from the engine, and a stale or hand-edited fixture fails
    here because the API's own output is the oracle.
    """
    # Stem is "case_01.response", so strip the whole suffix, not just ".json".
    preset_id = path.name.removesuffix(".response.json")
    request_path = FIXTURES / f"{preset_id}.request.json"
    assert request_path.exists(), f"{path.name} has no matching request fixture"
    response = json.loads(path.read_text(encoding="utf-8"))
    assert "PLACEHOLDER_DATA" not in {w["code"] for w in response.get("warnings", [])}

    resp = client.post("/api/v1/evaluate-case", json=json.loads(request_path.read_text(encoding="utf-8")))
    assert resp.status_code == 200, resp.text[:400]
    assert resp.json() == response, f"{path.name} has drifted from the engine"


def test_openapi_matches_live_app():
    """The committed openapi.json must not drift from the app (section 9.4)."""
    committed = json.loads(OPENAPI.read_text(encoding="utf-8"))
    live = app.openapi()
    assert committed == live, (
        "contracts/openapi.json is out of date; run `make openapi` (and `make types`)"
    )


# ------------------------------------------------------------- presets ----


def test_the_expected_presets_are_shipped():
    listing = client.get("/api/v1/presets")
    assert listing.status_code == 200
    assert [p["id"] for p in listing.json()["presets"]] == PRESET_IDS


@pytest.mark.parametrize("preset_id", PRESET_IDS)
def test_every_preset_evaluates_without_error(preset_id: str):
    """Acceptance: all presets evaluate, and their responses validate."""
    resp = client.post("/api/v1/evaluate-case", json=_preset_request(preset_id))
    assert resp.status_code == 200, resp.text[:600]
    body = resp.json()
    CaseEvaluationResponse.model_validate(body)  # must not raise
    assert body["case_id"] == preset_id
    assert "PLACEHOLDER_DATA" not in {w["code"] for w in body["warnings"]}
    assert body["jurisdiction"]["status"]


@pytest.mark.parametrize("preset_id", BLOCKED_IDS)
def test_blocked_presets_null_the_money_and_explain_it(preset_id: str):
    """Acceptance: blocked presets return null downstream blocks with remedies."""
    body = client.post("/api/v1/evaluate-case", json=_preset_request(preset_id)).json()
    assert body["jurisdiction"]["status"] in {"BARRED_SILPI", "EXCLUDED_TRADER", "EXCLUDED_MEDIUM"}
    # Never zeros: the two money blocks are absent and a BLOCK warning says why.
    assert body["financials"] is None
    assert body["buyer_cost"] is None
    block_warnings = [w for w in body["warnings"] if w["severity"] == "BLOCK"]
    assert block_warnings, "a blocked case must explain why the blocks are empty"
    assert "not because the amounts are zero" in block_warnings[0]["text"]
    # The alternative remedy is offered, and only for an ineligible case.
    assert body["jurisdiction"]["alternative_remedy"]
    assert "does not predict an outcome" in body["jurisdiction"]["alternative_remedy"]
    # The blocks that are never nullable still report.
    assert body["limitation"] is not None
    assert len(body["defenses"]) == 7
    assert body["evidence_readiness"]["band"] == "BLOCKED"


@pytest.mark.parametrize("preset_id", PRESET_IDS)
def test_preset_files_carry_no_expected_outputs(preset_id: str):
    """Presets are input-only: an answer recorded next to a question is a trap."""
    data = json.loads((PRESETS / f"{preset_id}.json").read_text(encoding="utf-8"))
    assert "request" in data
    assert set(data) <= PRESET_KEYS, f"{preset_id}.json carries non-input keys: {set(data) - PRESET_KEYS}"


def test_evaluation_is_deterministic():
    """Same request twice, byte for byte (the engine reads no clock)."""
    request = _preset_request("case_02")
    first = client.post("/api/v1/evaluate-case", json=request)
    second = client.post("/api/v1/evaluate-case", json=request)
    assert first.status_code == second.status_code == 200
    assert first.content == second.content


# ------------------------------------------------------------- settlement ----


def test_simulate_settlement_returns_a_valid_split():
    payload = {
        "request": _preset_request("case_01"),
        "upfront_pct": "50",
        "waiver_pct": "20",
        "days_to_second_payment": 30,
    }
    resp = client.post("/api/v1/simulate-settlement", json=payload)
    assert resp.status_code == 200, resp.text[:400]
    body = SettlementSimulationResponse.model_validate(resp.json())  # must not raise
    assert body.contract_version == "1.0"
    paid = sum((p.amount for p in body.payments), D("0"))
    assert paid == body.total_payable
    assert body.net_recovery == body.total_claim - body.interest_waived
    assert [p.days_from_now for p in body.payments] == [0, 30]
    assert body.assumptions


def test_simulate_settlement_refuses_a_blocked_case():
    """No claim to split, so 400 with the contract's envelope, not a 500."""
    payload = {
        "request": _preset_request("case_05a"),
        "upfront_pct": "50",
        "waiver_pct": "20",
        "days_to_second_payment": 30,
    }
    resp = client.post("/api/v1/simulate-settlement", json=payload)
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "RULE_VIOLATION"
    assert "no computed claim" in resp.json()["error"]["message"]


def test_simulate_settlement_refuses_out_of_range_percentages():
    payload = {
        "request": _preset_request("case_01"),
        "upfront_pct": "150",
        "waiver_pct": "20",
        "days_to_second_payment": 30,
    }
    resp = client.post("/api/v1/simulate-settlement", json=payload)
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "RULE_VIOLATION"


# ------------------------------------------------------------- endpoints ----


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


def test_preset_detail_and_missing_preset():
    detail = client.get("/api/v1/presets/case_01")
    assert detail.status_code == 200
    assert "request" in detail.json()
    assert client.get("/api/v1/presets/nope").status_code == 404
