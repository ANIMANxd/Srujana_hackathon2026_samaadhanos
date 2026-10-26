"""Payment routes: record, re-evaluate, void, and the v4 financing interaction."""

from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient
from sqlmodel import select

from backend.app import deps
from backend.store import db as store_db
from backend.store.ids import new_ulid
from backend.store.models import Event, Track

ROOT = Path(__file__).resolve().parents[4]
PRESET = json.loads((ROOT / "contracts" / "fixtures" / "case_01.request.json").read_text())
BLOCKED_PRESET = json.loads(
    (ROOT / "contracts" / "fixtures" / "case_05a.request.json").read_text()
)


def _today() -> date:
    return deps.get_adapters().clock.now().date()


def _create(client: TestClient, preset: dict = PRESET) -> str:
    response = client.post("/api/v1/cases", json=preset)
    assert response.status_code == 201, response.text[:500]
    return response.json()["case"]["id"]


def _detail(client: TestClient, case_id: str) -> dict:
    response = client.get(f"/api/v1/cases/{case_id}")
    assert response.status_code == 200, response.text[:500]
    return response.json()


def _claim(client: TestClient, case_id: str) -> Decimal:
    detail = _detail(client, case_id)
    financials = detail["latest_evaluation"]["financials"]
    assert financials is not None
    return Decimal(financials["total_claim"])


def _pay(
    client: TestClient,
    case_id: str,
    amount: Decimal | str,
    *,
    key: str | None = "pay-1",
    paid_on: date | None = None,
    method: str = "bank",
    note: str = "NEFT (synthetic)",
):
    headers = {} if key is None else {"Idempotency-Key": key}
    amount_text = format(amount, "f") if isinstance(amount, Decimal) else str(amount)
    return client.post(
        f"/api/v1/cases/{case_id}/payments",
        json={
            "amount": amount_text,
            "paid_on": (paid_on or _today()).isoformat(),
            "method": method,
            "note": note,
        },
        headers=headers,
    )


def _payments(client: TestClient, case_id: str) -> dict:
    response = client.get(f"/api/v1/cases/{case_id}/payments")
    assert response.status_code == 200, response.text[:500]
    return response.json()


def _event_types(case_id: str) -> list[str]:
    with store_db.session_scope() as session:
        return [
            event.type
            for event in session.exec(
                select(Event).where(Event.case_id == case_id).order_by(Event.seq)
            ).all()
        ]


def _tracks(case_id: str) -> list[Track]:
    with store_db.session_scope() as session:
        return list(
            session.exec(select(Track).where(Track.case_id == case_id)).all()
        )


def _insert_financing_track(case_id: str, state: str = "DISBURSED") -> None:
    with store_db.session_scope() as session:
        session.add(
            Track(
                id=new_ulid(),
                case_id=case_id,
                kind="FINANCING",
                state=state,
                version=1,
            )
        )


def test_payment_roundtrip(client):
    case_id = _create(client)
    before = _claim(client, case_id)
    amount = (before / 2).quantize(Decimal("0.01"))

    response = _pay(client, case_id, amount, note="NEFT (synthetic)")

    assert response.status_code == 200, response.text[:500]
    body = response.json()
    after = Decimal(body["latest_evaluation"]["financials"]["total_claim"])
    assert after < before

    history = _payments(client, case_id)
    assert history["case_id"] == case_id
    assert history["count"] == 1
    payment = history["payments"][0]
    assert payment["amount"] == format(amount, "f")
    assert payment["paid_on"] == _today().isoformat()
    assert payment["method"] == "bank"
    assert payment["note"] == "NEFT (synthetic)"
    assert payment["voided_at"] is None
    assert any(
        item.get("reference") == f"v5:{payment['id']}"
        for item in body["case"]["input_json"].get("part_payments", [])
    )

    assert "payment.recorded" in _event_types(case_id)
    assert client.get(f"/api/v1/cases/{case_id}/events/verify").json()["valid"] is True


def test_void_restores_outstanding_and_keeps_the_row(client):
    case_id = _create(client)
    before = _claim(client, case_id)
    amount = (before / 3).quantize(Decimal("0.01"))

    paid = _pay(client, case_id, amount, key="pay-void").json()
    after_payment = Decimal(paid["latest_evaluation"]["financials"]["total_claim"])
    payment_id = _payments(client, case_id)["payments"][0]["id"]

    voided = client.post(f"/api/v1/cases/{case_id}/payments/{payment_id}/void")
    assert voided.status_code == 200, voided.text[:500]
    after_void = Decimal(
        voided.json()["latest_evaluation"]["financials"]["total_claim"]
    )
    assert after_void > after_payment
    assert after_void == before

    history = _payments(client, case_id)
    assert history["count"] == 1, "a voided payment is never deleted"
    assert history["payments"][0]["voided_at"] is not None
    assert _event_types(case_id).count("payment.voided") == 1

    # Repeating the void is a no-op and writes no second event.
    again = client.post(f"/api/v1/cases/{case_id}/payments/{payment_id}/void")
    assert again.status_code == 200
    assert _event_types(case_id).count("payment.voided") == 1


