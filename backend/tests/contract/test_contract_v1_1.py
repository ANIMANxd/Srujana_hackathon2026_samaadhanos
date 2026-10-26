"""Contract v1.1 conformance: the frozen v1.0 contract is untouched, and the
v1.1 additions are well formed.

The two guarantees this file exists for (architecture.md section 9):

1. **v1.0 is byte-identical.** Every v1.0 component schema, every path item and
   the advertised `info.version` are hashed in
   `contracts/fixtures/v4/v1-contract-baseline.json`, captured from the
   contract-v1.0 document at tag time. Contract v1.1 may only have *added*
   components; it may not have edited one.
2. **v1.0 responses did not move.** The real v1.0 endpoints still answer with the
   same shapes and the same `contract_version`, so the frontend's existing
   screens keep working.

Plus the v1.1 fixtures: each one validates against its named model, the audit
chain actually verifies, and `recommendation` is null everywhere (golden rule 20).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import TypeAdapter

from backend.app.main import app
from backend.app.schemas import CONTRACT_VERSION
from backend.app.schemas_v4 import (
    V1_1_MODELS,
    Bid,
    Case,
    CaseDetail,
    ChainVerifyResult,
    ESignSession,
    Event,
    EventActor,
    FinancingRequest,
    OptionsResponse,
    PayoutStatus,
    Track,
    WebhookDelivery,
    ErrorEnvelope,
)

ROOT = Path(__file__).resolve().parents[3]
V4_FIXTURES = ROOT / "contracts" / "fixtures" / "v4"
BASELINE = V4_FIXTURES / "v1-contract-baseline.json"
OPENAPI = ROOT / "contracts" / "openapi.json"

client = TestClient(app)

# Fixture file -> the model its `payload` must validate against.
FIXTURE_MODELS: dict[str, Any] = {
    "options-financeable.json": OptionsResponse,
    "options-not-financeable-overdue.json": OptionsResponse,
    "case-detail-FINANCEABLE.json": CaseDetail,
    "case-detail-AWAITING_BUYER_ACCEPTANCE.json": CaseDetail,
    "case-detail-BIDS_AVAILABLE.json": CaseDetail,
    "case-detail-AWAITING_ESIGN.json": CaseDetail,
    "case-detail-AWAITING_DISBURSEMENT.json": CaseDetail,
    "case-detail-DISBURSED.json": CaseDetail,
    "case-detail-BUYER_DECLINED.json": CaseDetail,
    "case-detail-NO_BIDS.json": CaseDetail,
    "bids.json": list[Bid],
    "esign-session.json": ESignSession,
    "payout.json": PayoutStatus,
    "events.json": list[Event],
    "chain-verify-result.json": ChainVerifyResult,
    "webhook-deliveries.json": list[WebhookDelivery],
}

GENESIS_HASH = "0" * 64


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _baseline() -> dict[str, Any]:
    return _load(BASELINE)


# ------------------------------------------------- v1.0 must not have moved ----


def test_the_v1_0_contract_baseline_is_the_tagged_document():
    """Guard the guard: the baseline must describe a 67-schema, 8-path v1.0."""
    base = _baseline()
    assert base["info_version"] == "1.0"
    assert base["schema_count"] == 67
    assert len(base["components"]) == 67
    assert len(base["paths"]) == 8


def test_every_v1_0_component_schema_is_byte_identical():
    """v1.1 may add components; it may not edit one."""
    live = app.openapi()["components"]["schemas"]
    changed: list[str] = []
    missing: list[str] = []
    for name, digest in _baseline()["components"].items():
        if name not in live:
            missing.append(name)
        elif _fingerprint(live[name]) != digest:
            changed.append(name)
    assert not missing, f"v1.0 schemas removed by v1.1: {sorted(missing)}"
    assert not changed, (
        "v1.0 schemas changed by v1.1 (contract v1.0 is frozen, section 9): "
        f"{sorted(changed)}"
    )


def test_every_v1_0_path_is_byte_identical():
    """No v1.0 operation, parameter or response declaration may shift."""
    live = app.openapi()["paths"]
    changed = [
        path
        for path, digest in _baseline()["paths"].items()
        if path not in live or _fingerprint(live[path]) != digest
    ]
    assert not changed, f"v1.0 paths changed by v1.1: {sorted(changed)}"


def test_the_committed_openapi_document_matches_the_live_app():
    """contracts/openapi.json must be regenerated, not hand-edited (section 9.4)."""
    assert _load(OPENAPI) == app.openapi(), "run `make openapi` and `make types`"


def test_v1_responses_still_report_contract_version_1_0():
    """v1.1 is additive: no v1.0 body may start reporting a new version."""
    assert CONTRACT_VERSION == "1.0"
    for response in (
        client.get("/api/v1/config"),
        client.post(
            "/api/v1/simulate-settlement",
            json={
                "request": _load(
                    ROOT / "contracts" / "fixtures" / "case_01.request.json"
                ),
                "terms": {"upfront_pct": "0.00", "waiver_pct": "0.00", "days_to_second_payment": 0},
            },
        ),
    ):
        if response.status_code == 404:
            continue
        body = response.json()
        if "contract_version" in body:
            assert body["contract_version"] == "1.0"


def test_the_v1_error_envelope_is_unchanged():
    """v1.0 keeps `{error: {code, message, field}}`; v1.1 adds a separate envelope."""
    response = client.post("/api/v1/evaluate-case", json={"nope": True})
    assert response.status_code == 422
    error = response.json()["error"]
    assert set(error) == {"code", "message", "field"}, (
        f"v1.0 error envelope changed: {sorted(error)}"
    )


# ------------------------------------------------------ v1.1 is well formed ----


def test_every_v1_1_model_is_published_as_a_component():
    live = app.openapi()["components"]["schemas"]
    missing = [model.__name__ for model in V1_1_MODELS if model.__name__ not in live]
    assert not missing, f"v1.1 components missing from openapi.json: {missing}"


def test_v1_1_adds_cases_routes_without_touching_a_v1_0_path():
    """Contract v1.1 may add paths; it may not change one that already existed.

    The v1.0 path set is still pinned by
    `test_every_v1_0_path_is_byte_identical`; this asserts the *additions* are only
    the case routes that section 9 declares, so a stray endpoint fails here.
    """
    base = _baseline()
    live = app.openapi()
    added_paths = set(live["paths"]) - set(base["paths"])
    assert added_paths == {
        "/api/v1/cases",
        "/api/v1/cases/{case_id}",
        "/api/v1/cases/{case_id}/events",
        "/api/v1/cases/{case_id}/events/verify",
        "/api/v1/cases/{case_id}/financing",
        "/api/v1/cases/{case_id}/financing/bids",
        "/api/v1/cases/{case_id}/financing/bids/{bid_id}/select",
        "/api/v1/cases/{case_id}/financing/buyer-acceptance",
        "/api/v1/cases/{case_id}/financing/cancel",
        "/api/v1/cases/{case_id}/stream",
        "/api/v1/webhooks/esign",
        "/api/v1/webhooks/marketplace",
        "/api/v1/webhooks/disbursement",
        "/api/v1/cases/{case_id}/options",
        "/api/v1/mock/clock",
        "/api/v1/mock/clock/reset",
        "/api/v1/cases/{case_id}/recovery",
        "/api/v1/cases/{case_id}/recovery/mark-sent",
        "/api/v1/cases/{case_id}/recovery/odr-filed",
        # v1.2 payment routes are additive; the v1.0 path fingerprints above
        # still prove no existing operation moved.
        "/api/v1/cases/{case_id}/payments",
        "/api/v1/cases/{case_id}/payments/{payment_id}/void",
        # v1.2 customer-book routes (CB3-CB5), additive in the same way. The
        # exact set is pinned in tests/contract/test_contract_v1_2.py.
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
    }, f"unexpected new paths in contract v1.1: {sorted(added_paths)}"
    assert set(base["paths"]) <= set(live["paths"]), "a v1.0 path disappeared"
    added = set(live["components"]["schemas"]) - set(base["components"])
    assert len(added) >= 12, f"expected the v1.1 models to be added, got {sorted(added)}"


def test_recommendation_is_typed_null_in_the_schema():
    """Golden rule 20: the contract must make a recommendation unrepresentable."""
    schema = app.openapi()["components"]["schemas"]["OptionsResponse"]["properties"]["recommendation"]
    assert schema["type"] == "null", f"recommendation must be null-typed, got {schema}"


def test_recommendation_is_null_in_every_options_fixture():
    for name in ("options-financeable.json", "options-not-financeable-overdue.json"):
        payload = _load(V4_FIXTURES / name)["payload"]
        assert payload["recommendation"] is None, f"{name} recommends an option"


@pytest.mark.parametrize("filename", sorted(FIXTURE_MODELS))
def test_v4_fixture_validates_against_its_model(filename: str):
    document = _load(V4_FIXTURES / filename)
    assert "_fixture" in document, f"{filename} must carry its provenance block"
    adapter = TypeAdapter(FIXTURE_MODELS[filename])
    adapter.validate_python(document["payload"])


@pytest.mark.parametrize("filename", sorted(FIXTURE_MODELS))
def test_v4_fixtures_declare_whether_they_are_placeholders(filename: str):
    """Golden rule 7: a placeholder number is labelled, never silently shipped."""
    meta = _load(V4_FIXTURES / filename)["_fixture"]
    assert isinstance(meta["placeholder"], bool), f"{filename}: placeholder must be a bool"
    if meta["placeholder"]:
        assert meta["placeholder_fields"], (
            f"{filename} claims to be a placeholder but names no placeholder fields"
        )


def test_the_case_detail_fixtures_describe_one_case():
    """All eight financing states must be the same case, or the demo contradicts itself."""
    case_ids = set()
    for name in FIXTURE_MODELS:
        if not name.startswith("case-detail-"):
            continue
        payload = _load(V4_FIXTURES / name)["payload"]
        case_ids.add(payload["case"]["id"])
        assert payload["active_track"]["case_id"] == payload["case"]["id"]
    assert len(case_ids) == 1, f"case-detail fixtures disagree on the case: {case_ids}"


def test_the_eight_required_financing_states_are_covered():
    expected = {
        "FINANCEABLE",
        "AWAITING_BUYER_ACCEPTANCE",
        "BIDS_AVAILABLE",
        "AWAITING_ESIGN",
        "AWAITING_DISBURSEMENT",
        "DISBURSED",
        "BUYER_DECLINED",
        "NO_BIDS",
    }
    present = {
        _load(V4_FIXTURES / f"case-detail-{state}.json")["payload"]["active_track"]["state"]
        for state in expected
        if (V4_FIXTURES / f"case-detail-{state}.json").is_file()
    }
    assert present == expected, f"missing financing states: {expected - present}"


# ------------------------------------------------------------- audit chain ----


def _chain_hash(prev_hash: str, event: dict[str, Any]) -> str:
    body = {
        "type": event["type"],
        "payload": event["payload_json"],
        "actor": event["actor"],
        "created_at": event["created_at"],
    }
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256((prev_hash + canonical).encode()).hexdigest()


def test_the_event_fixture_chain_verifies():
    """`hash = sha256(prev_hash || canonical_json(...))`, genesis = 64 zeros."""
    events = _load(V4_FIXTURES / "events.json")["payload"]
    assert events, "events.json is empty"
    prev = GENESIS_HASH
    for index, event in enumerate(events, start=1):
        assert event["seq"] == index, f"event {index}: seq is {event['seq']}"
        assert event["prev_hash"] == prev, f"event {index}: prev_hash does not link"
        assert event["hash"] == _chain_hash(prev, event), f"event {index}: hash does not verify"
        prev = event["hash"]
    assert _load(V4_FIXTURES / "chain-verify-result.json")["payload"]["valid"] is True


def test_a_tampered_event_breaks_the_chain():
    """The chain is worth something only if an edit is detectable."""
    events = _load(V4_FIXTURES / "events.json")["payload"]
    events[3]["payload_json"] = {**events[3]["payload_json"], "tampered": True}
    prev = GENESIS_HASH
    broken_at = None
    for index, event in enumerate(events, start=1):
        if event["hash"] != _chain_hash(prev, event):
            broken_at = index
            break
        prev = event["hash"]
    assert broken_at == 4, f"expected the tamper to show at seq 4, got {broken_at}"


def test_the_bid_fixture_has_three_fictional_financiers():
    """Golden rule 17: fictional aliases only, and the mock never sets the maths."""
    bids = _load(V4_FIXTURES / "bids.json")["payload"]
    assert len(bids) == 3
    aliases = {bid["financier_alias"] for bid in bids}
    assert aliases == {"Financier A", "Financier B", "Financier C"}, aliases
    for bid in bids:
        assert bid["net_amount"] != bid["discount"], "net and discount must differ"


def test_the_webhook_log_covers_duplicate_parked_and_rejected():
    """The three hardening cases the demo rehearses (docs/webhooks.md)."""
    outcomes = {d["outcome"] for d in _load(V4_FIXTURES / "webhook-deliveries.json")["payload"]}
    assert {"APPLIED", "DUPLICATE", "PARKED", "REJECTED"} <= outcomes, outcomes
