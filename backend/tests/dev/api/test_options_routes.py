"""The options endpoint and the judge-console clock.

`GET /cases/{id}/options` is where Option 1 and Option 2 meet, so these tests pin the
things that must never drift: no recommendation ever, config citations on every
number, the section 1.1 notes, and the fact that time is the only input that changes
the verdict.
"""

from __future__ import annotations

import copy
import json
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app import deps
from backend.app.main import app
from backend.store import db as store_db

ROOT = Path(__file__).resolve().parents[4]
PRESET = json.loads((ROOT / "contracts" / "fixtures" / "case_01.request.json").read_text())

# The shipped presets are all overdue, so the financing happy path needs an invoice
# that is not yet due: delivery 2026-09-14 + the 45-day cap = due 2026-10-29.
OPEN_PRESET = copy.deepcopy(PRESET)
OPEN_PRESET["transaction"].update(
    {
        "contract_date": "2026-08-01",
        "supply_date": "2026-09-14",
        "delivery_date": "2026-09-14",
        "invoice_date": "2026-09-16",
        "calculation_date": "2026-10-25",
    }
)


@pytest.fixture()
def sim_client(database_url, monkeypatch) -> TestClient:
    """A client with the simulated clock on, as `make demo` runs it."""
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("MOCK_CLOCK", "1")
    monkeypatch.setenv("APP_ENV", "development")
    store_db.dispose()
    store_db.init_db(database_url)
    deps.reset_adapters()
    client = TestClient(app)
    yield client
    deps.reset_adapters()
    store_db.dispose()


@pytest.fixture()
def open_case(sim_client: TestClient) -> str:
    response = sim_client.post("/api/v1/cases", json=OPEN_PRESET)
    assert response.status_code == 201, response.text[:400]
    return response.json()["case"]["id"]


def _options(client: TestClient, case_id: str, query: str = "") -> dict:
    response = client.get(f"/api/v1/cases/{case_id}/options{query}")
    assert response.status_code == 200, response.text[:500]
    return response.json()


# ---------------------------------------------------------------- options ----


def test_options_returns_both_columns(sim_client, open_case):
    body = _options(sim_client, open_case)
    assert body["get_paid_early"]["available"] is True
    assert body["recover_with_law"]["available"] is True
    assert body["get_paid_early"]["indicative"]["accepted_amount"] == "1250000.00"
    assert body["recover_with_law"]["principal"] == "1250000.00"
    assert body["simulation"] is True


def test_recommendation_is_null(sim_client, open_case):
    """Golden rule 20, asserted from the route as well as from the schema."""
    body = _options(sim_client, open_case)
    assert body["recommendation"] is None


def test_recommendation_stays_null_when_option_one_is_blocked(sim_client):
    """The tempting moment to add one is exactly when one option is unavailable."""
    overdue = sim_client.post("/api/v1/cases", json=PRESET)
    body = _options(sim_client, overdue.json()["case"]["id"])
    assert body["get_paid_early"]["available"] is False
    assert body["recommendation"] is None


def test_the_default_expected_payment_date_is_as_of_plus_30_days(sim_client, open_case):
    body = _options(sim_client, open_case)
    as_of = date.fromisoformat(body["as_of"])
    expected = date.fromisoformat(body["recover_with_law"]["expected_payment_date"])
    assert expected == as_of + timedelta(days=30)


def test_an_explicit_expected_payment_date_is_honoured(sim_client, open_case):
    body = _options(sim_client, open_case, "?expected_payment_date=2026-12-31")
    assert body["recover_with_law"]["expected_payment_date"] == "2026-12-31"


def test_a_later_expected_date_accrues_more_interest(sim_client, open_case):
    """s.16 interest is time-based, so a later date must cost the buyer more."""
    near = _options(sim_client, open_case, "?expected_payment_date=2026-11-24")
    far = _options(sim_client, open_case, "?expected_payment_date=2026-12-31")
    assert float(far["recover_with_law"]["interest_to_expected_date"]) > float(
        near["recover_with_law"]["interest_to_expected_date"]
    )


def test_option_two_total_is_principal_plus_engine_interest(sim_client, open_case):
    """The engine owns s.16; the route must not re-add anything of its own."""
    body = _options(sim_client, open_case, "?expected_payment_date=2026-11-24")
    principal = float(body["recover_with_law"]["principal"])
    interest = float(body["recover_with_law"]["interest_to_expected_date"])
    total = float(body["recover_with_law"]["total_if_paid"])
    assert round(principal + interest, 2) == total
    assert interest == 14768.84, "the engine's figure for this case at this date"


def test_every_finance_number_carries_a_config_citation(sim_client, open_case):
    """A number with no provenance is a number nobody can defend."""
    body = _options(sim_client, open_case)
    refs = {citation["ref"] for citation in body["get_paid_early"]["citations"]}
    assert refs == {
        "config:treds.settlement_days",
        "config:mock_financing.rate_band",
        "config:mock_financing.platform_fee_pct",
        "config:financing.day_count",
    }
    assert all(citation["source"] for citation in body["get_paid_early"]["citations"])

    recovery_refs = {citation["ref"] for citation in body["recover_with_law"]["citations"]}
    assert "config:interest_multiplier" in recovery_refs


