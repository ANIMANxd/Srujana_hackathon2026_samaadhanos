"""The service's endpoints: simulation-only banner, reset, scenarios, and no Aadhaar."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from mock_providers import delivery
from mock_providers.app import app
from mock_providers.state import store


@pytest.fixture()
def client(monkeypatch, tmp_path):
    """A client whose deliveries never wait and never leave the process."""
    store.reset()
    delivery.service.reset()
    monkeypatch.setenv("MOCK_BUYER_ACCEPT_DELAY_S", "0")
    monkeypatch.setenv("MOCK_BID_DELAY_S", "0")
    monkeypatch.setenv("MOCK_PAYOUT_DELAY_S", "0")
    monkeypatch.setattr(delivery.service, "_backoff", (0.0,))
    monkeypatch.setattr(delivery.service, "_dead_letter_path", str(tmp_path / "dl.jsonl"))

    def no_post(url, *, content, headers, timeout):  # noqa: ANN001
        class _Response:
            status_code = 200

        return _Response()

    monkeypatch.setattr(delivery.service, "_post", no_post)
    with TestClient(app) as active:
        yield active
    store.reset()
    delivery.service.reset()


def _create_unit(client: TestClient, invoice: str = "INV-0042") -> str:
    response = client.post(
        "/marketplace/factoring-units",
        json={"invoice_no": invoice, "buyer_gstin": "29SYN000000000Z1", "amount": "1250000.00", "due_date": "2026-10-29"},
    )
    assert response.status_code == 200, response.text[:300]
    return response.json()["unit_id"]


def test_every_response_is_labelled_simulation(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.headers["X-Simulation"] == "true"
    assert response.json()["simulation"] == "true"


def test_the_banner_says_the_required_sentence(client):
    banner = client.get("/mock/banner").json()["banner"]
    assert "SIMULATION ONLY" in banner
    assert "Fictional names" in banner
    assert "No real money" in banner
    assert "no real signatures" in banner
    assert "no Aadhaar data" in banner


def test_the_esign_session_has_no_aadhaar_field(client):
    response = client.post(
        "/esign/sessions",
        json={
            "doc_id": "CONSENT-1",
            "doc_sha256": "a" * 64,
            "title": "Financing request and assignment consent (DEMO TEMPLATE)",
            "signer_display": "Demo Signer",
        },
    )
    assert response.status_code == 200, response.text[:300]
    body = response.json()
    assert body["session_id"].startswith("MOCK_ESIGN_")
    assert body["status"] == "PENDING"
    assert not any("aadhaar" in key.lower() for key in body)

    # A body *claiming* an Aadhaar number is ignored, not stored.
    smuggled = client.post(
        "/esign/sessions",
        json={
            "doc_id": "CONSENT-2",
            "doc_sha256": "b" * 64,
            "title": "x",
            "aadhaar_number": "9999 9999 9999",
        },
    )
    assert smuggled.status_code == 200
    assert "aadhaar_number" not in smuggled.json()


def test_the_otp_is_checked_and_attempts_are_capped(client):
    session_id = client.post(
        "/esign/sessions", json={"doc_id": "D", "doc_sha256": "c" * 64, "title": "t"}
    ).json()["session_id"]

    wrong = client.post(f"/esign/sessions/{session_id}/complete", json={"otp": "000000"})
    assert wrong.status_code == 401
    assert "attempt" in wrong.json()["detail"]

    right = client.post(f"/esign/sessions/{session_id}/complete", json={"otp": "123456"})
    assert right.status_code == 200
    assert right.json()["status"] == "SIGNED"


def test_the_buyer_must_accept_before_bidding(client):
    unit_id = _create_unit(client)
    blocked = client.post(f"/marketplace/factoring-units/{unit_id}/bidding", json={"window_seconds": 60})
    assert blocked.status_code == 409
    assert "buyer must accept" in blocked.json()["detail"].lower()

    client.post(f"/marketplace/factoring-units/{unit_id}/acceptance-request", json={})
    allowed = client.post(f"/marketplace/factoring-units/{unit_id}/bidding", json={"window_seconds": 60})
    assert allowed.status_code == 200


def test_bids_carry_rates_only_never_money(client):
    """The mock must not ship a discount, a fee or a net amount."""
    unit_id = _create_unit(client)
    client.post(f"/marketplace/factoring-units/{unit_id}/acceptance-request", json={})
    client.post(f"/marketplace/factoring-units/{unit_id}/bidding", json={"window_seconds": 60})

    bids = client.get(f"/marketplace/factoring-units/{unit_id}/bids").json()["bids"]
    assert len(bids) == 3
    for bid in bids:
        assert set(bid) == {"bid_id", "financier_alias", "annual_rate_pct", "valid_until"}
        assert bid["bid_id"].startswith("MOCK_BID_")
        assert bid["financier_alias"] in {"Financier A", "Financier B", "Financier C"}
        assert 8.00 <= float(bid["annual_rate_pct"]) <= 12.00


def test_bids_are_deterministic_for_the_same_invoice(client):
    unit_id = _create_unit(client, "INV-SAME")
    client.post(f"/marketplace/factoring-units/{unit_id}/acceptance-request", json={})
    client.post(f"/marketplace/factoring-units/{unit_id}/bidding", json={"window_seconds": 60})
    first = [bid["annual_rate_pct"] for bid in client.get(f"/marketplace/factoring-units/{unit_id}/bids").json()["bids"]]

    client.post("/mock/reset")
    second_unit = _create_unit(client, "INV-SAME")
    client.post(f"/marketplace/factoring-units/{second_unit}/acceptance-request")
    client.post(f"/marketplace/factoring-units/{second_unit}/bidding", json={"window_seconds": 60})
    second = [bid["annual_rate_pct"] for bid in client.get(f"/marketplace/factoring-units/{second_unit}/bids").json()["bids"]]

    assert first == second, "the same invoice must always get the same rates"


def test_a_payout_carries_a_mock_utr(client):
    response = client.post("/payouts", json={"amount": "1247654.11", "unit_id": "MOCK_UNIT_1"})
    assert response.status_code == 200, response.text[:300]
    body = response.json()
    assert body["payout_ref"].startswith("MOCK_PAYOUT_")
    assert body["utr"].startswith("MOCKUTR")
    assert body["status"] == "PROCESSED"


def test_the_buyer_rejects_scenario_changes_the_outcome(client):
    unit_id = _create_unit(client)
    client.post("/mock/scenarios", json={"case_id": unit_id, "scenario": "buyer_rejects"})
    client.post(f"/marketplace/factoring-units/{unit_id}/acceptance-request", json={})
    acceptance = client.get(f"/marketplace/factoring-units/{unit_id}/acceptance").json()
    assert acceptance["status"] == "REJECTED"


def test_an_unknown_scenario_is_refused(client):
    response = client.post("/mock/scenarios", json={"case_id": "x", "scenario": "make_me_rich"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "UNKNOWN_SCENARIO"


def test_reset_clears_every_object(client):
    _create_unit(client)
    assert client.get("/mock/deliveries").json()["deliveries"] is not None
    client.post("/mock/reset")
    assert store.units == {}
    assert store.esign == {}


def test_the_service_refuses_to_start_in_production(monkeypatch):
    """A simulation must never be reachable from a production deployment."""
    import asyncio

    import mock_providers.app as module

    monkeypatch.setenv("APP_ENV", "production")

    async def enter() -> None:
        async with module._lifespan(module.app):
            pass

    with pytest.raises(SystemExit) as excinfo:
        asyncio.run(enter())
    assert excinfo.value.code == 1
