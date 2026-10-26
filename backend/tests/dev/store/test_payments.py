"""Payments are recorded as Decimal/TEXT and voided, never deleted."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlmodel import Session, select

from backend.store import customers
from backend.store.audit import verify_chain
from backend.store.models import Event, Payment

AT = datetime(2026, 10, 26, 9, 0, tzinfo=UTC)


def _types(session: Session, case_id: str) -> list[str]:
    return [
        row.type
        for row in session.exec(
            select(Event).where(Event.case_id == case_id).order_by(Event.seq)
        ).all()
    ]


def test_a_payment_roundtrips_as_decimal_text_and_is_audited(session: Session, case):
    payment = customers.record_payment(
        session,
        case_id=case.id,
        amount=Decimal("125000.00"),
        paid_on=date(2026, 10, 1),
        method="bank",
        note="NEFT from buyer",
        at=AT,
    )

    assert isinstance(payment.amount, Decimal)
    assert str(payment.amount) == "125000.00"
    assert payment.method == "bank"
    assert payment.voided_at is None

    raw = session.execute(
        text("SELECT amount, typeof(amount) FROM payments WHERE id = :id"),
        params={"id": payment.id},
    ).one()
    assert raw[0] == "125000.00", "scale must survive the roundtrip"
    assert raw[1] == "text", "money must be TEXT, never REAL"

    event = session.exec(
        select(Event).where(Event.case_id == case.id, Event.type == "payment.recorded")
    ).one()
    assert event.payload_json["amount"] == "125000.00"
    assert event.payload_json["payment_id"] == payment.id
    assert verify_chain(session, case.id)["ok"] is True


def test_voiding_keeps_the_row_and_is_idempotent(session: Session, case):
    payment = customers.record_payment(
        session,
        case_id=case.id,
        amount="1000.00",
        paid_on=date(2026, 10, 1),
        method="upi",
        at=AT,
    )
    event_count = len(_types(session, case.id))

    voided = customers.void_payment(session, payment_id=payment.id, reason="wrong case", at=AT)
    assert voided.voided_at is not None
    assert len(_types(session, case.id)) == event_count + 1

    again = customers.void_payment(session, payment_id=payment.id, at=AT)
    assert again.voided_at == voided.voided_at
    assert len(_types(session, case.id)) == event_count + 1, "a repeat void writes nothing"

    rows = session.exec(select(Payment).where(Payment.case_id == case.id)).all()
    assert len(rows) == 1, "a voided payment is never deleted"
    assert rows[0].voided_at is not None

    assert customers.payments_for_case(session, case.id) == rows
    assert customers.payments_for_case(session, case.id, include_voided=False) == []
    assert verify_chain(session, case.id)["ok"] is True


def test_amount_guards(session: Session, case):
    with pytest.raises(TypeError, match="never float"):
        customers.record_payment(
            session,
            case_id=case.id,
            amount=125000.1,  # type: ignore[arg-type]
            paid_on=date(2026, 10, 1),
            method="bank",
            at=AT,
        )

    with pytest.raises(ValueError, match="two decimal places"):
        customers.record_payment(
            session,
            case_id=case.id,
            amount=Decimal("100.005"),
            paid_on=date(2026, 10, 1),
            method="bank",
            at=AT,
        )

    with pytest.raises(ValueError, match="more than zero"):
        customers.record_payment(
            session,
            case_id=case.id,
            amount="0.00",
            paid_on=date(2026, 10, 1),
            method="bank",
            at=AT,
        )

    with pytest.raises(ValueError, match="Unknown payment method"):
        customers.record_payment(
            session,
            case_id=case.id,
            amount="100.00",
            paid_on=date(2026, 10, 1),
            method="card",
            at=AT,
        )

    with pytest.raises(TypeError, match="paid_on must be a date"):
        customers.record_payment(
            session,
            case_id=case.id,
            amount="100.00",
            paid_on=datetime(2026, 10, 1, 9, 0, tzinfo=UTC),  # type: ignore[arg-type]
            method="bank",
            at=AT,
        )

    with pytest.raises(LookupError, match="No case"):
        customers.record_payment(
            session,
            case_id="01JAV4E7K3M9Q2R5T8V0W1XCZF",
            amount="100.00",
            paid_on=date(2026, 10, 1),
            method="bank",
            at=AT,
        )


def test_trailing_zeros_are_accepted_and_normalised(session: Session, case):
    payment = customers.record_payment(
        session,
        case_id=case.id,
        amount="100.000",
        paid_on=date(2026, 10, 1),
        method="cash",
        at=AT,
    )
    assert str(payment.amount) == "100.00"


def test_voiding_an_unknown_payment_is_a_clear_lookup_error(session: Session):
    with pytest.raises(LookupError, match="No payment"):
        customers.void_payment(session, payment_id="01JAV4E7K3M9Q2R5T8V0W1XCZG", at=AT)
