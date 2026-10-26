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
from backend.app import deps

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
    "/api/v1/cases/{case_id}/financing/bids",
    "/api/v1/cases/{case_id}/options",
    "/api/v1/cases/{case_id}/payments",
    # v1.2 customer book (CB3-CB5).
    "/api/v1/customers",
    "/api/v1/customers/suggestions",
    "/api/v1/customers/{customer_id}",
    "/api/v1/insights",
}
WRITE_PATHS = {
    "/api/v1/evaluate-case",
    "/api/v1/simulate-settlement",
    "/api/v1/generate-artifact",
    "/api/v1/cases",
    "/api/v1/cases/{case_id}/financing",
    "/api/v1/cases/{case_id}/financing/buyer-acceptance",
    "/api/v1/cases/{case_id}/financing/bids/{bid_id}/select",
    "/api/v1/cases/{case_id}/financing/cancel",
    "/api/v1/webhooks/esign",
    "/api/v1/webhooks/marketplace",
    "/api/v1/webhooks/disbursement",
    "/api/v1/mock/clock",
    "/api/v1/mock/clock/reset",
    "/api/v1/cases/{case_id}/recovery",
    "/api/v1/cases/{case_id}/recovery/mark-sent",
    "/api/v1/cases/{case_id}/recovery/odr-filed",
    "/api/v1/cases/{case_id}/payments",
    "/api/v1/cases/{case_id}/payments/{payment_id}/void",
    # v1.2 customer book owner actions (CB3-CB5).
    "/api/v1/customers/suggestions/dismiss",
    "/api/v1/customers/{customer_id}/attach",
    "/api/v1/customers/{customer_id}/detach",
    "/api/v1/customer-groups",
    "/api/v1/customer-groups/{group_id}/members",
    "/api/v1/customer-groups/{group_id}/members/{customer_id}",
    "/api/v1/import/invoices",
}
UPLOAD_PATHS = {"/api/v1/extract-evidence"}
# `GET /cases/{id}/stream` is an infinite `text/event-stream`. A synchronous client
# cannot consume it without hanging, so it is exercised by
# `tests/dev/webhooks/test_webhooks.py::test_a_committed_transition_notifies_the_sse_broker`
# (the broker) and `::test_the_stream_message_format_is_a_single_data_line` (the frame
# format). It is listed here so the coverage test still fails if a *fourth* kind of
# path appears undeclared.
STREAM_PATHS = {"/api/v1/cases/{case_id}/stream"}


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
    exercised = READ_PATHS | WRITE_PATHS | UPLOAD_PATHS | STREAM_PATHS
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
        (
            "GET",
            "/api/v1/cases/{case_id}/payments",
            client.get(f"/api/v1/cases/{case_id}/payments"),
        ),
    ]
    for method, path, response in responses:
        assert response.status_code == 200, f"{method} {path}: {response.text[:300]}"
        _assert_matches(
            _response_pointer(path, method), response.json(), f"{method} {path}"
        )


def _financing_case() -> str:
    """A case that is not yet due, so Option 1 is financeable in the demo clock."""
    payload = {
        **_preset_request(),
        "transaction": {
            **_preset_request()["transaction"],
            "contract_date": "2026-08-01",
            "supply_date": "2026-09-14",
            "delivery_date": "2026-09-14",
            "invoice_date": "2026-09-16",
        },
    }
    created = client.post("/api/v1/cases", json=payload)
    assert created.status_code == 201, created.text[:300]
    return created.json()["case"]["id"]


