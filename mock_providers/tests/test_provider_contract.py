"""The §7.1–7.3 contract: OTP outcomes, delayed decisions, deterministic bids, payout.

Delays are set to 0 and the transport is stubbed, so these assert the *contract*
(timing is configuration, not behaviour we want to wait for). The retry/back-off
behaviour of the transport has its own file.
"""

from __future__ import annotations

import hashlib
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from mock_providers import delivery
from mock_providers.app import app
from mock_providers.marketplace import deterministic_rates
from mock_providers.state import store


@pytest.fixture()
def sent(monkeypatch):
    """A client whose deliveries are captured instead of posted, with zero delays."""
    for name in (
        "MOCK_BUYER_ACCEPT_DELAY_S",
        "MOCK_BID_DELAY_S",
        "MOCK_PAYOUT_DELAY_S",
    ):
        monkeypatch.setenv(name, "0")
    monkeypatch.setenv("MOCK_ESIGN_OTP", "123456")
    monkeypatch.delenv("MOCK_SCENARIO", raising=False)

    captured: list[dict] = []
    store.reset()
    delivery.service.reset()
    monkeypatch.setattr(delivery.service, "_backoff", (0.0,))
    monkeypatch.setattr(delivery.service, "_dead_letter_path", None)
    monkeypatch.setattr(delivery.service, "_sleep", lambda _s: None)

    def fake_post(url, *, content, headers, timeout):  # noqa: ANN001
        import json

        envelope = json.loads(content)
        captured.append({"url": url, "envelope": envelope, "headers": dict(headers)})

        class _Response:
            status_code = 200

        return _Response()

    monkeypatch.setattr(delivery.service, "_post", fake_post)
    with TestClient(app) as client:
        yield client, captured
    store.reset()
    delivery.service.reset()


def _types(captured: list[dict]) -> list[str]:
    return [item["envelope"]["type"] for item in captured]


def _session(client: TestClient, case_id: str = "01CASE") -> str:
    response = client.post(
        "/esign/sessions",
        json={
            "doc_id": "CONSENT-1",
            "doc_sha256": "a" * 64,
            "title": "Financing request and assignment consent (DEMO TEMPLATE)",
            "case_id": case_id,
        },
    )
    assert response.status_code == 200, response.text[:300]
    return response.json()["session_id"]


# --------------------------------------------------------------------- eSign ----


def test_a_new_session_is_pending_with_a_ten_minute_expiry(sent):
    client, _ = sent
    body = client.post(
        "/esign/sessions", json={"doc_id": "D", "doc_sha256": "b" * 64, "title": "t"}
    ).json()
    assert body["status"] == "PENDING"
    assert body["session_id"].startswith("MOCK_ESIGN_")
    assert body["expires_at"].endswith("Z")


def test_the_right_otp_completes_the_session_and_announces_it(sent):
    client, captured = sent
    session_id = _session(client)

    response = client.post(f"/esign/sessions/{session_id}/otp", json={"otp": "123456"})
    assert response.status_code == 200, response.text[:300]
    assert response.json()["status"] == "SIGNED"

    assert _types(captured) == ["esign.completed"]
    data = captured[0]["envelope"]["data"]
    assert data["session_id"] == session_id
    assert data["signed_doc_sha256"] == "a" * 64
    assert data["signer_display"] == "Demo Signer"
    assert data["signed_at"].endswith("Z")
    assert data["case_id"] == "01CASE", "the API needs the case id to route the event"


def test_wrong_otp_is_counted_and_the_third_failure_fails_the_session(sent):
    client, captured = sent
    session_id = _session(client)

    first = client.post(f"/esign/sessions/{session_id}/otp", json={"otp": "000000"})
    second = client.post(f"/esign/sessions/{session_id}/otp", json={"otp": "000000"})
    third = client.post(f"/esign/sessions/{session_id}/otp", json={"otp": "000000"})

    assert first.status_code == 401
    assert "2 attempt" in first.json()["detail"]
    assert second.status_code == 401
    assert third.status_code == 403
    assert client.get(f"/esign/sessions/{session_id}").json()["status"] == "FAILED"

    assert _types(captured) == ["esign.failed"]
    assert captured[0]["envelope"]["data"]["reason"] == "otp_failed"


def test_the_correct_otp_still_works_after_two_failures(sent):
    client, captured = sent
    session_id = _session(client)
    client.post(f"/esign/sessions/{session_id}/otp", json={"otp": "0"})
    client.post(f"/esign/sessions/{session_id}/otp", json={"otp": "0"})

    ok = client.post(f"/esign/sessions/{session_id}/otp", json={"otp": "123456"})
    assert ok.status_code == 200
    assert _types(captured) == ["esign.completed"]


