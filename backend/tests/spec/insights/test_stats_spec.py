"""Customer stats: days measured from acceptance, the sample size, and open invoices.

Every expected number is arithmetic from the task's example, written out beside
the assertion that uses it. Acceptance is the day of delivery here because no
objection was raised, and the legal due date is acceptance + the 45-day agreed
period the request states.
"""

from __future__ import annotations

from decimal import Decimal

from backend.tests.spec.insights.helpers import (
    GSTIN_STATS,
    create_case,
    customer_named,
    pay,
    profile,
)

# ---------------------------------------------------------------- examples ----

ACCEPTED = [
    # (invoice, accepted on, paid on, days after acceptance)
    # Jan 1 -> Jan 31 is 30 days.
    ("SPEC-30", "2026-01-01", "2026-01-31", 30),
    # Feb 1 -> Apr 2: Feb has 28 days in 2026, so 27 + 31 + 2 = 60 days.
    ("SPEC-60", "2026-02-01", "2026-04-02", 60),
    # Mar 1 -> May 30: 30 (March) + 30 (April) + 30 (May) = 90 days.
    ("SPEC-90", "2026-03-01", "2026-05-30", 90),
]


def test_three_paid_invoices_give_average_median_worst_and_on_time(client):
    """30, 60 and 90 days -> average 60, median 60, worst 90; due at 45 -> 1 of 3.

    (30 + 60 + 90) / 3 = 60.00
    sorted 30, 60, 90 -> median 60.00, worst 90.00
    on time means paid on or before acceptance + 45:
        Jan 31 <= Feb 15 yes; Apr 2 <= Mar 18 no; May 30 <= Apr 15 no -> 1 of 3
    1 / 3 x 100 = 33.333... -> 33.33
    """
    name = "Stats Buyer Private Limited"
    for invoice_no, accepted_on, paid_on, _days in ACCEPTED:
        case_id = create_case(
            client,
            invoice_no=invoice_no,
            delivery=accepted_on,
            principal="100000.00",
            credit_days=45,
            buyer_name=name,
            buyer_gstin=GSTIN_STATS,
        )
        pay(client, case_id, "100000.00", paid_on, key=f"pay-{invoice_no}")

    stats = customer_named(client, name)["stats"]

    assert stats["invoice_count"] == 3
    assert stats["paid_count"] == 3
    assert stats["based_on"] == 3, "the average must say how many invoices stand behind it"
    assert stats["avg_days_to_pay"] == "60.00"
    assert stats["median_days_to_pay"] == "60.00"
    assert stats["worst_days_to_pay"] == "90.00"
    assert stats["on_time_count"] == 1
    assert stats["on_time_text"] == "1 of 3 on time"
    assert stats["on_time_pct"] == "33.33"


def test_each_invoice_reports_its_own_days_to_pay(client):
    name = "Stats Series Buyer Private Limited"
    for invoice_no, accepted_on, paid_on, _days in ACCEPTED:
        case_id = create_case(
            client,
            invoice_no=invoice_no,
            delivery=accepted_on,
            principal="100000.00",
            credit_days=45,
            buyer_name=name,
            buyer_gstin=GSTIN_STATS,
        )
        pay(client, case_id, "100000.00", paid_on, key=f"series-{invoice_no}")

    customer = customer_named(client, name)
    points = {
        point["invoice_no"]: (point["days_to_pay"], point["accepted_on"], point["status"])
        for point in profile(client, customer["id"])["series"]
    }
    assert points == {
        "SPEC-30": (30, "2026-01-01", "PAID"),
        "SPEC-60": (60, "2026-02-01", "PAID"),
        "SPEC-90": (90, "2026-03-01", "PAID"),
    }


def test_two_paid_invoices_are_not_enough_history(client):
    """Two is below the product setting of three, so there is no average at all."""
    name = "Thin History Buyer Private Limited"
    for invoice_no, accepted_on, paid_on in (
        ("THIN-1", "2026-01-01", "2026-01-31"),  # 30 days
        ("THIN-2", "2026-02-01", "2026-03-13"),  # 40 days
    ):
        case_id = create_case(
            client,
            invoice_no=invoice_no,
            delivery=accepted_on,
            principal="50000.00",
            credit_days=45,
            buyer_name=name,
        )
        pay(client, case_id, "50000.00", paid_on, key=f"thin-{invoice_no}")

    stats = customer_named(client, name)["stats"]

    assert stats["paid_count"] == 2
    assert stats["based_on"] == 2
    assert stats["avg_days_to_pay"] is None
    assert stats["median_days_to_pay"] is None
    assert stats["on_time_pct"] is None
    assert "Not enough history" in stats["avg_days_to_pay_reason"]
    assert stats["min_history"] == 3


def test_a_partial_payment_keeps_the_invoice_open(client):
    """40,000 of a 100,000 invoice is a part payment: the invoice is not paid."""
    name = "Partial Payment Buyer Private Limited"
    case_id = create_case(
        client,
        invoice_no="PART-1",
        delivery="2026-06-01",
        principal="100000.00",
        credit_days=45,
        buyer_name=name,
    )
    pay(client, case_id, "40000.00", "2026-07-01", key="part-1")

    customer = customer_named(client, name)
    assert customer["stats"]["paid_count"] == 0
    assert customer["stats"]["paid_invoice_count"] == 0

    profile_body = profile(client, customer["id"])
    invoice = profile_body["invoices"][0]
    assert invoice["status"] != "PAID"
    # 100,000 - 40,000 = 60,000 still due, before any interest.
    assert Decimal(invoice["outstanding"]) >= Decimal("60000.00")


def test_days_are_measured_from_acceptance_not_the_invoice_date(client):
    """An invoice dated 10 days before delivery must still count 30 days, not 40.

    delivery + 30 days:
        2026-01-11 -> 2026-02-10
        2026-02-11 -> 2026-03-13  (Feb 2026 has 28 days: 17 + 13)
        2026-03-11 -> 2026-04-10
    Measured from the invoice date (10 days earlier) each would read 40, so an
    average of 30.00 proves the clock starts at acceptance.
    """
    name = "Acceptance Anchor Buyer Private Limited"
    rows = (
        ("ANCHOR-1", "2026-01-11", "2026-01-01", "2026-02-10"),
        ("ANCHOR-2", "2026-02-11", "2026-02-01", "2026-03-13"),
        ("ANCHOR-3", "2026-03-11", "2026-03-01", "2026-04-10"),
    )
    for invoice_no, delivery, invoice_date, paid_on in rows:
        case_id = create_case(
            client,
            invoice_no=invoice_no,
            delivery=delivery,
            invoice=invoice_date,
            principal="100000.00",
            credit_days=45,
            buyer_name=name,
        )
        pay(client, case_id, "100000.00", paid_on, key=f"anchor-{invoice_no}")

    customer = customer_named(client, name)
    stats = customer["stats"]
    assert stats["based_on"] == 3
    assert stats["avg_days_to_pay"] == "30.00", "days must run from acceptance, not the invoice"
    assert stats["worst_days_to_pay"] == "30.00"

    body = profile(client, customer["id"])
    for point in body["series"]:
        assert point["days_to_pay"] == 30
        assert point["accepted_on"] == next(
            delivery for invoice_no, delivery, _i, _p in rows if invoice_no == point["invoice_no"]
        )
        assert point["legal_due_days"] == 45
