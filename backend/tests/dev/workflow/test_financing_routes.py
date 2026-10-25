"""The financing routes: preconditions, transitions, idempotency and the race.

The provider *service* does not exist, so the adapters are fakes from `conftest.py`.
What is under test here is the route contract: the two required headers, the
transition legality, the audit trail, and that two racing selects cannot both win.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from backend.store import db as store_db
from backend.store.models import Track
from backend.workflow import financing_sm, tracks
from backend.workflow.transitions import available_actions

from .conftest import TRACK_ID, make_bids

FINANCING = "/api/v1/cases/{case_id}/financing"
ACCEPTANCE = "/api/v1/cases/{case_id}/financing/buyer-acceptance"
BIDS = "/api/v1/cases/{case_id}/financing/bids"
SELECT = "/api/v1/cases/{case_id}/financing/bids/{bid_id}/select"
CANCEL = "/api/v1/cases/{case_id}/financing/cancel"


def _headers(version: int = 0, key: str = "key-1") -> dict[str, str]:
    return {"Idempotency-Key": key, "If-Match": str(version)}


def _start(client: TestClient, case_id: str, **overrides) -> dict:
    response = client.post(FINANCING.format(case_id=case_id), headers=overrides.pop("headers", _headers(0)))
    assert response.status_code == 200, response.text[:400]
    return response.json()


def _accept(client: TestClient, case_id: str, version: int) -> dict:
    response = client.post(ACCEPTANCE.format(case_id=case_id), headers=_headers(version, key=f"accept-{version}"))
    assert response.status_code == 200, response.text[:400]
    return response.json()


def _to_bids_available(client: TestClient, case_id: str, marketplace) -> dict:
    """Drive the track to BIDS_AVAILABLE with the fake marketplace."""
    started = _start(client, case_id)
    return _accept(client, case_id, started["track"]["version"])


# --------------------------------------------------------- preconditions ----


def test_a_missing_idempotency_key_is_400(client, case_id):
    response = client.post(FINANCING.format(case_id=case_id), headers={"If-Match": "0"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "MISSING_IDEMPOTENCY_KEY"


def test_a_missing_if_match_is_400(client, case_id):
    response = client.post(FINANCING.format(case_id=case_id), headers={"Idempotency-Key": "k"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "MISSING_IF_MATCH"


def test_a_non_numeric_if_match_is_400(client, case_id):
    response = client.post(
        FINANCING.format(case_id=case_id),
        headers={"Idempotency-Key": "k", "If-Match": "version-one"},
    )
    assert response.status_code == 400


def test_the_same_key_with_a_different_request_is_409(client, case_id, open_case_id):
    """The key scopes to (route, case): reusing it on another case is a conflict."""
    first = client.post(FINANCING.format(case_id=case_id), headers=_headers(0, key="dup"))
    assert first.status_code == 200

    # Same key, same case: a replay of the stored response, not a conflict.
    replay = client.post(FINANCING.format(case_id=case_id), headers=_headers(0, key="dup"))
    assert replay.status_code == 200
    assert replay.json() == first.json()

    # Same key, different case: the recorded body no longer matches.
    conflict = client.post(FINANCING.format(case_id=open_case_id), headers=_headers(0, key="dup"))
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"


def test_a_replay_does_not_open_a_second_track(client, case_id):
    client.post(FINANCING.format(case_id=case_id), headers=_headers(0, key="same"))
    replay = client.post(FINANCING.format(case_id=case_id), headers=_headers(0, key="same"))
    assert replay.status_code == 200

    with store_db.session_scope() as session:
        rows = session.exec(__import__("sqlmodel").select(Track).where(Track.case_id == case_id)).all()
    assert len(rows) == 1, "a replay must never create a second track"


# ------------------------------------------------------------- transitions ----


def test_starting_financing_opens_a_track_in_financeable(client, open_case_id):
    body = _start(client, open_case_id)
    assert body["track"]["kind"] == "FINANCING"
    assert body["track"]["state"] == "FINANCEABLE"
    assert body["track"]["version"] == 2, "created at 1, transitioned to 2"
    assert body["reasons"] == []
    assert "request_buyer_acceptance" in body["detail"]["available_actions"]


def test_a_not_financeable_case_returns_the_reasons(client, case_id):
    """The shipped presets are all overdue, so this is the real refusal path.

    A refusal is a 200 with reasons, not an error: the owner asked a question and
    gets an answer, and Option 2 is untouched.
    """
    response = client.post(FINANCING.format(case_id=case_id), headers=_headers(0))
    assert response.status_code == 200, response.text[:400]
    body = response.json()

    assert body["track"]["state"] == "NOT_FINANCEABLE"
    assert body["reasons"], "a refusal must say why"
    assert body["reasons"][0]["code"] == "OVERDUE"
    assert body["detail"]["available_actions"] == ["switch_to_recovery"], (
        "Option 2 must still be offered"
    )
    assert body["detail"]["latest_evaluation"] is not None, "Option 2 numbers stay on screen"


def test_starting_twice_is_a_conflict(client, open_case_id):
    _start(client, open_case_id)
    again = client.post(FINANCING.format(case_id=open_case_id), headers=_headers(0, key="other"))
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "TRACK_ALREADY_ACTIVE"


def test_a_stale_if_match_yields_409_with_the_current_state(client, open_case_id):
    _start(client, open_case_id)
    stale = client.post(ACCEPTANCE.format(case_id=open_case_id), headers=_headers(0, key="stale"))
    assert stale.status_code == 409
    body = stale.json()["error"]
    assert body["code"] == "STALE_VERSION"
    assert body["details"]["current_version"] == 2
    assert body["details"]["current_state"] == "FINANCEABLE"


def test_buyer_acceptance_walks_the_track_to_bids_available(client, open_case_id, marketplace):
    marketplace.bids = make_bids(valid_until=datetime(2026, 10, 26, 9, 0, tzinfo=UTC))
    body = _to_bids_available(client, open_case_id, marketplace)
    assert body["track"]["state"] == "BIDS_AVAILABLE", body
    assert "select_bid" in body["detail"]["available_actions"]


def test_buyer_rejection_ends_the_financing_option(client, open_case_id, marketplace):
    marketplace.acceptance_status = "REJECTED"
    started = _start(client, open_case_id)
    body = _accept(client, open_case_id, started["track"]["version"])
    assert body["track"]["state"] == "BUYER_DECLINED"
    assert body["detail"]["available_actions"] == ["switch_to_recovery", "cancel_financing"]


def test_bids_are_listed_when_available(client, open_case_id, marketplace):
    marketplace.bids = make_bids(valid_until=datetime(2026, 10, 26, 9, 0, tzinfo=UTC))
    _to_bids_available(client, open_case_id, marketplace)

    listed = client.get(BIDS.format(case_id=open_case_id))
    assert listed.status_code == 200
    bids = listed.json()["bids"]
    assert len(bids) == 3
    assert {bid["financier_alias"] for bid in bids} == {"Financier A", "Financier B", "Financier C"}


def test_an_invalid_transition_names_the_state_and_the_allowed_events(client, open_case_id):
    _start(client, open_case_id)
    response = client.post(
        SELECT.format(case_id=open_case_id, bid_id="MOCK-BID-A"), headers=_headers(2, key="early")
    )
    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "INVALID_TRANSITION"
    assert error["details"]["state"] == "FINANCEABLE"
    assert "select_bid" not in error["details"]["allowed_events"]
    assert error["message"], "the message must be plain English"


def test_cancel_ends_the_track(client, open_case_id):
    started = _start(client, open_case_id)
    response = client.post(
        CANCEL.format(case_id=open_case_id), headers=_headers(started["track"]["version"], key="cancel")
    )
    assert response.status_code == 200
    assert response.json()["track"]["state"] == "CANCELLED"


# --------------------------------------------------------------- select ----


def test_selecting_a_bid_creates_a_session_and_a_template_document(client, open_case_id, marketplace, esign):
    marketplace.bids = make_bids(valid_until=datetime(2026, 10, 26, 9, 0, tzinfo=UTC))
    available = _to_bids_available(client, open_case_id, marketplace)

    response = client.post(
        SELECT.format(case_id=open_case_id, bid_id="MOCK-BID-B"),
        headers=_headers(available["track"]["version"], key="select-1"),
    )
    assert response.status_code == 200, response.text[:500]
    body = response.json()

    assert body["track"]["state"] == "AWAITING_ESIGN"
    assert body["esign_session"]["session_id"].startswith("MOCK-")
    assert body["consent_document"]["watermark"] == "TEMPLATE"
    assert len(body["consent_document"]["sha256"]) == 64
    assert esign.created == [body["consent_document"]["sha256"]], (
        "the provider must be asked to sign exactly the document that was hashed"
    )
    assert body["consent_document"]["pdf_base64"], "the DEMO consent PDF must be produced"


def test_the_consent_document_is_a_watermarked_template(config=None):
    """The document text itself carries the TEMPLATE watermark and fictional parties."""
    from decimal import Decimal

    from backend.artifacts.financing_consent import ConsentInputs, build_consent_markdown

    markdown = build_consent_markdown(
        ConsentInputs(
            case_id="01JAV4E7K3M9Q2R5T8V0W1XCZD",
            invoice_no="INV-0042",
            supplier_name="Sample Supplies Pvt Ltd (synthetic)",
            buyer_name="Sample Buyer Corp (synthetic)",
            financier_alias="Financier B",
            accepted_amount=Decimal("1250000.00"),
            annual_rate=Decimal("8.00"),
            discount=Decimal("1095.89"),
            fee=Decimal("1250.00"),
            net_amount=Decimal("1247654.11"),
            tenor_days=4,
            due_date="2026-10-29",
            bid_id="MOCK-BID-B",
            esign_session_id="MOCK-ESIGN-0001",
        )
    )
    assert "TEMPORARY" not in markdown
    assert "DEMO TEMPLATE" in markdown
    assert "Financier B (fictional)" in markdown
    assert "no legal effect" in markdown
    assert "No Aadhaar number is collected" in markdown
    assert "OQ-10" in markdown, "the doc must not claim a financier can enforce MSMED rights"


def test_an_expired_bid_cannot_be_selected(client, open_case_id, marketplace):
    marketplace.bids = make_bids(valid_until=datetime(2026, 10, 24, 9, 0, tzinfo=UTC))
    available = _to_bids_available(client, open_case_id, marketplace)

    response = client.post(
        SELECT.format(case_id=open_case_id, bid_id="MOCK-BID-B"),
        headers=_headers(available["track"]["version"], key="expired"),
    )
    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "INVALID_TRANSITION"
    assert "expired" in error["message"]
    assert error["details"]["state"] == "BIDS_AVAILABLE"


def test_an_unknown_bid_is_404(client, open_case_id, marketplace):
    marketplace.bids = make_bids(valid_until=datetime(2026, 10, 26, 9, 0, tzinfo=UTC))
    available = _to_bids_available(client, open_case_id, marketplace)
    response = client.post(
        SELECT.format(case_id=open_case_id, bid_id="MOCK-BID-ZZZ"),
        headers=_headers(available["track"]["version"], key="unknown"),
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "BID_NOT_FOUND"


# ---------------------------------------------------------------- the race ----


def test_two_concurrent_bid_selects_produce_one_200_and_one_409(client, open_case_id, marketplace):
    """The scenario the optimistic lock exists for.

    Two clients hold the same `If-Match: 1`. Whichever UPDATE lands first wins; the
    other's WHERE clause matches nothing, so it is told the current state instead of
    silently overwriting a signature.
    """
    marketplace.bids = make_bids(valid_until=datetime(2026, 10, 26, 9, 0, tzinfo=UTC))
    available = _to_bids_available(client, open_case_id, marketplace)
    version = available["track"]["version"]

    results: list[int] = []
    barrier = threading.Barrier(2)
    lock = threading.Lock()

    def select(key: str) -> None:
        with TestClient(client.app) as worker:
            barrier.wait(timeout=10)
            response = worker.post(
                SELECT.format(case_id=open_case_id, bid_id="MOCK-BID-B"),
                headers=_headers(version, key=key),
            )
            with lock:
                results.append(response.status_code)

    threads = [
        threading.Thread(target=select, args=(f"race-{index}",)) for index in range(2)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert sorted(results) == [200, 409], f"expected exactly one winner and one loser, got {results}"

    with store_db.session_scope() as session:
        rows = session.exec(__import__("sqlmodel").select(Track).where(Track.case_id == open_case_id)).all()
    assert len(rows) == 1
    assert rows[0].state == "AWAITING_ESIGN"
    assert rows[0].version == version + 1, "exactly one transition was applied"


# ---------------------------------------------------------------- audit ----


def test_every_transition_appends_an_event_with_its_actor(client, open_case_id, marketplace):
    marketplace.bids = make_bids(valid_until=datetime(2026, 10, 26, 9, 0, tzinfo=UTC))
    available = _to_bids_available(client, open_case_id, marketplace)
    client.post(
        SELECT.format(case_id=open_case_id, bid_id="MOCK-BID-B"),
        headers=_headers(available["track"]["version"], key="audit"),
    )

    events = client.get(f"/api/v1/cases/{open_case_id}/events").json()
    types = [event["type"] for event in events]
    assert types[0] == "case.created"
    assert "track.created" in types
    assert "financing.check_financeability" in types
    assert "financing.buyer_accepted" in types
    assert types[-1] == "financing.select_bid"

    actors = {event["type"]: event["actor"] for event in events}
    assert actors["financing.select_bid"] == "USER"
    assert actors["financing.buyer_accepted"] == "PROVIDER_MOCK", (
        "an event the provider caused must not be attributed to the user"
    )

    assert client.get(f"/api/v1/cases/{open_case_id}/events/verify").json()["valid"] is True