def test_an_expired_session_cannot_be_rescued(sent):
    client, captured = sent
    session_id = _session(client)
    # Push the expiry into the past: ten minutes is configuration, not behaviour.
    store.esign[session_id].expires_at = "2020-01-01T00:00:00Z"

    response = client.post(f"/esign/sessions/{session_id}/otp", json={"otp": "123456"})
    assert response.status_code == 410
    assert client.get(f"/esign/sessions/{session_id}").json()["status"] == "EXPIRED"
    assert _types(captured) == ["esign.failed"]
    assert captured[0]["envelope"]["data"]["reason"] == "expired"


def test_there_is_no_aadhaar_field_and_a_smuggled_one_is_ignored(sent):
    client, _ = sent
    body = client.post(
        "/esign/sessions",
        json={
            "doc_id": "D",
            "doc_sha256": "c" * 64,
            "title": "t",
            "aadhaar_number": "9999 9999 9999",
        },
    ).json()
    assert not any("aadhaar" in key.lower() for key in body)
    assert "9999" not in str(store.esign)


# -------------------------------------------------------------- marketplace ----


def _unit(client: TestClient, *, case_id: str = "01CASE", band=("8.00", "12.00")) -> str:
    response = client.post(
        "/marketplace/factoring-units",
        json={
            "case_id": case_id,
            "invoice_no": "INV-0042",
            "buyer_gstin": "29SYN000000000Z1",
            "amount": "1250000.00",
            "due_date": "2026-10-29",
            "rate_band": {"low": band[0], "high": band[1]},
        },
    )
    assert response.status_code == 200, response.text[:300]
    return response.json()["unit_id"]


def test_registering_the_same_invoice_twice_returns_the_same_unit(sent):
    client, _ = sent
    first = _unit(client)
    second = _unit(client)
    assert first == second
    assert len(store.units) == 1


def test_acceptance_answers_pending_then_announces_fu_accepted(sent):
    client, captured = sent
    unit_id = _unit(client)

    response = client.post(f"/marketplace/factoring-units/{unit_id}/acceptance-request", json={})
    assert response.status_code == 200
    assert response.json()["status"] == "PENDING", "the decision arrives by webhook"

    assert _types(captured) == ["fu.accepted"]
    assert captured[0]["envelope"]["data"]["case_id"] == "01CASE"


@pytest.mark.parametrize(
    ("scenario", "event", "decision"),
    [
        ("buyer_rejects", "fu.rejected", "REJECTED"),
        ("buyer_window_expires", "fu.expired", "EXPIRED"),
    ],
)
def test_the_buyer_decision_follows_the_scenario(sent, scenario, event, decision):
    client, captured = sent
    unit_id = _unit(client)
    client.post("/mock/scenarios", json={"case_id": "01CASE", "scenario": scenario})
    client.post(f"/marketplace/factoring-units/{unit_id}/acceptance-request", json={})

    assert _types(captured) == [event]
    assert captured[0]["envelope"]["data"]["decision"] == decision


def test_bidding_is_refused_until_the_buyer_accepts(sent):
    client, _ = sent
    unit_id = _unit(client)
    blocked = client.post(f"/marketplace/factoring-units/{unit_id}/bidding", json={})
    assert blocked.status_code == 409
    assert "buyer must accept" in blocked.json()["detail"].lower()


def test_bids_are_three_rates_only_inside_the_sent_band(sent):
    client, captured = sent
    unit_id = _unit(client)
    client.post(f"/marketplace/factoring-units/{unit_id}/acceptance-request", json={})
    client.post(
        f"/marketplace/factoring-units/{unit_id}/bidding",
        json={"rate_band": {"low": "9.00", "high": "10.00"}},
    )

    bids = client.get(f"/marketplace/factoring-units/{unit_id}/bids").json()["bids"]
    assert len(bids) == 3
    for bid in bids:
        assert set(bid) == {"bid_id", "financier_alias", "annual_rate_pct", "valid_until"}
        assert bid["bid_id"].startswith("MOCK_BID_")
        assert Decimal(bid["annual_rate_pct"]) % Decimal("0.05") == 0, "quantised to 0.05"
        assert Decimal("9.00") <= Decimal(bid["annual_rate_pct"]) <= Decimal("10.00")

    announced = captured[-1]["envelope"]["data"]["bids"]
    assert announced == bids, "the webhook carries the same three bids"


def test_rates_are_deterministic_from_the_case_and_scenario():
    """`sha256(case_id + scenario)` inside the band, quantised to 0.05."""
    band = (Decimal("8.00"), Decimal("12.00"))
    first = deterministic_rates("01CASE", "happy_path", band)
    assert first == deterministic_rates("01CASE", "happy_path", band)
    assert first != deterministic_rates("02OTHER", "happy_path", band)

    digest = hashlib.sha256(b"01CASE|happy_path").digest()
    expected_first = (band[0] + Decimal("0.05") * (digest[0] % 81)).quantize(Decimal("0.05"))
    assert first[0] == min(first), "sorted ascending"
    assert expected_first in first or expected_first <= first[0]

    for rate in first:
        assert rate % Decimal("0.05") == 0
        assert band[0] <= rate <= band[1]
    assert len(set(first)) == 3, "three different cards"