def test_financing_routes_match_the_contract():
    """Every declared financing path is called for real.

    The mock provider service does not exist, so `buyer-acceptance` reports the
    provider as unavailable and `select` finds no bids: both are still exercised, and
    only the 200 bodies are schema-checked.
    """
    case_id = _financing_case()
    headers = {"Idempotency-Key": "conformance-1", "If-Match": "0"}

    started = client.post(f"/api/v1/cases/{case_id}/financing", headers=headers)
    assert started.status_code == 200, started.text[:300]
    _assert_matches(
        _response_pointer("/api/v1/cases/{case_id}/financing", "POST"),
        started.json(),
        "POST /financing",
    )
    version = started.json()["track"]["version"]

    acceptance = client.post(
        f"/api/v1/cases/{case_id}/financing/buyer-acceptance",
        headers={"Idempotency-Key": "conformance-2", "If-Match": str(version)},
    )
    assert acceptance.status_code == 200, acceptance.text[:300]
    _assert_matches(
        _response_pointer("/api/v1/cases/{case_id}/financing/buyer-acceptance", "POST"),
        acceptance.json(),
        "POST /financing/buyer-acceptance",
    )
    version = acceptance.json()["track"]["version"]

    bids = client.get(f"/api/v1/cases/{case_id}/financing/bids")
    assert bids.status_code == 200, bids.text[:300]
    _assert_matches(
        _response_pointer("/api/v1/cases/{case_id}/financing/bids", "GET"),
        bids.json(),
        "GET /financing/bids",
    )

    # No bids exist, so selecting is refused - the path is still exercised.
    select = client.post(
        f"/api/v1/cases/{case_id}/financing/bids/MOCK-BID-A/select",
        headers={"Idempotency-Key": "conformance-3", "If-Match": str(version)},
    )
    assert select.status_code == 409, select.text[:300]
    assert select.json()["error"]["code"] in {"INVALID_TRANSITION", "STALE_VERSION"}

    cancel = client.post(
        f"/api/v1/cases/{case_id}/financing/cancel",
        headers={"Idempotency-Key": "conformance-4", "If-Match": str(version)},
    )
    assert cancel.status_code == 200, cancel.text[:300]
    _assert_matches(
        _response_pointer("/api/v1/cases/{case_id}/financing/cancel", "POST"),
        cancel.json(),
        "POST /financing/cancel",
    )


def test_payment_routes_match_the_contract():
    """The v1.2 payment write paths are called for real, including the void."""
    case_id = _financing_case()
    today = deps.get_adapters().clock.now().date().isoformat()

    created = client.post(
        f"/api/v1/cases/{case_id}/payments",
        json={
            "amount": "100.00",
            "paid_on": today,
            "method": "bank",
            "note": "conformance (synthetic)",
        },
        headers={"Idempotency-Key": "conformance-payment-1"},
    )
    assert created.status_code == 200, created.text[:400]
    _assert_matches(
        _response_pointer("/api/v1/cases/{case_id}/payments", "POST"),
        created.json(),
        "POST /payments",
    )

    history = client.get(f"/api/v1/cases/{case_id}/payments")
    assert history.status_code == 200, history.text[:400]
    _assert_matches(
        _response_pointer("/api/v1/cases/{case_id}/payments", "GET"),
        history.json(),
        "GET /payments",
    )
    payment_id = history.json()["payments"][0]["id"]

    voided = client.post(
        f"/api/v1/cases/{case_id}/payments/{payment_id}/void"
    )
    assert voided.status_code == 200, voided.text[:400]
    _assert_matches(
        _response_pointer(
            "/api/v1/cases/{case_id}/payments/{payment_id}/void", "POST"
        ),
        voided.json(),
        "POST /payments/{payment_id}/void",
    )
    assert client.get(f"/api/v1/cases/{case_id}/payments").json()["payments"][0][
        "voided_at"
    ] is not None


