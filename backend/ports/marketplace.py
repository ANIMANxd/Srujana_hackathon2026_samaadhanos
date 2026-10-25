"""Financing marketplace port (architecture_v4 section 6).

The important fact this interface encodes: **the buyer must accept the factoring
unit before financiers bid**. There is no method that skips acceptance, because
that is not how TReDS works (architecture_v4 section 0).

Bids come back as contract `Bid` models. Their discount, fee and net are computed
by `backend/finance/`, never by the provider — a mock must not be able to introduce
a maths bug.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Protocol, runtime_checkable

from backend.app.schemas_v4 import Bid


@dataclass(frozen=True)
class FactoringUnitIn:
    """The invoice as registered on the marketplace."""

    invoice_no: str
    buyer_gstin: str | None
    amount: Decimal
    due_date: date
    currency: str = "INR"


@dataclass(frozen=True)
class FactoringUnitRef:
    """The marketplace's identifier for a registered unit (`MOCK`-prefixed in mock mode)."""

    unit_id: str


@dataclass(frozen=True)
class AcceptanceRequest:
    """A request that the buyer accept the unit. The buyer acts in their own login."""

    unit_id: str
    requested_at: datetime


@dataclass(frozen=True)
class AcceptanceStatus:
    """`status` is PENDING, ACCEPTED, REJECTED or EXPIRED."""

    unit_id: str
    status: str
    decided_at: datetime | None = None


@dataclass(frozen=True)
class BidAcceptance:
    """The supplier accepted a bid; the receivable now belongs to the financier."""

    unit_id: str
    bid_id: str
    accepted_at: datetime


@runtime_checkable
class FinancingMarketplace(Protocol):
    """A TReDS-style marketplace, or a labelled simulation of one."""

    simulated: bool

    def register_invoice(self, inv: FactoringUnitIn, idem_key: str) -> FactoringUnitRef:
        """Register the unit. Idempotent on `invoice_no + buyer_gstin`."""
        ...

    def request_buyer_acceptance(self, ref: FactoringUnitRef) -> AcceptanceRequest:
        """Ask the buyer to accept. Nothing moves until they do."""
        ...

    def get_acceptance(self, ref: FactoringUnitRef) -> AcceptanceStatus:
        """Poll the buyer's decision."""
        ...

    def open_bidding(self, ref: FactoringUnitRef, window: timedelta) -> None:
        """Open the bid window for an accepted unit."""
        ...

    def list_bids(self, ref: FactoringUnitRef) -> list[Bid]:
        """Bids received so far, priced by `backend/finance/`."""
        ...

    def accept_bid(
        self, ref: FactoringUnitRef, bid_id: str, idem_key: str, amount: str | None = None
    ) -> BidAcceptance:
        """Accept a bid. Idempotent on `idem_key`.

        `amount` is the net the API computed with `backend/finance`. It is passed
        through so the provider can schedule a payout for the right figure without
        ever computing one itself.
        """
        ...