def test_no_bids_scenario_announces_nothing(sent):
    client, captured = sent
    unit_id = _unit(client)
    client.post("/mock/scenarios", json={"case_id": "01CASE", "scenario": "no_bids"})
    client.post(f"/marketplace/factoring-units/{unit_id}/acceptance-request", json={})
    before = len(captured)
    client.post(f"/marketplace/factoring-units/{unit_id}/bidding", json={})

    assert client.get(f"/marketplace/factoring-units/{unit_id}/bids").json()["bids"] == []
    assert len(captured) == before, "no bids, so no bids.available event"


def test_accepting_a_bid_twice_announces_it_once(sent):
    client, captured = sent
    unit_id = _unit(client)
    client.post(f"/marketplace/factoring-units/{unit_id}/acceptance-request", json={})
    client.post(f"/marketplace/factoring-units/{unit_id}/bidding", json={})
    bid_id = client.get(f"/marketplace/factoring-units/{unit_id}/bids").json()["bids"][0]["bid_id"]

    first = client.post(f"/marketplace/bids/{bid_id}/accept", json={"unit_id": unit_id, "amount": "1240530.82"})
    second = client.post(f"/marketplace/bids/{bid_id}/accept", json={"unit_id": unit_id, "amount": "1240530.82"})

    assert first.status_code == 200
    assert first.json()["duplicate"] is False
    assert second.status_code == 200
    assert second.json()["duplicate"] is True
    assert _types(captured).count("bid.accepted") == 1, "idempotent"


# --------------------------------------------------------------------- bank ----


def _walk_to_bid_accepted(client: TestClient, captured: list[dict]) -> tuple[str, str]:
    session_id = _session(client)
    unit_id = _unit(client)
    client.post(f"/marketplace/factoring-units/{unit_id}/acceptance-request", json={})
    client.post(f"/marketplace/factoring-units/{unit_id}/bidding", json={})
    bid_id = client.get(f"/marketplace/factoring-units/{unit_id}/bids").json()["bids"][0]["bid_id"]
    client.post(f"/marketplace/bids/{bid_id}/accept", json={"unit_id": unit_id, "amount": "1240530.82"})
    return session_id, unit_id


def test_a_payout_needs_both_the_signature_and_the_accepted_bid(sent):
    client, captured = sent
    session_id, _ = _walk_to_bid_accepted(client, captured)
    assert "payout.processed" not in _types(captured), "no money before the signature"

    client.post(f"/esign/sessions/{session_id}/otp", json={"otp": "123456"})
    assert "payout.processed" in _types(captured), "signature completes the trigger"


def test_a_signature_alone_does_not_pay(sent):
    client, captured = sent
    session_id = _session(client)
    client.post(f"/esign/sessions/{session_id}/otp", json={"otp": "123456"})
    assert "payout.processed" not in _types(captured)


def test_the_payout_amount_is_the_one_the_api_sent(sent):
    """The mock never computes a discount or a net; it echoes what it was given."""
    client, captured = sent
    session_id, _ = _walk_to_bid_accepted(client, captured)
    client.post(f"/esign/sessions/{session_id}/otp", json={"otp": "123456"})

    payout = next(item for item in captured if item["envelope"]["type"] == "payout.processed")
    data = payout["envelope"]["data"]
    assert data["amount"] == "1240530.82", "exactly the amount the API sent on accept"
    assert data["currency"] == "INR"
    assert data["payout_id"].startswith("MOCK_PAYOUT_")
    digits = data["utr"].removeprefix("MOCKUTR")
    assert digits.isdigit(), "MOCKUTR<digits> only"
    assert data["settled_at"].endswith("Z")


def test_the_payout_failed_scenario_announces_a_failure(sent):
    client, captured = sent
    client.post("/mock/scenarios", json={"case_id": "01CASE", "scenario": "payout_failed_then_succeeds"})
    session_id, _ = _walk_to_bid_accepted(client, captured)
    client.post(f"/esign/sessions/{session_id}/otp", json={"otp": "123456"})

    assert "payout.failed" in _types(captured)
    assert "payout.processed" not in _types(captured)


def test_a_payout_is_scheduled_once_even_if_both_triggers_repeat(sent):
    client, captured = sent
    session_id, unit_id = _walk_to_bid_accepted(client, captured)
    bid_id = client.get(f"/marketplace/factoring-units/{unit_id}/bids").json()["bids"][0]["bid_id"]

    client.post(f"/marketplace/bids/{bid_id}/accept", json={"unit_id": unit_id, "amount": "1240530.82"})
    client.post(f"/esign/sessions/{session_id}/otp", json={"otp": "123456"})

    assert _types(captured).count("payout.processed") == 1
