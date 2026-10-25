"""In-memory state for the mock providers, reset by `POST /mock/reset`.

Deliberately a dict: this is a simulation, and a database would suggest durability
the demo does not need. Everything is keyed by `MOCK`-prefixed ids.

No Aadhaar field exists anywhere in this file, and none ever will (golden rule 18).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ESignSession:
    session_id: str
    status: str = "PENDING"  # PENDING | SIGNED | FAILED | EXPIRED
    signing_url: str = ""
    expires_at: str = ""
    attempts: int = 0
    case_id: str | None = None
    doc_sha256: str | None = None
    signed_doc_sha256: str | None = None
    signer_display: str | None = None
    signed_at: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "status": self.status,
            "signing_url": self.signing_url,
            "expires_at": self.expires_at,
            "signed_doc_sha256": self.signed_doc_sha256,
            "signer_display": self.signer_display,
            "signed_at": self.signed_at,
        }


@dataclass
class FactoringUnit:
    unit_id: str
    invoice_no: str
    buyer_gstin: str | None
    amount: str  # decimal string; the mock never does maths on it
    due_date: str
    case_id: str | None = None
    currency: str = "INR"
    acceptance: str = "PENDING"  # PENDING | ACCEPTED | REJECTED | EXPIRED
    bidding_open: bool = False
    bids: list[dict[str, Any]] = field(default_factory=list)
    rate_band: str | None = None  # "low|high" as sent by the API from config
    accepted_bid_id: str | None = None
    accepted_at: str | None = None
    accepted_amount: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "unit_id": self.unit_id,
            "invoice_no": self.invoice_no,
            "buyer_gstin": self.buyer_gstin,
            "amount": self.amount,
            "currency": self.currency,
            "due_date": self.due_date,
            "acceptance": self.acceptance,
            "bidding_open": self.bidding_open,
            "bids": self.bids,
        }


@dataclass
class Payout:
    payout_ref: str
    amount: str
    status: str = "PENDING"  # PENDING | PROCESSED | FAILED
    utr: str | None = None
    settled_at: str | None = None
    case_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "payout_ref": self.payout_ref,
            "payout_id": self.payout_ref,
            "status": self.status,
            "amount": self.amount,
            "currency": "INR",
            "utr": self.utr,
            "settled_at": self.settled_at,
        }


class Store:
    """Everything the simulation remembers, for one run."""

    def __init__(self) -> None:
        self.esign: dict[str, ESignSession] = {}
        self.units: dict[str, FactoringUnit] = {}
        self.payouts: dict[str, Payout] = {}
        self.idempotency: dict[str, Any] = {}
        self.scenarios: dict[str, str] = {}
        # Payout coordination: a payout is only due once BOTH the esign and the bid
        # acceptance are known for a case (architecture_v4 section 7.3).
        self.payout_triggers: dict[str, dict[str, Any]] = {}
        self.utr_counter = 0
        # The case the judge is currently driving. `POST /mock/scenarios {case_id}`
        # sets it, so every outgoing webhook can be routed even when the API adapter
        # does not send a case id of its own.
        self.active_case_id: str | None = None

    def next_utr(self) -> str:
        """`MOCKUTR<digits>`: digits only, so it can never be read as a real UTR."""
        self.utr_counter += 1
        return f"MOCKUTR{self.utr_counter:011d}"

    def reset(self) -> None:
        self.esign.clear()
        self.units.clear()
        self.payouts.clear()
        self.idempotency.clear()
        self.scenarios.clear()
        self.payout_triggers.clear()
        self.utr_counter = 0
        self.active_case_id = None


store = Store()
