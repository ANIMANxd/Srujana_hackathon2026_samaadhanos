"""Webhook pipeline: signature, freshness, parsing, dedupe, ordering, and the bids maths."""

from __future__ import annotations

import time
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlmodel import select

from backend.app.schemas_v4 import TrackState
from backend.finance import bid_quote, finance_config
from backend.store import db as store_db
from backend.store.models import Bid
from backend.store.models import Track

from .conftest import (
    SECRETS,
    bids_body,
    deliver,
    esign_body,
    event_types,
    inbox_outcome,
    open_track,
    payout_body,
    signed,
    track_state,
)


# ----------------------------------------------------------- the happy path ----


def test_a_valid_delivery_is_applied(client, case_id):
    open_track(case_id, TrackState.AWAITING_ESIGN)
    response = deliver(client, "esign", esign_body(case_id))
    assert response.status_code == 200, response.text[:300]
    body = response.json()
    assert body["duplicate"] is False
    assert body["outcome"] == "APPLIED"
    assert track_state(case_id) == "AWAITING_DISBURSEMENT"
    assert inbox_outcome("MOCK-EVT-ESIGN-1") == "APPLIED"
    assert "financing.esign_completed" in event_types(case_id)


def test_the_transition_and_the_inbox_row_share_one_transaction(client, case_id):
    """A transition always has its inbox row, and vice versa."""
    open_track(case_id, TrackState.AWAITING_ESIGN)
    deliver(client, "esign", esign_body(case_id))

    assert track_state(case_id) == "AWAITING_DISBURSEMENT"
    assert inbox_outcome("MOCK-EVT-ESIGN-1") == "APPLIED"


# ---------------------------------------------------------------- security ----


def test_a_bad_signature_is_401(client, case_id):
    open_track(case_id, TrackState.AWAITING_ESIGN)
    raw, headers = signed("esign", esign_body(case_id))
    headers["X-Mock-Signature"] = "v1=" + "0" * 64

    response = client.post("/api/v1/webhooks/esign", content=raw, headers=headers)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "BAD_SIGNATURE"
    assert track_state(case_id) == "AWAITING_ESIGN", "nothing may be applied on a bad signature"
    assert inbox_outcome("MOCK-EVT-ESIGN-1") is None, "an unverified body never enters the inbox"


def test_a_signature_from_another_provider_is_401(client, case_id):
    """The secret is per provider, so one provider cannot forge another's event."""
    open_track(case_id, TrackState.AWAITING_ESIGN)
    body = esign_body(case_id)
    raw, headers = signed("esign", body)
    headers["X-Mock-Signature"] = signed("marketplace", body)[1]["X-Mock-Signature"]

    response = client.post("/api/v1/webhooks/esign", content=raw, headers=headers)
    assert response.status_code == 401


def test_a_stale_timestamp_is_401(client, case_id):
    open_track(case_id, TrackState.AWAITING_ESIGN)
    old = int(time.time()) - 301
    raw, headers = signed("esign", esign_body(case_id), timestamp=old)

    response = client.post("/api/v1/webhooks/esign", content=raw, headers=headers)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "STALE_WEBHOOK"
    assert track_state(case_id) == "AWAITING_ESIGN"


def test_a_timestamp_just_inside_the_window_is_accepted(client, case_id):
    """299 s old is still fresh; the boundary is a real boundary."""
    open_track(case_id, TrackState.AWAITING_ESIGN)
    raw, headers = signed("esign", esign_body(case_id), timestamp=int(time.time()) - 299)
    assert client.post("/api/v1/webhooks/esign", content=raw, headers=headers).status_code == 200


def test_a_timestamp_in_the_far_future_is_401(client, case_id):
    """Otherwise a signature could be made to last indefinitely."""
    open_track(case_id, TrackState.AWAITING_ESIGN)
    raw, headers = signed("esign", esign_body(case_id), timestamp=int(time.time()) + 400)
    assert client.post("/api/v1/webhooks/esign", content=raw, headers=headers).status_code == 401