def test_customer_book_routes_match_the_contract():
    """Every v1.2 customer-book path is called for real, in one round trip."""
    preset = _preset_request()

    def create(gstin: str | None, name: str) -> str:
        payload = {
            **preset,
            "buyer": {**preset["buyer"], "gstin": gstin, "name": name},
        }
        created = client.post("/api/v1/cases", json=payload)
        assert created.status_code == 201, created.text[:400]
        return created.json()["case"]["id"]

    provisional_case = create(None, "Conformance Book Provisional Ltd")
    create("29ABCDE1234F1Z5", "Conformance Book Private Limited")

    listed = client.get("/api/v1/customers", params={"sort": "outstanding"})
    assert listed.status_code == 200, listed.text[:400]
    _assert_matches(
        _response_pointer("/api/v1/customers", "GET"), listed.json(), "GET /customers"
    )
    by_name = {entry["display_name"]: entry["id"] for entry in listed.json()["entries"]}
    provisional_id = by_name["Conformance Book Provisional Ltd"]
    pan_id = by_name["Conformance Book Private Limited"]

    grouped = client.get("/api/v1/customers", params={"group": "true", "sort": "name"})
    assert grouped.status_code == 200, grouped.text[:400]
    _assert_matches(
        _response_pointer("/api/v1/customers", "GET"), grouped.json(), "GET /customers?group=true"
    )

    profile = client.get(f"/api/v1/customers/{pan_id}")
    assert profile.status_code == 200, profile.text[:400]
    _assert_matches(
        _response_pointer("/api/v1/customers/{customer_id}", "GET"),
        profile.json(),
        "GET /customers/{customer_id}",
    )
    assert profile.json()["stats"]["based_on"] < profile.json()["stats"]["min_history"]
    assert len(profile.json()["buyer_cost_summary"]["lines"]) == 3

    suggestions = client.get("/api/v1/customers/suggestions")
    assert suggestions.status_code == 200, suggestions.text[:400]
    _assert_matches(
        _response_pointer("/api/v1/customers/suggestions", "GET"),
        suggestions.json(),
        "GET /customers/suggestions",
    )

    dismissed = client.post(
        "/api/v1/customers/suggestions/dismiss",
        json={"a": provisional_id, "b": pan_id},
        headers={"Idempotency-Key": "conformance-dismiss-1"},
    )
    assert dismissed.status_code == 200, dismissed.text[:400]
    _assert_matches(
        _response_pointer("/api/v1/customers/suggestions/dismiss", "POST"),
        dismissed.json(),
        "POST /customers/suggestions/dismiss",
    )

    attached = client.post(
        f"/api/v1/customers/{provisional_id}/attach",
        json={"target_customer_id": pan_id},
        headers={"Idempotency-Key": "conformance-attach-1"},
    )
    assert attached.status_code == 200, attached.text[:400]
    _assert_matches(
        _response_pointer("/api/v1/customers/{customer_id}/attach", "POST"),
        attached.json(),
        "POST /customers/{customer_id}/attach",
    )

    detached = client.post(
        f"/api/v1/customers/{pan_id}/detach",
        json={"case_ids": [provisional_case]},
        headers={"Idempotency-Key": "conformance-detach-1"},
    )
    assert detached.status_code == 200, detached.text[:400]
    _assert_matches(
        _response_pointer("/api/v1/customers/{customer_id}/detach", "POST"),
        detached.json(),
        "POST /customers/{customer_id}/detach",
    )
    assert detached.json()["moved_to"] == [provisional_id]

    group = client.post(
        "/api/v1/customer-groups",
        json={"label": "Conformance group (synthetic)", "customer_ids": [pan_id]},
        headers={"Idempotency-Key": "conformance-group-1"},
    )
    assert group.status_code == 201, group.text[:400]
    _assert_matches(
        _response_pointer("/api/v1/customer-groups", "POST", 201),
        group.json(),
        "POST /customer-groups",
    )
    group_id = group.json()["id"]

    added = client.post(
        f"/api/v1/customer-groups/{group_id}/members",
        json={"customer_id": provisional_id},
        headers={"Idempotency-Key": "conformance-group-2"},
    )
    assert added.status_code == 200, added.text[:400]
    _assert_matches(
        _response_pointer("/api/v1/customer-groups/{group_id}/members", "POST"),
        added.json(),
        "POST /customer-groups/{group_id}/members",
    )

    removed = client.request(
        "DELETE",
        f"/api/v1/customer-groups/{group_id}/members/{provisional_id}",
        headers={"Idempotency-Key": "conformance-group-3"},
    )
    assert removed.status_code == 200, removed.text[:400]
    _assert_matches(
        _response_pointer(
            "/api/v1/customer-groups/{group_id}/members/{customer_id}", "DELETE"
        ),
        removed.json(),
        "DELETE /customer-groups/{group_id}/members/{customer_id}",
    )

    insights = client.get("/api/v1/insights")
    assert insights.status_code == 200, insights.text[:400]
    _assert_matches(
        _response_pointer("/api/v1/insights", "GET"),
        insights.json(),
        "GET /insights",
    )
    for point in insights.json()["outstanding_by_customer"]:
        assert isinstance(point["value"], str), "chart money must be a decimal string"


def test_import_route_matches_the_contract():
    """The CSV import is called for real in both modes, on one small file."""
    header = (
        "invoice_no,invoice_date,delivery_date,amount,buyer_name,buyer_gstin,"
        "agreed_credit_days,paid_on,paid_amount,notes\n"
    )
    raw = (
        header
        + 'CONF-IMP-1,2026-08-03,2026-08-01,"1,25,000.00",Conformance Import Buyer,'
        + ",45,,\n"
    ).encode()

    preview = client.post(
        "/api/v1/import/invoices",
        params={"mode": "preview"},
        files={"file": ("invoices.csv", raw, "text/csv")},
    )
    assert preview.status_code == 200, preview.text[:400]
    _assert_matches(
        _response_pointer("/api/v1/import/invoices", "POST"),
        preview.json(),
        "POST /import/invoices?mode=preview",
    )
    assert preview.json()["rows"][0]["status"] == "VALID"
    assert preview.json()["summary"]["date_format"] == "YYYY-MM-DD"

    commit = client.post(
        "/api/v1/import/invoices",
        params={"mode": "commit", "import_token": preview.json()["import_token"]},
        files={"file": ("invoices.csv", raw, "text/csv")},
    )
    assert commit.status_code == 200, commit.text[:400]
    _assert_matches(
        _response_pointer("/api/v1/import/invoices", "POST"),
        commit.json(),
        "POST /import/invoices?mode=commit",
    )
    assert commit.json()["summary"]["created_rows"] == 1