def test_future_paid_on_is_rejected(client):
    case_id = _create(client)

    response = _pay(
        client, case_id, Decimal("100.00"), paid_on=_today() + timedelta(days=1)
    )

    assert response.status_code == 422, response.text[:500]
    assert "future" in response.json()["error"]["message"].lower()
    assert _payments(client, case_id)["count"] == 0


def test_paid_on_before_the_invoice_date_is_rejected(client):
    case_id = _create(client)
    invoice_date = date.fromisoformat(_detail(client, case_id)["case"]["invoice_date"])

    response = _pay(
        client,
        case_id,
        Decimal("100.00"),
        paid_on=invoice_date - timedelta(days=1),
    )

    assert response.status_code == 422, response.text[:500]
    assert "invoice date" in response.json()["error"]["message"].lower()
    assert _payments(client, case_id)["count"] == 0


def test_a_financed_case_refuses_payments(client):
    case_id = _create(client)
    _insert_financing_track(case_id, "DISBURSED")

    response = _pay(client, case_id, Decimal("100.00"), key="pay-financed")

    assert response.status_code == 409, response.text[:500]
    assert response.json()["error"]["message"] == (
        "This invoice is financed; the buyer pays the financier."
    )
    assert _payments(client, case_id)["count"] == 0


def test_a_financed_case_refuses_a_void(client):
    case_id = _create(client)
    amount = (_claim(client, case_id) / 10).quantize(Decimal("0.01"))
    _pay(client, case_id, amount, key="pay-before-financing")
    payment_id = _payments(client, case_id)["payments"][0]["id"]
    _insert_financing_track(case_id, "SETTLED")

    response = client.post(f"/api/v1/cases/{case_id}/payments/{payment_id}/void")

    assert response.status_code == 409, response.text[:500]
    assert "financed" in response.json()["error"]["message"].lower()


def test_full_payment_closes_the_recovery_track_as_paid(client):
    case_id = _create(client)
    prepared = client.post(
        f"/api/v1/cases/{case_id}/recovery",
        json={"stage": 1},
        headers={"Idempotency-Key": "recovery-pay-1", "If-Match": "0"},
    )
    assert prepared.status_code == 200, prepared.text[:500]
    assert prepared.json()["track"]["state"] == "STAGE_1_PREPARED"

    claim = _claim(client, case_id)
    response = _pay(client, case_id, claim, key="pay-full")
    assert response.status_code == 200, response.text[:500]
    body = response.json()
    assert Decimal(body["latest_evaluation"]["financials"]["total_claim"]) == Decimal(
        "0.00"
    )
    assert body["active_track"] is None, "the closed recovery track is not active"

    tracks = _tracks(case_id)
    recovery = next(track for track in tracks if track.kind == "RECOVERY")
    assert recovery.state == "PAID"
    assert recovery.closed_at is not None

    with store_db.session_scope() as session:
        events = session.exec(
            select(Event).where(Event.case_id == case_id).order_by(Event.seq)
        ).all()
        types = [event.type for event in events]
        assert "payment.recorded" in types
        assert "recovery.paid" in types
        paid_event = next(event for event in events if event.type == "recovery.paid")
        assert paid_event.payload_json["source"] == "payment"
        assert paid_event.payload_json["to"] == "PAID"
        assert paid_event.payload_json["payment_id"] == _payments(client, case_id)[
            "payments"
        ][0]["id"]


def test_payment_idempotency_and_the_cap(client):
    case_id = _create(client)
    amount = (_claim(client, case_id) / 4).quantize(Decimal("0.01"))

    first = _pay(client, case_id, amount, key="pay-idempotent")
    second = _pay(client, case_id, amount, key="pay-idempotent")
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()
    assert _payments(client, case_id)["count"] == 1
    assert _event_types(case_id).count("payment.recorded") == 1

    conflict = _pay(client, case_id, amount + Decimal("1.00"), key="pay-idempotent")
    assert conflict.status_code == 409

    missing = _pay(client, case_id, amount, key=None)
    assert missing.status_code == 400

    over = _pay(
        client,
        case_id,
        _claim(client, case_id) + Decimal("1.00"),
        key="pay-over",
    )
    assert over.status_code == 422, over.text[:500]
    assert "above" in over.json()["error"]["message"].lower()
    assert _payments(client, case_id)["count"] == 1


def test_zero_and_negative_amounts_are_rejected(client):
    case_id = _create(client)

    zero = _pay(client, case_id, Decimal("0.00"), key="pay-zero")
    negative = _pay(client, case_id, Decimal("-1.00"), key="pay-negative")

    assert zero.status_code == 422
    assert negative.status_code == 422
    assert _payments(client, case_id)["count"] == 0


def test_unknown_case_and_payment_are_404(client):
    assert client.get("/api/v1/cases/NOPE/payments").status_code == 404
    case_id = _create(client)
    assert (
        client.post(
            f"/api/v1/cases/{case_id}/payments/NOPE/void"
        ).status_code
        == 404
    )


def test_a_case_without_engine_financials_records_the_fallback_assumption(client):
    case_id = _create(client, BLOCKED_PRESET)
    detail = _detail(client, case_id)
    assert detail["latest_evaluation"]["financials"] is None

    response = _pay(client, case_id, Decimal("100.00"), key="pay-fallback")
    assert response.status_code == 200, response.text[:500]
    types = _event_types(case_id)
    assert "payment.recorded" in types
    assert "payment.assumption" in types