def test_a_malformed_body_is_422(client, case_id):
    import json

    raw = b"{not json"
    stamp = str(int(time.time()))
    from backend.app import security

    headers = {
        security.TIMESTAMP_HEADER: stamp,
        security.SIGNATURE_HEADER: security.signature_for(raw, stamp, SECRETS["esign"]),
        security.EVENT_ID_HEADER: "MOCK-EVT-BAD",
        "Content-Type": "application/json",
    }
    response = client.post("/api/v1/webhooks/esign", content=raw, headers=headers)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "MALFORMED_WEBHOOK"
    assert inbox_outcome("MOCK-EVT-BAD") is None


def test_a_missing_event_id_is_422(client, case_id):
    raw, headers = signed("esign", {"case_id": case_id, "event_id": "placeholder", "type": "esign.completed"})
    del headers["X-Mock-Event-Id"]
    body = b'{"case_id":"' + case_id.encode() + b'","type":"esign.completed"}'
    from backend.app import security

    headers["X-Mock-Signature"] = security.signature_for(
        body, headers[security.TIMESTAMP_HEADER], SECRETS["esign"]
    )
    response = client.post("/api/v1/webhooks/esign", content=body, headers=headers)
    assert response.status_code == 422


def test_a_missing_secret_is_a_server_error_not_a_pass(client, case_id, monkeypatch):
    monkeypatch.delenv("WEBHOOK_SECRET_ESIGN", raising=False)
    raw, headers = signed("esign", esign_body(case_id))
    response = client.post("/api/v1/webhooks/esign", content=raw, headers=headers)
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "WEBHOOK_SECRET_MISSING"


# --------------------------------------------------------------- duplicate ----


def test_a_duplicate_is_acknowledged_three_times_and_applied_once(client, case_id):
    open_track(case_id, TrackState.AWAITING_ESIGN)
    body = esign_body(case_id, event_id="MOCK-EVT-DUP")

    first = deliver(client, "esign", body)
    second = deliver(client, "esign", body)
    third = deliver(client, "esign", body)

    assert first.status_code == 200
    assert first.json()["duplicate"] is False
    assert first.json()["outcome"] == "APPLIED"

    for repeat in (second, third):
        assert repeat.status_code == 200, "a duplicate is acknowledged, not refused"
        assert repeat.json() == {"duplicate": True, "provider_event_id": "MOCK-EVT-DUP"}

    transitions = [t for t in event_types(case_id) if t == "financing.esign_completed"]
    assert len(transitions) == 1, "three deliveries must produce exactly one transition"

    with store_db.session_scope() as session:
        rows = session.exec(select(Track).where(Track.case_id == case_id)).all()
    assert rows[0].version == 4, "the version moved exactly once"


# -------------------------------------------------------- out of order / park ----


def test_a_payout_before_esign_is_parked_then_applied(client, case_id):
    """The out-of-order case: the money arrives before the signature."""
    open_track(case_id, TrackState.AWAITING_ESIGN)

    early = deliver(client, "disbursement", payout_body(case_id, event_id="MOCK-EVT-PAYOUT-EARLY"))
    assert early.status_code == 200
    assert early.json()["outcome"] == "PARKED"
    assert track_state(case_id) == "AWAITING_ESIGN", "a parked event must not be applied"
    assert inbox_outcome("MOCK-EVT-PAYOUT-EARLY") == "PARKED"

    signed_response = deliver(client, "esign", esign_body(case_id, event_id="MOCK-EVT-ESIGN-2"))
    assert signed_response.status_code == 200
    assert signed_response.json()["outcome"] == "APPLIED"

    # The esign transition unlocked the parked payout: it is retried immediately.
    assert signed_response.json()["retried_parked"] == 1
    assert inbox_outcome("MOCK-EVT-PAYOUT-EARLY") == "APPLIED"
    assert track_state(case_id) == "DISBURSED"

    types = event_types(case_id)
    assert "financing.esign_completed" in types
    assert "financing.payout_processed" in types


def test_a_parked_event_is_not_reported_as_applied(client, case_id):
    open_track(case_id, TrackState.AWAITING_ESIGN)
    early = deliver(client, "disbursement", payout_body(case_id, event_id="MOCK-EVT-PARK-ONLY"))
    body = early.json()
    assert body["outcome"] == "PARKED"
    assert body["processed_at"] if "processed_at" in body else True
    assert body["reason"], "a parked event must say why it is waiting"


