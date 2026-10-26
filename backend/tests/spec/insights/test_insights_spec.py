"""Portfolio insights: concentration at the product threshold, and the 43B(h) list.

Outstanding 60 / 30 / 10 across three customers is 60% concentration for the top
one, which is at or above the 40% product threshold, so it is flagged. The
before-March list is open, overdue invoices only: a paid invoice and one that is
not due yet must never appear in it.
"""

from __future__ import annotations

from decimal import Decimal

from backend.tests.spec.insights.helpers import (
    create_case,
    customer_named,
    days_ago,
    insights,
    pay,
    profile,
    today,
)

OUTSTANDING = (
    ("CONC-60", "60000.00"),  # 60 / 100 = 60%
    ("CONC-30", "30000.00"),  # 30 / 100 = 30%
    ("CONC-10", "10000.00"),  # 10 / 100 = 10%
)


def test_top_customer_share_is_60_percent_and_flags_at_40(client):
    """60,000 + 30,000 + 10,000 = 100,000 outstanding; the top share is 60%.

    None of the three is overdue (delivery five days ago, 45-day period), so no
    interest has accrued and the outstanding figures are the principals.
    """
    for index, (invoice_no, principal) in enumerate(OUTSTANDING):
        create_case(
            client,
            invoice_no=invoice_no,
            delivery=days_ago(5),
            principal=principal,
            credit_days=45,
            buyer_name=f"Concentration Buyer {index + 1} Private Limited",
        )

    data = insights(client)

    assert data["customer_count"] == 3
    assert data["outstanding_total"] == "100000.00"
    # 60000 / 100000 x 100 = 60.00, and 60 >= the 40% product threshold.
    assert data["top_customer_share_pct"] == "60.00"
    assert data["concentration_flag"] is True

    charted = sum(
        (Decimal(point["value"]) for point in data["outstanding_by_customer"]),
        Decimal("0.00"),
    )
    assert charted == Decimal("100000.00"), "the chart must add up to the total"


def test_before_march_lists_only_open_overdue_invoices(client):
    """One open overdue, one paid, one not due -> exactly one row, the overdue one.

    delivery 60 days ago + 45 days = due 15 days ago, so that invoice is overdue.
    delivery 5 days ago  + 45 days = due 40 days from now, so that one is not due.
    The third invoice is paid in full before its due date.
    """
    name = "Timeline Buyer Private Limited"
    create_case(
        client,
        invoice_no="OVERDUE-1",
        delivery=days_ago(60),
        principal="50000.00",
        credit_days=45,
        buyer_name=name,
    )
    paid_case = create_case(
        client,
        invoice_no="PAID-1",
        delivery=days_ago(60),
        principal="40000.00",
        credit_days=45,
        buyer_name=name,
    )
    create_case(
        client,
        invoice_no="NOTDUE-1",
        delivery=days_ago(5),
        principal="30000.00",
        credit_days=45,
        buyer_name=name,
    )
    # Paid 20 days ago, which is before the due date 15 days ago, so it is paid on time.
    pay(client, paid_case, "40000.00", days_ago(20), key="before-march-paid")

    data = insights(client)
    listed = [item["invoice_no"] for item in data["before_march"]]

    assert listed == ["OVERDUE-1"], f"only open overdue invoices belong here, got {listed}"
    item = data["before_march"][0]
    assert "43B(h)" in item["note"]
    assert Decimal(item["outstanding"]) >= Decimal("50000.00")
    assert item["next_march"] > today().isoformat()

    # The same screen's own statuses: paid is PAID, the recent one is NOT_DUE.
    customer = customer_named(client, name)
    statuses = {
        invoice["invoice_no"]: invoice["status"]
        for invoice in profile(client, customer["id"])["invoices"]
    }
    assert statuses["PAID-1"] == "PAID"
    assert statuses["NOTDUE-1"] == "NOT_DUE"
    assert statuses["OVERDUE-1"] == "OVERDUE"
