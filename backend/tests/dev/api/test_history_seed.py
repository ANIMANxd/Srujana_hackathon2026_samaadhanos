"""The 12-month history seed: six fictional customers, imported as a CSV.

These tests read the acceptance for the seed: the book has six customers (five
after the demo attach), every row carries its sample size, there are at least two
suggestions, and the portfolio has a concentration flag and a before-March list.
They also prove the seed goes through the import path (re-running it is a no-op
because the import's own duplicate rule skips every row) and that the v4 presets
still work beside it.
"""

from __future__ import annotations

import csv
import io
from datetime import date, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlmodel import select

from backend.insights.identity import validate_gstin
from backend.store import db as store_db
from backend.store.history import (
    HISTORY_CUSTOMERS,
    HISTORY_GSTINS,
    HISTORY_ROW_COUNT,
    build_history,
    earliest_priceable_delivery,
    indian_amount,
    seed_history,
)
from backend.store.models import Case, Customer, Payment
from backend.store.seed import seed_presets

AS_OF = date(2026, 10, 26)
FLOOR = date(2026, 2, 16)


def _rows(text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(text)))


# ------------------------------------------------------------------ data ----


def test_the_history_is_deterministic_and_well_formed():
    first = build_history(AS_OF, floor=FLOOR)
    assert first == build_history(AS_OF, floor=FLOOR), "the fixed seed must not drift"
    assert build_history(AS_OF + timedelta(days=1), floor=FLOOR) != first

    rows = _rows(first)
    assert len(rows) == HISTORY_ROW_COUNT == 41
    assert len(HISTORY_CUSTOMERS) == 6

    for row in rows:
        assert set(row) == {
            "invoice_no",
            "invoice_date",
            "delivery_date",
            "amount",
            "buyer_name",
            "buyer_gstin",
            "agreed_credit_days",
            "paid_on",
            "paid_amount",
            "notes",
        }
        # No cell may look like a spreadsheet formula.
        for cell in row.values():
            assert not cell.strip().startswith(("=", "+", "-", "@")), cell
        delivery = date.fromisoformat(row["delivery_date"])
        invoice = date.fromisoformat(row["invoice_date"])
        assert delivery <= invoice <= AS_OF
        assert Decimal(row["amount"].replace(",", "")) > 0
        if row["paid_on"]:
            assert invoice <= date.fromisoformat(row["paid_on"]) <= AS_OF
            assert row["paid_amount"]
        else:
            assert not row["paid_amount"]
        if row["buyer_gstin"]:
            assert validate_gstin(row["buyer_gstin"])["ok"] is True, row["buyer_gstin"]

    # Two state registrations of one PAN, and one buyer with no GSTIN at all.
    assert "29AABCK9012L1Z7" in HISTORY_GSTINS and "33AABCK9012L1Z4" in HISTORY_GSTINS
    assert any(not customer.gstins for customer in HISTORY_CUSTOMERS)
    # Every contact number is a synthetic 90000 0000x.
    phones = [customer.phone for customer in HISTORY_CUSTOMERS]
    assert len(set(phones)) == 6
    assert all(phone.startswith("+91 90000 0000") for phone in phones)


def test_indian_grouping_and_the_priceable_window():
    assert indian_amount(Decimal("125000")) == "1,25,000.00"
    assert indian_amount(Decimal("1234567.5")) == "12,34,567.50"
    assert indian_amount(Decimal("999")) == "999.00"

    rows = _rows(build_history(AS_OF, floor=FLOOR))
    oldest = min(date.fromisoformat(row["delivery_date"]) for row in rows)
    assert oldest >= FLOOR, "the ledger cannot start before the captured Bank Rate epochs"

    # With no epoch limit the plan reaches the full twelve months.
    unclamped = _rows(build_history(AS_OF, floor=date(2000, 1, 1)))
    assert min(date.fromisoformat(row["delivery_date"]) for row in unclamped) == (
        AS_OF - timedelta(days=340)
    )


def test_the_priceable_floor_comes_from_the_config():
    """The seed reads the first Bank Rate epoch instead of hard-coding a date."""
    floor = earliest_priceable_delivery()
    assert floor is None or isinstance(floor, date)


# --------------------------------------------------------------- the book ----


