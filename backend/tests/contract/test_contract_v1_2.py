"""Contract v1.2 conformance: v1.0/v1.1 are frozen, v1.2 adds the v5 routes.

The v1.1 fingerprint was captured before the v1.2 models and the first v1.2
routes were added (contracts/fixtures/v5/v1.1-contract-baseline.json); every
entry in it must still hash identically. The only new paths allowed are the
payment and customer-book paths v1.2 declares.

The v5 fixtures are hand-shaped placeholders until the CB6 export exists. They
must say so, and they must still validate against the models they claim to show.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import TypeAdapter

from backend.app.main import app
from backend.app.schemas import CONTRACT_VERSION
from backend.app.schemas_v4 import CONTRACT_VERSION_V1_1
from backend.app.schemas_v5 import (
    V1_2_MODELS,
    BuyerCostSummary,
    ChartSeriesPoint,
    Customer,
    CustomerGroupRow,
    CustomerListResponse,
    CustomerProfile,
    CustomerRow,
    CustomerSeriesPoint,
    CustomerStats,
    ImportPreview,
    ImportResult,
    Payment,
    PaymentCreateRequest,
    PaymentListResponse,
    PortfolioInsights,
    SuggestedAction,
    Suggestion,
    SuggestionListResponse,
)
from backend.app.schemas_v5 import CONTRACT_VERSION_V1_2

ROOT = Path(__file__).resolve().parents[3]
V5_FIXTURES = ROOT / "contracts" / "fixtures" / "v5"
BASELINE = V5_FIXTURES / "v1.1-contract-baseline.json"
OPENAPI = ROOT / "contracts" / "openapi.json"

FIXTURE_MODELS: dict[str, Any] = {
    "customer.json": Customer,
    "customer-row.json": CustomerRow,
    "customer-group-row.json": CustomerGroupRow,
    "customer-profile.json": CustomerProfile,
    "customer-stats.json": CustomerStats,
    "customer-list.json": CustomerListResponse,
    "customer-series-point.json": CustomerSeriesPoint,
    "chart-series-point.json": ChartSeriesPoint,
    "buyer-cost-summary.json": BuyerCostSummary,
    "suggested-action.json": SuggestedAction,
    "payment.json": Payment,
    "payment-create-request.json": PaymentCreateRequest,
    "payment-list.json": PaymentListResponse,
    "suggestion.json": Suggestion,
    "suggestion-list.json": SuggestionListResponse,
    "import-preview.json": ImportPreview,
    "import-result.json": ImportResult,
    "portfolio-insights.json": PortfolioInsights,
}


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _baseline() -> dict[str, Any]:
    return _load(BASELINE)


# ------------------------------------------------- v1.1 must not have moved ----


def test_the_v1_1_baseline_is_the_pre_v1_2_document():
    """The fingerprint is the v1.1 document as it stood before v1.2 was added.

    It is not the historical `contract-v1.1` tag (which predates the v1.1
    routes); it is the complete v1.1 surface the v1.2 work starts from.
    """
    base = _baseline()
    assert base["info_version"] == CONTRACT_VERSION == "1.0"
    assert base["contract_version"] == CONTRACT_VERSION_V1_1 == "1.1"
    assert base["schema_count"] == len(base["components"])
    assert len(base["paths"]) == 27


def test_every_v1_1_component_schema_is_byte_identical():
    live = app.openapi()["components"]["schemas"]
    changed: list[str] = []
    missing: list[str] = []
    for name, digest in _baseline()["components"].items():
        if name not in live:
            missing.append(name)
        elif _fingerprint(live[name]) != digest:
            changed.append(name)
    assert not missing, f"v1.1 schemas removed by v1.2: {sorted(missing)}"
    assert not changed, (
        "v1.1 schemas changed by v1.2 (contract v1.1 is frozen, section 9): "
        f"{sorted(changed)}"
    )


def test_every_v1_1_path_is_byte_identical():
    live = app.openapi()["paths"]
    changed = [
        path
        for path, digest in _baseline()["paths"].items()
        if path not in live or _fingerprint(live[path]) != digest
    ]
    assert not changed, f"v1.1 paths changed by v1.2: {sorted(changed)}"


def test_v1_2_adds_the_payment_and_customer_book_routes():
    """v1.2 adds the payment and customer-book paths; the v1.1 set stays intact."""
    live = set(app.openapi()["paths"])
    baseline = set(_baseline()["paths"])
    added = live - baseline
    assert added == {
        "/api/v1/cases/{case_id}/payments",
        "/api/v1/cases/{case_id}/payments/{payment_id}/void",
        # CB3-CB5: the customer book, its owner actions and the portfolio view.
        "/api/v1/customers",
        "/api/v1/customers/suggestions",
        "/api/v1/customers/suggestions/dismiss",
        "/api/v1/customers/{customer_id}",
        "/api/v1/customers/{customer_id}/attach",
        "/api/v1/customers/{customer_id}/detach",
        "/api/v1/customer-groups",
        "/api/v1/customer-groups/{group_id}/members",
        "/api/v1/customer-groups/{group_id}/members/{customer_id}",
        "/api/v1/insights",
    }, f"unexpected v1.2 paths: {sorted(added)}"
    assert baseline <= live, f"a v1.1 path disappeared: {sorted(baseline - live)}"


# ------------------------------------------------------ v1.2 is well formed ----


def test_the_v1_2_contract_number_is_separate_from_v1_0():
    assert CONTRACT_VERSION == "1.0"
    assert CONTRACT_VERSION_V1_2 == "1.2"
    assert CONTRACT_VERSION_V1_1 == "1.1"


def test_every_v1_2_model_is_published_as_a_component():
    live = app.openapi()["components"]["schemas"]
    missing = [model.__name__ for model in V1_2_MODELS if model.__name__ not in live]
    assert not missing, f"v1.2 components missing from openapi.json: {missing}"


def test_the_committed_openapi_document_matches_the_live_app():
    assert _load(OPENAPI) == app.openapi(), "run `make openapi` and `make types`"


def test_v1_2_stats_averages_are_nullable_and_explained():
    """AGENTS.md rule 25: a nullable average carries the reason and the sample size."""
    schema = app.openapi()["components"]["schemas"]["CustomerStats"]["properties"]
    for average, reason in (
        ("avg_days_to_pay", "avg_days_to_pay_reason"),
        ("on_time_pct", "on_time_pct_reason"),
    ):
        assert average in schema and reason in schema
        assert '"null"' in json.dumps(schema[average]), (
            f"{average} must be nullable so the UI can show 'not enough history'"
        )
    assert "based_on" in schema and "min_history" in schema


def test_customer_shapes_use_no_score_rating_or_risk_words():
    """AGENTS.md rule 22: descriptive only, never a buyer score or prediction."""
    forbidden = ("score", "rating", "risk", "rank", "defaulter", "blacklist", "predict")
    schemas = app.openapi()["components"]["schemas"]
    for name in (
        "Customer",
        "CustomerRow",
        "CustomerGroupRow",
        "CustomerProfile",
        "CustomerStats",
        "PortfolioInsights",
    ):
        for property_name in schemas[name].get("properties", {}):
            lowered = property_name.lower()
            assert not any(word in lowered for word in forbidden), (
                f"{name}.{property_name} uses a forbidden buyer label"
            )


def test_money_and_similarity_are_strings_not_floats():
    schemas = app.openapi()["components"]["schemas"]
    assert schemas["Payment"]["properties"]["amount"]["type"] == "string"
    assert schemas["Suggestion"]["properties"]["similarity"]["type"] == "string"
    assert (
        schemas["CustomerStats"]["properties"]["outstanding_total"]["type"] == "string"
    )


def test_suggestion_kinds_are_the_two_owner_actions():
    kind_schema = app.openapi()["components"]["schemas"]["SuggestionKind"]
    assert set(kind_schema["enum"]) == {"ATTACH", "LINK_AS_GROUP"}


# ----------------------------------------------------------- v5 fixtures ----


def test_every_v1_2_model_has_a_placeholder_fixture():
    assert set(FIXTURE_MODELS) == {
        "customer.json",
        "customer-row.json",
        "customer-group-row.json",
        "customer-profile.json",
        "customer-stats.json",
        "customer-list.json",
        "customer-series-point.json",
        "chart-series-point.json",
        "buyer-cost-summary.json",
        "suggested-action.json",
        "payment.json",
        "payment-create-request.json",
        "payment-list.json",
        "suggestion.json",
        "suggestion-list.json",
        "import-preview.json",
        "import-result.json",
        "portfolio-insights.json",
    }


@pytest.mark.parametrize("filename", sorted(FIXTURE_MODELS))
def test_v5_fixture_is_marked_placeholder_and_validates(filename: str):
    document = _load(V5_FIXTURES / filename)
    meta = document["_fixture"]
    assert meta["contract_version"] == CONTRACT_VERSION_V1_2
    assert meta["synthetic"] is True
    assert meta["placeholder"] is True, (
        "CB6 has not generated these from the seeded database yet; every v1.2 "
        "fixture is still hand-shaped"
    )
    assert meta["placeholder_fields"], f"{filename} names no placeholder fields"
    assert meta["schema"] == FIXTURE_MODELS[filename].__name__
    TypeAdapter(FIXTURE_MODELS[filename]).validate_python(document["payload"])


def test_the_customer_stats_fixture_shows_not_enough_history():
    payload = _load(V5_FIXTURES / "customer-stats.json")["payload"]
    assert payload["avg_days_to_pay"] is None
    assert payload["on_time_pct"] is None
    assert payload["based_on"] < payload["min_history"]
    assert "Not enough history" in payload["avg_days_to_pay_reason"]
    assert "Not enough history" in payload["on_time_pct_reason"]