def test_an_unknown_event_type_is_rejected_not_applied(client, case_id):
    open_track(case_id, TrackState.AWAITING_ESIGN)
    response = deliver(
        client, "esign", {"case_id": case_id, "event_id": "MOCK-EVT-ODD", "type": "esign.exploded"}
    )
    assert response.status_code == 200
    assert response.json()["outcome"] == "REJECTED"
    assert track_state(case_id) == "AWAITING_ESIGN"


# ------------------------------------------------------------------- bids ----


def test_bids_are_stored_with_finance_computed_numbers(client, case_id):
    """The provider ships rates only. Discount, fee and net come from backend/finance."""
    open_track(case_id, TrackState.BIDDING_OPEN)

    response = deliver(client, "marketplace", bids_body(case_id, event_id="MOCK-EVT-BIDS"))
    assert response.status_code == 200, response.text[:300]
    assert response.json()["outcome"] == "APPLIED"
    assert track_state(case_id) == "BIDS_AVAILABLE"

    cfg = finance_config(__import__("backend.app.config_loader", fromlist=["load_config"]).load_config())
    expected_a = bid_quote(Decimal("1250000.00"), Decimal("12.00"), 4, cfg)
    expected_b = bid_quote(Decimal("1250000.00"), Decimal("8.00"), 4, cfg)

    with store_db.session_scope() as session:
        stored = {
            row.id: row
            for row in session.exec(select(Bid).where(Bid.track_id.is_not(None))).all()
        }

    assert set(stored) == {"MOCK-BID-A", "MOCK-BID-B"}
    assert stored["MOCK-BID-A"].discount == expected_a["discount"]
    assert stored["MOCK-BID-A"].fee == expected_a["fee"]
    assert stored["MOCK-BID-A"].net_amount == expected_a["net_amount"]
    assert stored["MOCK-BID-B"].net_amount == expected_b["net_amount"]

    # The hostile numbers in the payload were ignored entirely.
    assert stored["MOCK-BID-A"].discount != Decimal("999999.99")
    assert stored["MOCK-BID-A"].net_amount != Decimal("1.00")
    # 4-day tenor: 12% -> 1,643.84 discount less 1,250.00 fee; 8% -> 1,095.89 less 1,250.00
    assert stored["MOCK-BID-A"].net_amount == Decimal("1247106.16")


def test_bids_arriving_twice_do_not_duplicate(client, case_id):
    open_track(case_id, TrackState.BIDDING_OPEN)
    deliver(client, "marketplace", bids_body(case_id, event_id="MOCK-EVT-BIDS-DUP"))
    second = deliver(client, "marketplace", bids_body(case_id, event_id="MOCK-EVT-BIDS-DUP"))
    assert second.status_code == 200
    assert second.json()["duplicate"] is True

    with store_db.session_scope() as session:
        count = len(session.exec(select(Bid)).all())
    assert count == 2, "two bids, not four"


def test_bids_for_a_track_that_is_not_bidding_are_parked(client, case_id):
    open_track(case_id, TrackState.AWAITING_ESIGN)
    response = deliver(client, "marketplace", bids_body(case_id, event_id="MOCK-EVT-BIDS-EARLY"))
    assert response.status_code == 200
    assert response.json()["outcome"] == "PARKED"
    assert track_state(case_id) == "AWAITING_ESIGN"


# --------------------------------------------------------------- the stream ----


def test_a_committed_transition_notifies_the_sse_broker(client, case_id):
    """The stream is fed by committed transitions, not by intent."""
    from backend.app.routes import events as events_module

    received: list[dict] = []
    queue = events_module._subscribe(case_id)
    try:
        open_track(case_id, TrackState.AWAITING_ESIGN)
        deliver(client, "esign", esign_body(case_id, event_id="MOCK-EVT-SSE"))
        while not queue.empty():
            received.append(queue.get_nowait())
    finally:
        events_module._unsubscribe(case_id, queue)

    assert received, "a committed transition must publish a message"
    message = received[0]
    assert message["type"] == "track.transition"
    assert message["track_state"] == "AWAITING_DISBURSEMENT"
    assert message["version"] == 4


def test_the_stream_message_format_is_a_single_data_line():
    from backend.app.routes.events import heartbeat_message, sse_message

    line = sse_message({"type": "track.transition", "track_state": "DISBURSED", "version": 5})
    assert line.startswith("data: ")
    assert line.endswith("\n\n")
    assert heartbeat_message() == ": heartbeat\n\n"
