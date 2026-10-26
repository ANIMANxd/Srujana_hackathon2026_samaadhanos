"""Builders for the pure stats tests. Every figure is a round Decimal."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from backend.insights.stats import CaseSnapshot, PaymentRecord, TrackSummary

INVOICE_DATE = date(2025, 12, 1)
AS_OF = date(2026, 10, 26)


def evaluation(
    *,
    acceptance: str | None = "2026-01-10",
    due: str | None = "2026-02-09",
    interest: str = "100.00",
    total_claim: str = "1100.00",
    days_overdue: int = 0,
    ledger_payments: tuple[str, ...] = (),
) -> dict[str, Any]:
    """An engine response fragment with the fields the stats module reads."""
    return {
        "timeline": {
            "acceptance_date": acceptance,
            "due_date": due,
            "days_overdue": days_overdue,
        },
        "financials": {
            "interest_total": interest,
            "principal_outstanding": total_claim,
            "interest_outstanding": "0.00",
            "total_claim": total_claim,
            "ledger": [
                {"kind": "PAYMENT", "payment": amount} for amount in ledger_payments
            ],
        },
    }


def make_case(
    *,
    case_id: str,
    evaluation_data: dict[str, Any] | None,
    customer_id: str = "cu1",
    customer_name: str = "Acme Industries (synthetic)",
    invoice_no: str = "INV-1",
    accepted: str = "1000.00",
    invoice_date: date = INVOICE_DATE,
    track: TrackSummary | None = None,
) -> CaseSnapshot:
    return CaseSnapshot(
        case_id=case_id,
        customer_id=customer_id,
        customer_name=customer_name,
        invoice_no=invoice_no,
        invoice_date=invoice_date,
        accepted_amount=Decimal(accepted),
        evaluation=evaluation_data,
        active_track=track,
    )


def make_payment(
    *,
    payment_id: str = "p1",
    case_id: str,
    amount: str = "1000.00",
    paid_on: date = date(2026, 2, 9),
    voided_at: datetime | None = None,
) -> PaymentRecord:
    return PaymentRecord(
        payment_id=payment_id,
        case_id=case_id,
        amount=Decimal(amount),
        paid_on=paid_on,
        voided_at=voided_at,
    )


def paid_pair(
    *,
    case_id: str,
    invoice_no: str,
    acceptance: str = "2026-01-10",
    due: str = "2026-02-09",
    paid_on: date = date(2026, 2, 9),
    amount: str = "1000.00",
    interest: str = "100.00",
    total_claim: str = "1100.00",
    customer_id: str = "cu1",
    customer_name: str = "Acme Industries (synthetic)",
    invoice_date: date = INVOICE_DATE,
) -> tuple[CaseSnapshot, PaymentRecord]:
    """A fully paid invoice whose engine ledger shows the same payment."""
    case = make_case(
        case_id=case_id,
        customer_id=customer_id,
        customer_name=customer_name,
        invoice_no=invoice_no,
        accepted=amount,
        invoice_date=invoice_date,
        evaluation_data=evaluation(
            acceptance=acceptance,
            due=due,
            interest=interest,
            total_claim=total_claim,
            ledger_payments=(amount,),
        ),
    )
    payment = make_payment(
        payment_id=f"pay-{case_id}",
        case_id=case_id,
        amount=amount,
        paid_on=paid_on,
    )
    return case, payment


def open_case(
    *,
    case_id: str,
    invoice_no: str,
    acceptance: str | None = "2026-01-10",
    due: str | None = "2026-09-30",
    accepted: str = "1000.00",
    total_claim: str = "1000.00",
    interest: str = "0.00",
    customer_id: str = "cu1",
    customer_name: str = "Acme Industries (synthetic)",
    track: TrackSummary | None = None,
) -> CaseSnapshot:
    return make_case(
        case_id=case_id,
        customer_id=customer_id,
        customer_name=customer_name,
        invoice_no=invoice_no,
        accepted=accepted,
        evaluation_data=evaluation(
            acceptance=acceptance,
            due=due,
            interest=interest,
            total_claim=total_claim,
            ledger_payments=(),
        ),
        track=track,
    )
