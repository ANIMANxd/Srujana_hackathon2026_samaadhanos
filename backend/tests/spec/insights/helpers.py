"""Case builders and the HTTP calls the v5 spec tests need.

Test-author rules (AGENTS.md section 3): this suite works from the task's
hand-computed examples and the published contract, never from
`backend/insights/**` or `backend/engine/**`. Every expected number below is
arithmetic written out by hand in the test that uses it.

One input is pinned deliberately: the requests carry
`config_overrides={"bank_rate_pct": ...}`. The statute config holds no Bank Rate
epoch before 2026-04-01 (CR-8), so a case accepted in January cannot be priced
without pinning a rate. Day counts, due dates and on-time results do not depend
on the rate, and pinning it keeps each oracle about the dates under test. The
config keeps the rate it ships with; nothing statutory is edited here.
"""

from __future__ import annotations

from datetime import date, timedelta

from backend.app import deps

# A rate the engine accepts as an explicit override for one request only.
PINNED_BANK_RATE = {"bank_rate_pct": "5.50"}

# Format-valid and fictional: 2 digits, 5 letters, 4 digits, 1 letter, 1, Z, 1.
# The PAN is characters 3-12, which is what makes two states one legal entity.
GSTIN_KA_ACME = "29ABCDE1234F1Z5"  # PAN ABCDE1234F
GSTIN_TN_ACME = "33ABCDE1234F1Z5"  # same PAN, Tamil Nadu
GSTIN_MH_OTHER = "27PQRSX5678K1Z3"  # PAN PQRSX5678K, a different legal entity
GSTIN_STATS = "29STATS1234A1Z5"  # PAN STATS1234A


def today() -> date:
    """The API's clock, so "overdue" and "not due yet" are measured the same way."""
    return deps.get_adapters().clock.now().date()


def days_ago(days: int) -> str:
    return (today() - timedelta(days=days)).isoformat()


def case_request(
    *,
    invoice_no: str,
    delivery: str,
    invoice: str | None = None,
    principal: str = "100000.00",
    credit_days: int | None = 45,
    buyer_name: str,
    buyer_gstin: str | None = None,
) -> dict:
    """One stored case, built from the suite's valid round-number request."""
    from backend.tests.spec.helpers import base_request

    return base_request(
        case_id=f"spec-{invoice_no}",
        buyer={"name": buyer_name, "gstin": buyer_gstin},
        transaction={
            "contract_date": None,
            "supply_date": delivery,
            "delivery_date": delivery,
            "invoice_date": invoice or delivery,
            "principal": principal,
            "written_credit_days": credit_days,
            "calculation_date": today().isoformat(),
        },
        evidence={"items": [{"kind": "INVOICE", "present": True, "ref": invoice_no}]},
        config_overrides=PINNED_BANK_RATE,
    )


def create_case(client, **kwargs) -> str:
    """POST /cases and return the server-issued case id."""
    response = client.post("/api/v1/cases", json=case_request(**kwargs))
    assert response.status_code == 201, response.text[:800]
    return response.json()["case"]["id"]


def pay(client, case_id: str, amount: str, paid_on: str, *, key: str) -> None:
    """POST a payment (the route the owner uses), asserting it was accepted."""
    response = client.post(
        f"/api/v1/cases/{case_id}/payments",
        json={
            "amount": amount,
            "paid_on": paid_on,
            "method": "bank",
            "note": "spec (synthetic)",
        },
        headers={"Idempotency-Key": key},
    )
    assert response.status_code == 200, response.text[:800]


def book(client) -> dict:
    response = client.get("/api/v1/customers", params={"sort": "name"})
    assert response.status_code == 200, response.text[:800]
    return response.json()


def customer_named(client, name: str) -> dict:
    """The one list row for this buyer, as the customer screen reads it."""
    matches = [
        entry["customer"]
        for entry in book(client)["entries"]
        if entry["kind"] == "CUSTOMER" and entry["customer"]["display_name"] == name
    ]
    assert len(matches) == 1, f"expected exactly one customer named {name!r}: {matches}"
    return matches[0]


def profile(client, customer_id: str) -> dict:
    response = client.get(f"/api/v1/customers/{customer_id}")
    assert response.status_code == 200, response.text[:800]
    return response.json()


def insights(client) -> dict:
    response = client.get("/api/v1/insights")
    assert response.status_code == 200, response.text[:800]
    return response.json()