def test_the_section_1_1_notes_are_present(sim_client, open_case):
    body = _options(sim_client, open_case)
    notes = " ".join(body["get_paid_early"]["notes"]).lower()
    assert "buyer must accept" in notes, "the buyer-acceptance fact must be on screen"
    assert "interest" in notes and "not included" in notes, "accrued interest must be excluded"

    recovery_notes = " ".join(body["recover_with_law"]["notes"]).lower()
    assert "only" in recovery_notes and "buyer pays" in recovery_notes


def test_options_404_for_an_unknown_case(sim_client):
    assert sim_client.get("/api/v1/cases/NOPE00000000000000000000/options").status_code == 404


def test_options_body_matches_the_published_schema(sim_client, open_case):
    from backend.app.schemas_v4 import OptionsResponse

    body = _options(sim_client, open_case)
    assert set(body) == {
        "case_id",
        "as_of",
        "simulation",
        "get_paid_early",
        "recover_with_law",
        "recommendation",
    }, "no undeclared fields leak out of the route"
    OptionsResponse.model_validate(body)


# ------------------------------------------------------------------ clock ----


def test_advancing_the_clock_past_the_due_date_hides_option_one(sim_client, open_case):
    """The acceptance test for the whole two-option story."""
    detail = sim_client.get(f"/api/v1/cases/{open_case}").json()
    due = date.fromisoformat(detail["latest_evaluation"]["timeline"]["due_date"])

    before = _options(sim_client, open_case)
    assert before["get_paid_early"]["available"] is True

    moved = sim_client.post("/api/v1/mock/clock", json={"advance_days": 10})
    assert moved.status_code == 200
    assert moved.json()["offset_seconds"] == 10 * 86400

    after = _options(sim_client, open_case)
    assert after["get_paid_early"]["available"] is False, "past the due date, Option 1 cannot be financed"
    assert after["get_paid_early"]["indicative"] is None, "no numbers for an option you cannot take"
    assert after["get_paid_early"]["unavailable_reasons"], "a blocked option must say why"
    assert after["recover_with_law"]["available"] is True, "Option 2 remains"
    assert after["as_of"] != before["as_of"]
    assert due <= date.fromisoformat(after["as_of"]), "the clock really did pass the due date"


def test_advancing_the_clock_re_evaluates_the_case(sim_client, open_case):
    before = sim_client.get(f"/api/v1/cases/{open_case}").json()["latest_evaluation"]
    # Far enough past the appointed day for s.16 interest to have accrued at all.
    sim_client.post("/api/v1/mock/clock", json={"advance_days": 40})
    after = sim_client.get(f"/api/v1/cases/{open_case}").json()["latest_evaluation"]

    assert after["calculation_date"] != before["calculation_date"]
    assert after["financials"]["interest_total"] != before["financials"]["interest_total"], (
        "a later calculation date must accrue more interest"
    )


def test_resetting_the_clock_restores_option_one(sim_client, open_case):
    sim_client.post("/api/v1/mock/clock", json={"advance_days": 10})
    assert _options(sim_client, open_case)["get_paid_early"]["available"] is False

    reset = sim_client.post("/api/v1/mock/clock/reset")
    assert reset.status_code == 200
    assert reset.json()["offset_seconds"] == 0
    assert _options(sim_client, open_case)["get_paid_early"]["available"] is True


def test_the_clock_may_not_run_backwards(sim_client):
    """A rewritten timeline would break the audit story; reset is the way back."""
    response = sim_client.post("/api/v1/mock/clock", json={"advance_days": -3})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "CLOCK_BACKWARDS"


def test_the_mock_routes_are_404_in_production(monkeypatch, database_url):
    """Not hidden from the UI: refused by the server, because UI is not security."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("PROVIDER_MODE", "live")
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.delenv("MOCK_CLOCK", raising=False)
    store_db.dispose()
    store_db.init_db(database_url)
    deps.reset_adapters()

    # A bare client: entering it would run the startup guard, which is a separate test.
    client = TestClient(app)
    try:
        for method, path in (
            ("post", "/api/v1/mock/clock"),
            ("post", "/api/v1/mock/clock/reset"),
        ):
            response = getattr(client, method)(path, json={"advance_days": 1})
            assert response.status_code == 404, f"{path} must not exist in production"
            assert response.json()["error"]["code"] == "NOT_FOUND"
    finally:
        deps.reset_adapters()
        store_db.dispose()


def test_a_real_clock_says_so_instead_of_silently_doing_nothing(monkeypatch, database_url):
    """Without MOCK_CLOCK the button must explain itself, not pretend to work."""
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("MOCK_CLOCK", raising=False)
    store_db.dispose()
    store_db.init_db(database_url)
    deps.reset_adapters()

    client = TestClient(app)
    try:
        response = client.post("/api/v1/mock/clock", json={"advance_days": 1})
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "CLOCK_NOT_SIMULATED"
        assert "MOCK_CLOCK" in response.json()["error"]["details"]["hint"]
    finally:
        deps.reset_adapters()
        store_db.dispose()