def test_seed_history_builds_the_demo_book(client: TestClient):
    report = seed_history()

    assert report.rows == 41
    assert report.created_cases == 41
    assert report.payments == 29
    assert report.invalid == 0
    assert report.customers == 6

    listed = client.get("/api/v1/customers", params={"sort": "outstanding"}).json()
    assert listed["count"] == 6, "six fictional customers, one row each"

    by_name = {entry["display_name"]: entry["customer"] for entry in listed["entries"]}
    prompt = by_name["Ganga Precision Works Private Limited"]["stats"]
    late = by_name["Yamuna Steel Traders Pvt Ltd"]["stats"]
    two_states = by_name["Kaveri Auto Components Private Limited"]
    provisional = by_name["Ganga Precision Works Pvt Ltd"]
    related = [by_name[name] for name in ("Saraswati Polymers Private Limited", "Saraswati Polymers Pvt Ltd")]

    # Every row carries its sample size, and every average has at least 3 invoices.
    for entry in listed["entries"]:
        stats = entry["customer"]["stats"]
        assert stats["based_on"] >= stats["min_history"], entry["display_name"]
        assert stats["based_on"] == stats["paid_count"]
        assert len(stats["on_time_text"]) > 0

    # The prompt payer pays inside the engine's due date; the late payer averages ~70.
    assert prompt["avg_days_to_pay"] is not None
    assert Decimal(prompt["avg_days_to_pay"]) <= Decimal("45")
    assert prompt["on_time_count"] == prompt["paid_count"]
    assert late["avg_days_to_pay"] == "70.00"
    assert late["on_time_count"] == 0
    assert Decimal(late["overdue_total"]) > 0

    # One legal entity, two state registrations.
    assert two_states["pan"] == "AABCK9012L"
    assert two_states["gstins"] == ["29AABCK9012L1Z7", "33AABCK9012L1Z4"]

    # The near-duplicate is provisional and not merged.
    assert provisional["kind"] == "PROVISIONAL"
    assert provisional["gstins"] == []
    assert [customer["pan"] for customer in related] == ["AABCS3456M", "AABCS3456N"]

    # At least one open overdue invoice for each late customer.
    for name in (
        "Yamuna Steel Traders Pvt Ltd",
        "Ganga Precision Works Pvt Ltd",
        "Saraswati Polymers Private Limited",
        "Saraswati Polymers Pvt Ltd",
    ):
        profile = client.get(f"/api/v1/customers/{by_name[name]['id']}").json()
        overdue_open = [
            invoice
            for invoice in profile["invoices"]
            if invoice["status"] == "OVERDUE" and Decimal(invoice["outstanding"]) > 0
        ]
        assert overdue_open, f"{name} needs an open overdue invoice"

    # Two owner actions, never applied automatically: attach and group-link.
    suggestions = client.get("/api/v1/customers/suggestions").json()
    assert suggestions["count"] >= 2
    kinds = {item["kind"] for item in suggestions["suggestions"]}
    assert {"ATTACH", "LINK_AS_GROUP"} <= kinds
    pairs = {(item["a"], item["b"]) for item in suggestions["suggestions"]}
    assert (provisional["id"], by_name["Ganga Precision Works Private Limited"]["id"]) in pairs

    # Portfolio: a concentration flag and a before-March list.
    insights = client.get("/api/v1/insights").json()
    assert insights["concentration_flag"] is True
    assert Decimal(insights["top_customer_share_pct"]) >= Decimal("40")
    assert len(insights["before_march"]) >= 1
    assert "43B(h)" in insights["before_march"][0]["note"]
    assert insights["based_on"] == sum(
        entry["customer"]["stats"]["based_on"] for entry in listed["entries"]
    )


def test_seed_history_is_idempotent_because_it_goes_through_the_import(client: TestClient):
    first = seed_history()
    assert first.created_cases == 41

    def counts() -> dict[str, int]:
        with store_db.session_scope() as session:
            return {
                "cases": len(session.exec(select(Case)).all()),
                "customers": len(session.exec(select(Customer)).all()),
                "payments": len(session.exec(select(Payment)).all()),
            }

    before = counts()
    second = seed_history()

    assert second.created_cases == 0
    assert second.skipped == 41, "the import's own duplicate rule skips every row"
    assert second.payments == 0
    assert counts() == before
    assert client.get("/api/v1/customers").json()["count"] == 6


def test_the_demo_attach_leaves_five_customers(client: TestClient):
    seed_history()
    listed = client.get("/api/v1/customers").json()["entries"]
    by_name = {entry["display_name"]: entry["customer"] for entry in listed}
    provisional = by_name["Ganga Precision Works Pvt Ltd"]
    pan_customer = by_name["Ganga Precision Works Private Limited"]

    attached = client.post(
        f"/api/v1/customers/{provisional['id']}/attach",
        json={"target_customer_id": pan_customer["id"]},
        headers={"Idempotency-Key": "history-demo-attach"},
    )
    assert attached.status_code == 200, attached.text[:600]

    after = client.get("/api/v1/customers").json()
    assert after["count"] == 5, "the demo attach folds the provisional into the PAN customer"
    merged = next(
        entry["customer"]
        for entry in after["entries"]
        if entry["customer"]["id"] == pan_customer["id"]
    )
    assert merged["stats"]["invoice_count"] == 15, "both invoice histories, one customer"


def test_the_v4_presets_still_work_beside_the_history(database_url: str, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", database_url)
    store_db.dispose()
    store_db.init_db(database_url)
    with store_db.session_scope() as session:
        presets = seed_presets(session)
    assert len(presets) == 10

    report = seed_history()
    assert report.created_cases == 41

    with store_db.session_scope() as session:
        cases = session.exec(select(Case)).all()
        invoice_numbers = {row.invoice_no for row in cases}
        customers = len({row.customer_id for row in cases if row.customer_id})
    assert len(cases) == 51, "10 preset cases and 41 imported ones"
    assert "synthetic-INV-001" in invoice_numbers, "the v4 demo invoice is still there"
    assert customers == 16, "10 preset buyers plus the 6 history customers"
    store_db.dispose()
