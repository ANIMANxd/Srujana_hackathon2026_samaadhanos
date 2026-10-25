"""Store + fake providers for the workflow tests.

The mock provider *service* does not exist yet, so the adapters are replaced with
in-memory fakes. That keeps these tests about the state machine and the locking
rules, not about HTTP.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.app import deps
from backend.app.main import app
from backend.app.schemas_v4 import Bid, BidStatus, ESignSession, ESignStatus, PayoutStatus
from backend.store import db as store_db

ROOT = Path(__file__).resolve().parents[4]
PRESET = json.loads((ROOT / "contracts" / "fixtures" / "case_01.request.json").read_text())

TRACK_ID = "TRK-FIN-TEST"


class FakeClock:
    simulated = True

    def __init__(self, moment: datetime) -> None:
        self._moment = moment

    def now(self) -> datetime:
        return self._moment


class FakeMarketplace:
    """Returns three fictional bids, immediately and deterministically."""

    simulated = True

    def __init__(self) -> None:
        self.acceptance_status = "ACCEPTED"
        self.bids: list[Bid] = []
        self.bid_valid_until = datetime(2026, 10, 26, 9, 0, tzinfo=UTC)
        self.raise_unavailable = False

    def register_invoice(self, inv: Any, idem_key: str, **_):
        if self.raise_unavailable:
            from backend.ports.errors import ProviderUnavailable

            raise ProviderUnavailable("mock marketplace down")
        from backend.ports.marketplace import FactoringUnitRef

        return FactoringUnitRef(unit_id="MOCK-UNIT-1")

    def request_buyer_acceptance(self, ref, **_):
        from backend.ports.marketplace import AcceptanceRequest

        return AcceptanceRequest(unit_id=ref.unit_id, requested_at=datetime(2026, 10, 25, 9, 0, tzinfo=UTC))

    def get_acceptance(self, ref, **_):
        from backend.ports.marketplace import AcceptanceStatus

        return AcceptanceStatus(unit_id=ref.unit_id, status=self.acceptance_status)

    def open_bidding(self, ref, window, **_) -> None:
        return None

    def list_bids(self, ref, **_):
        if self.raise_unavailable:
            from backend.ports.errors import ProviderUnavailable

            raise ProviderUnavailable("mock marketplace down")
        return list(self.bids)

    def accept_bid(self, ref, bid_id: str, idem_key: str, **_):
        raise NotImplementedError


class FakeESign:
    simulated = True

    def __init__(self) -> None:
        self.created: list[str] = []

    def create_session(self, doc, signer, idem_key: str, **_):
        self.created.append(doc.doc_sha256)
        return ESignSession(
            session_id="MOCK-ESIGN-0001",
            status=ESignStatus.PENDING,
            signing_url="/mock/esign/MOCK-ESIGN-0001",
            expires_at=datetime(2026, 10, 25, 9, 10, tzinfo=UTC),
        )

    def get_session(self, session_id: str, **_):
        raise NotImplementedError


class FakeDisbursement:
    simulated = True

    def get_payout(self, payout_ref: str, **_):
        return PayoutStatus(payout_ref=payout_ref, amount=Decimal("0.00"))


@pytest.fixture()
def database_url(tmp_path) -> str:
    return f"sqlite:///{tmp_path / 'workflow.db'}"


@pytest.fixture()
def marketplace() -> FakeMarketplace:
    return FakeMarketplace()


@pytest.fixture()
def esign() -> FakeESign:
    return FakeESign()


@pytest.fixture()
def clock() -> FakeClock:
    return FakeClock(datetime.combine(date(2026, 10, 25), time(12, 0), tzinfo=UTC))


@pytest.fixture()
def client(database_url, monkeypatch, marketplace, esign, clock) -> Iterator[TestClient]:
    monkeypatch.setenv("DATABASE_URL", database_url)
    store_db.dispose()
    store_db.init_db(database_url)

    adapters = deps.Adapters(
        esign=esign,
        marketplace=marketplace,
        disbursement=FakeDisbursement(),
        clock=clock,
        ids=deps.build_adapters().ids,
        mode="mock",
    )
    monkeypatch.setattr(deps, "get_adapters", lambda: adapters)

    with TestClient(app) as active:
        yield active
    store_db.dispose()


@pytest.fixture()
def case_id(client: TestClient) -> str:
    """The as-shipped preset: 206 days overdue, so Option 1 is *not* financeable."""
    response = client.post("/api/v1/cases", json=PRESET)
    assert response.status_code == 201, response.text[:400]
    return response.json()["case"]["id"]


@pytest.fixture()
def open_case_id(client: TestClient) -> str:
    """A case that is not yet due, so Option 1 is financeable.

    The shipped presets are all overdue (that is the v3 story), so the financing happy
    path needs an invoice with a future due date: delivery 2026-09-14 + the 45-day cap
    = due 2026-10-29, four days after the demo date.
    """
    payload = {
        **PRESET,
        "transaction": {
            **PRESET["transaction"],
            "contract_date": "2026-08-01",
            "supply_date": "2026-09-14",
            "delivery_date": "2026-09-14",
            "invoice_date": "2026-09-16",
            "calculation_date": "2026-10-25",
        },
    }
    response = client.post("/api/v1/cases", json=payload)
    assert response.status_code == 201, response.text[:400]
    return response.json()["case"]["id"]


def make_bids(*, valid_until: datetime, count: int = 3) -> list[Bid]:
    rows = [
        ("MOCK-BID-A", "Financier A", Decimal("12.00"), Decimal("1643.84")),
        ("MOCK-BID-B", "Financier B", Decimal("8.00"), Decimal("1095.89")),
        ("MOCK-BID-C", "Financier C", Decimal("10.00"), Decimal("1369.86")),
    ]
    return [
        Bid(
            id=bid_id,
            track_id=TRACK_ID,
            financier_alias=alias,
            annual_rate=rate,
            discount=discount,
            fee=Decimal("1250.00"),
            net_amount=Decimal("1250000.00") - discount - Decimal("1250.00"),
            valid_until=valid_until,
            status=BidStatus.AVAILABLE,
        )
        for bid_id, alias, rate, discount in rows[:count]
    ]