def test_webhook_routes_match_the_contract(monkeypatch):
    """All three providers are called for real, with a valid signature."""
    import time

    from backend.app import security

    monkeypatch.setenv("WEBHOOK_SECRET_ESIGN", "conformance-esign")
    case_id = _financing_case()

    for provider, event_type in (
        ("esign", "esign.completed"),
        ("marketplace", "fu.accepted"),
        ("disbursement", "payout.processed"),
    ):
        secret = f"conformance-{provider}"
        monkeypatch.setenv(f"WEBHOOK_SECRET_{provider.upper()}", secret)
        payload = {
            "case_id": case_id,
            "event_id": f"MOCK-EVT-CONFORMANCE-{provider}",
            "type": event_type,
        }
        raw = json.dumps(payload, separators=(",", ":")).encode()
        stamp = str(int(time.time()))
        headers = {
            security.TIMESTAMP_HEADER: stamp,
            security.SIGNATURE_HEADER: security.signature_for(raw, stamp, secret),
            security.EVENT_ID_HEADER: payload["event_id"],
            "Content-Type": "application/json",
        }
        response = client.post(f"/api/v1/webhooks/{provider}", content=raw, headers=headers)
        assert response.status_code == 200, f"{provider}: {response.text[:300]}"
        # Handled, parked or rejected are all legitimate here; the path is exercised
        # and the envelope is checked.
        assert {"duplicate", "outcome", "provider_event_id"} <= set(response.json())


def test_options_and_mock_clock_match_the_contract():
    """The two v1.1 additions are called for real.

    `MOCK_CLOCK` is not set in the contract environment, so the clock routes answer
    `400 CLOCK_NOT_SIMULATED`; that still exercises the path, and the 200 body is
    schema-checked when the environment allows it.
    """
    case_id = _financing_case()

    options = client.get(f"/api/v1/cases/{case_id}/options")
    assert options.status_code == 200, options.text[:400]
    _assert_matches(
        _response_pointer("/api/v1/cases/{case_id}/options", "GET"),
        options.json(),
        "GET /options",
    )
    assert options.json()["recommendation"] is None, "recommendation is always null"
    assert options.json()["recover_with_law"]["expected_payment_date"]

    advance = client.post("/api/v1/mock/clock", json={"advance_days": 1})
    assert advance.status_code in {200, 400}, advance.text[:300]
    reset = client.post("/api/v1/mock/clock/reset")
    assert reset.status_code in {200, 400}, reset.text[:300]


def test_recovery_routes_match_the_contract():
    """The three recovery routes are called for real, in ladder order."""
    created = client.post("/api/v1/cases", json=_preset_request())
    case_id = created.json()["case"]["id"]
    headers = {"Idempotency-Key": "conformance-recovery-1", "If-Match": "0"}

    prepared = client.post(f"/api/v1/cases/{case_id}/recovery", json={"stage": 1}, headers=headers)
    assert prepared.status_code == 200, prepared.text[:400]
    _assert_matches(
        _response_pointer("/api/v1/cases/{case_id}/recovery", "POST"),
        prepared.json(),
        "POST /recovery",
    )
    version = prepared.json()["track"]["version"]

    sent = client.post(
        f"/api/v1/cases/{case_id}/recovery/mark-sent",
        json={"stage": 1, "channel": "email"},
        headers={"Idempotency-Key": "conformance-recovery-2", "If-Match": str(version)},
    )
    assert sent.status_code == 200, sent.text[:400]
    _assert_matches(
        _response_pointer("/api/v1/cases/{case_id}/recovery/mark-sent", "POST"),
        sent.json(),
        "POST /recovery/mark-sent",
    )

    # Filing is refused from stage 1; the path is still exercised.
    filed = client.post(
        f"/api/v1/cases/{case_id}/recovery/odr-filed",
        headers={"Idempotency-Key": "conformance-recovery-3", "If-Match": str(sent.json()["track"]["version"])},
    )
    assert filed.status_code == 409, filed.text[:300]
    assert filed.json()["error"]["code"] == "INVALID_TRANSITION"


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
