"""Mock TReDS-style marketplace: buyer acceptance, then bids.

Two properties this service must keep:

- **The buyer accepts first.** `bidding` refuses until acceptance is ACCEPTED,
  because on a real marketplace nothing moves before the buyer logs in.
- **The mock never computes money.** A bid carries an annual rate and a validity
  window only; the API's `backend/finance/` turns those into discount, fee and net.
  A mock that computes rupees is a mock that can be wrong about rupees.

Financier aliases are fictional: "Financier A/B/C" (golden rule 17).
"""

from __future__ import annotations

import hashlib
import os
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from mock_providers import signer
from mock_providers.delivery import service
from mock_providers.routing import case_id_for, remember_case
from mock_providers.state import FactoringUnit, store

router = APIRouter(prefix="/marketplace", tags=["marketplace"])

FINANCIERS = ("Financier A", "Financier B", "Financier C")
RATE_BAND = (8.00, 12.00)
BID_STEP = 0.05
BID_VALID_HOURS = 24


def api_url() -> str:
    base = os.environ.get("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    return f"{base}/api/v1/webhooks/marketplace"


class FactoringUnitIn(BaseModel):
    case_id: str | None = None
    invoice_no: str
    buyer_gstin: str | None = None
    amount: str
    currency: str = "INR"
    due_date: str


class BiddingWindow(BaseModel):
    case_id: str | None = None
    window_seconds: int = 86_400


class AcceptBid(BaseModel):
    case_id: str | None = None
    unit_id: str


def _dates() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def deterministic_rates(unit: FactoringUnit) -> list[float]:
    """Three distinct rates inside the band, seeded by the invoice.

    Same invoice always yields the same bids, so a demo run is reproducible.
    """
    seed = hashlib.sha256(f"{unit.invoice_no}|{unit.buyer_gstin}".encode()).digest()
    low, high = RATE_BAND
    steps = int(round((high - low) / BID_STEP))  # 80 steps at 0.05
    picks: list[float] = []
    for index in range(3):
        offset = seed[index] % (steps + 1)
        rate = round(low + offset * BID_STEP, 2)
        while rate in picks:
            rate = round(min(high, rate + BID_STEP), 2)
        picks.append(rate)
    return sorted(picks)


def _bid_payloads(unit: FactoringUnit) -> list[dict]:
    valid_until = (datetime.now(UTC) + timedelta(hours=BID_VALID_HOURS)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    return [
        {
            "bid_id": signer.new_id("BID"),
            "financier_alias": FINANCIERS[index % len(FINANCIERS)],
            # Rate and validity only. No discount, no fee, no net amount.
            "annual_rate": f"{rate:.2f}",
            "valid_until": valid_until,
        }
        for index, rate in enumerate(deterministic_rates(unit))
    ]


@router.post("/factoring-units")
def register_unit(payload: FactoringUnitIn) -> dict:
    for unit in store.units.values():
        if unit.invoice_no == payload.invoice_no and unit.buyer_gstin == payload.buyer_gstin:
            return {"unit_id": unit.unit_id}
    unit_id = signer.new_id("UNIT")
    unit = FactoringUnit(
        unit_id=unit_id,
        invoice_no=payload.invoice_no,
        buyer_gstin=payload.buyer_gstin,
        amount=payload.amount,
        due_date=payload.due_date,
        currency=payload.currency,
    )
    remember_case(unit, payload.case_id)
    store.units[unit_id] = unit
    return {"unit_id": unit_id}


@router.post("/factoring-units/{unit_id}/acceptance-request")
def request_acceptance(unit_id: str, background: BackgroundTasks) -> dict:
    """Ask the buyer. The scenario decides whether they accept, reject or ignore it."""
    unit = store.units.get(unit_id)
    if unit is None:
        raise HTTPException(status_code=404, detail="Unknown factoring unit")

    scenario = store.scenarios.get(unit_id) or os.environ.get("MOCK_SCENARIO", "happy_path")
    if scenario == "buyer_rejects":
        unit.acceptance = "REJECTED"
        event = "fu.rejected"
    elif scenario == "buyer_window_expires":
        unit.acceptance = "EXPIRED"
        event = "fu.rejected"
    else:
        unit.acceptance = "ACCEPTED"
        event = "fu.accepted"

    background.add_task(
        service.deliver,
        event,
        {"case_id": case_id_for(unit=unit), "unit_id": unit_id, "invoice_no": unit.invoice_no},
        api_url(),
        "marketplace",
    )
    return {"unit_id": unit_id, "requested_at": _dates()}


@router.get("/factoring-units/{unit_id}/acceptance")
def get_acceptance(unit_id: str) -> dict:
    unit = store.units.get(unit_id)
    if unit is None:
        raise HTTPException(status_code=404, detail="Unknown factoring unit")
    return {"unit_id": unit_id, "status": unit.acceptance, "decided_at": None}


@router.post("/factoring-units/{unit_id}/bidding")
def open_bidding(unit_id: str, payload: BiddingWindow, background: BackgroundTasks) -> dict:
    unit = store.units.get(unit_id)
    if unit is None:
        raise HTTPException(status_code=404, detail="Unknown factoring unit")
    if unit.acceptance != "ACCEPTED":
        raise HTTPException(
            status_code=409,
            detail="The buyer must accept the invoice before financiers can bid.",
        )

    scenario = store.scenarios.get(unit_id) or os.environ.get("MOCK_SCENARIO", "happy_path")
    unit.bidding_open = True
    unit.bids = [] if scenario == "no_bids" else _bid_payloads(unit)

    if unit.bids:
        background.add_task(
            service.deliver,
            "bids.available",
            {
                "case_id": os.environ.get("MOCK_LAST_CASE_ID"),
                "unit_id": unit_id,
                "accepted_amount": unit.amount,
                "tenor_days": 30,
                "bids": unit.bids,
            },
            api_url(),
            "marketplace",
        )
    return {"unit_id": unit_id, "window_seconds": payload.window_seconds, "bids": len(unit.bids)}


@router.get("/factoring-units/{unit_id}/bids")
def list_bids(unit_id: str) -> dict:
    unit = store.units.get(unit_id)
    if unit is None:
        raise HTTPException(status_code=404, detail="Unknown factoring unit")
    return {"unit_id": unit_id, "bids": unit.bids}


@router.post("/bids/{bid_id}/accept")
def accept_bid(bid_id: str, payload: AcceptBid, background: BackgroundTasks) -> dict:
    unit = store.units.get(payload.unit_id)
    if unit is None:
        raise HTTPException(status_code=404, detail="Unknown factoring unit")
    if not any(bid["bid_id"] == bid_id for bid in unit.bids):
        raise HTTPException(status_code=404, detail="Unknown bid")

    accepted_at = _dates()
    background.add_task(
        service.deliver,
        "bid.accepted",
        {"case_id": case_id_for(unit=unit), "unit_id": unit.unit_id, "bid_id": bid_id},
        api_url(),
        "marketplace",
    )
    return {"unit_id": unit.unit_id, "bid_id": bid_id, "accepted_at": accepted_at}
