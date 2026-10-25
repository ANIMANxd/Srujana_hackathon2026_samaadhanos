"""Mock TReDS-style marketplace (architecture_v4 section 7.2).

Three properties this service must keep:

- **The buyer accepts first.** Bidding refuses until the buyer has accepted, because
  on a real marketplace nothing moves before that login.
- **The mock never computes money.** A bid carries `bid_id`, `financier_alias`,
  `annual_rate_pct` and `valid_until` only. `backend/finance/` turns those into
  discount, fee and net, so a simulation cannot introduce a money bug.
- **Determinism.** The three rates come from `sha256(case_id + scenario)` inside the
  band the API sends from config, quantised to 0.05, so the same demo always shows
  the same numbers.

Delays (`MOCK_BUYER_ACCEPT_DELAY_S`, `MOCK_BID_DELAY_S`) exist so the API has to cope
with a provider that answers "pending" and acts later.
"""

from __future__ import annotations

import hashlib
import os
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from mock_providers import bank, signer
from mock_providers.delivery import service
from mock_providers.routing import case_id_for, remember_case
from mock_providers.state import FactoringUnit, store

router = APIRouter(prefix="/marketplace", tags=["marketplace"])

FINANCIERS = ("Financier A", "Financier B", "Financier C")
BID_VALID_HOURS = 24
RATE_STEP = Decimal("0.05")
# The band the API sends from config; this is only the fallback when it sends none.
DEFAULT_BAND = (Decimal("8.00"), Decimal("12.00"))


def api_url() -> str:
    base = os.environ.get("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    return f"{base}/api/v1/webhooks/marketplace"


def _now() -> datetime:
    return datetime.now(UTC)


def _stamp(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _delay(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except ValueError:
        return default


class RateBand(BaseModel):
    low: str
    high: str


class FactoringUnitIn(BaseModel):
    case_id: str | None = None
    invoice_no: str
    buyer_gstin: str | None = None
    amount: str
    currency: str = "INR"
    due_date: str
    rate_band: RateBand | None = None


class AcceptanceIn(BaseModel):
    case_id: str | None = None


class BiddingWindow(BaseModel):
    case_id: str | None = None
    window_seconds: int = 86_400
    rate_band: RateBand | None = None


class AcceptBid(BaseModel):
    case_id: str | None = None
    unit_id: str
    # The amount the API sends: the net it already computed. The mock never derives it.
    amount: str | None = None


def _scenario(key: str | None, unit_id: str | None = None) -> str:
    """A scenario may be set by case id or by unit id, whichever the caller knows.

    `active_case_id` is the last resort: the API's adapter does not send a case id
    with its own requests, so the case a judge activated must still be honoured.
    """
    from mock_providers.state import store as _store

    return (
        (key and _store.scenarios.get(key))
        or (unit_id and _store.scenarios.get(unit_id))
        or (_store.active_case_id and _store.scenarios.get(_store.active_case_id))
        or os.environ.get("MOCK_SCENARIO")
        or "happy_path"
    )


def deterministic_rates(case_id: str, scenario: str, band: tuple[Decimal, Decimal]) -> list[Decimal]:
    """Three distinct rates from `sha256(case_id + scenario)`, inside the band.

    Quantised to 0.05 and de-duplicated, so three cards always show three numbers.
    """
    low, high = band
    if high <= low:
        low, high = DEFAULT_BAND
    steps = int((high - low) / RATE_STEP)
    digest = hashlib.sha256(f"{case_id}|{scenario}".encode("utf-8")).digest()

    picks: list[Decimal] = []
    for index in range(3):
        offset = digest[index] % (steps + 1)
        rate = (low + RATE_STEP * offset).quantize(RATE_STEP, rounding=ROUND_HALF_UP)
        guard = 0
        while rate in picks and guard < steps:
            rate = min(high, rate + RATE_STEP)
            guard += 1
        picks.append(rate)
    return sorted(picks)


def _band(unit: FactoringUnit, override: RateBand | None) -> tuple[Decimal, Decimal]:
    raw = override or unit.rate_band
    if raw is None:
        return DEFAULT_BAND
    try:
        return (Decimal(raw.low), Decimal(raw.high))
    except Exception:  # noqa: BLE001 - a malformed band falls back rather than 500s
        return DEFAULT_BAND


def _bids(unit: FactoringUnit, override: RateBand | None) -> list[dict]:
    case_key = case_id_for(unit=unit) or unit.invoice_no
    scenario = _scenario(unit.case_id, unit.unit_id)
    rates = deterministic_rates(case_key, scenario, _band(unit, override))
    valid_until = _stamp(_now() + timedelta(hours=BID_VALID_HOURS))
    return [
        {
            "bid_id": signer.new_id("BID"),
            "financier_alias": FINANCIERS[index % len(FINANCIERS)],
            # Rate and validity only: no discount, no fee, no net amount.
            "annual_rate_pct": f"{rate:.2f}",
            "valid_until": valid_until,
        }
        for index, rate in enumerate(rates)
    ]


@router.get("/factoring-units")
def list_units() -> dict:
    """Every registered unit. Used by the judge console and the scenario harness."""
    return {"units": [unit.as_dict() for unit in store.units.values()]}


@router.post("/factoring-units")
def register_unit(payload: FactoringUnitIn) -> dict:
    """Idempotent on `invoice_no + buyer_gstin` (section 7.2)."""
    for unit in store.units.values():
        if unit.invoice_no == payload.invoice_no and unit.buyer_gstin == payload.buyer_gstin:
            remember_case(unit, payload.case_id)
            return {"unit_id": unit.unit_id}

    unit = FactoringUnit(
        unit_id=signer.new_id("UNIT"),
        invoice_no=payload.invoice_no,
        buyer_gstin=payload.buyer_gstin,
        amount=payload.amount,
        due_date=payload.due_date,
        case_id=payload.case_id,
        currency=payload.currency,
        rate_band=payload.rate_band.low + "|" + payload.rate_band.high if payload.rate_band else None,
    )
    remember_case(unit, payload.case_id)
    store.units[unit.unit_id] = unit
    return {"unit_id": unit.unit_id}


@router.post("/factoring-units/{unit_id}/acceptance-request")
def request_acceptance(
    unit_id: str, background: BackgroundTasks, payload: AcceptanceIn | None = None
) -> dict:
    """Ask the buyer, then answer the decision after a delay.

    The response is immediate and `PENDING`; the decision arrives as a webhook, which
    is what a real marketplace does. `fu.accepted`, `fu.rejected` or `fu.expired`
    depends on the active scenario.
    """
    unit = store.units.get(unit_id)
    if unit is None:
        raise HTTPException(status_code=404, detail="Unknown factoring unit")
    if payload and payload.case_id:
        remember_case(unit, payload.case_id)

    scenario = _scenario(unit.case_id, unit.unit_id)
    if scenario == "buyer_rejects":
        decision, event = "REJECTED", "fu.rejected"
    elif scenario == "buyer_window_expires":
        decision, event = "EXPIRED", "fu.expired"
    else:
        decision, event = "ACCEPTED", "fu.accepted"

    requested_at = _stamp(_now())
    background.add_task(
        service.deliver_after,
        _delay("MOCK_BUYER_ACCEPT_DELAY_S", 3.0),
        event,
        {
            "case_id": case_id_for(unit=unit),
            "unit_id": unit_id,
            "invoice_no": unit.invoice_no,
            "decision": decision,
        },
        api_url(),
        "marketplace",
    )

    # The decision is applied after the delay, so the poll reports PENDING until then.
    unit.acceptance = "PENDING"
    background.add_task(_settle_acceptance, unit_id, decision)
    return {"unit_id": unit_id, "requested_at": requested_at, "status": "PENDING"}


def _settle_acceptance(unit_id: str, decision: str) -> None:
    unit = store.units.get(unit_id)
    if unit is not None and unit.acceptance == "PENDING":
        unit.acceptance = decision


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
    if payload.case_id:
        remember_case(unit, payload.case_id)
    if unit.acceptance != "ACCEPTED":
        raise HTTPException(
            status_code=409,
            detail="The buyer must accept the invoice before financiers can bid.",
        )

    scenario = _scenario(unit.case_id, unit.unit_id)
    unit.bidding_open = True
    unit.bids = [] if scenario == "no_bids" else _bids(unit, payload.rate_band)

    if unit.bids:
        background.add_task(
            service.deliver_after,
            _delay("MOCK_BID_DELAY_S", 3.0),
            "bids.available",
            {
                "case_id": case_id_for(unit=unit),
                "unit_id": unit_id,
                "accepted_amount": unit.amount,
                "tenor_days": 30,
                "bids": unit.bids,
            },
            api_url(),
            "marketplace",
        )

    if not unit.bids:
        # Section 5.1: a closed window with zero bids is what reaches NO_BIDS.
        background.add_task(
            service.deliver_after,
            _delay("MOCK_BID_DELAY_S", 3.0),
            "bidding.closed",
            {"case_id": case_id_for(unit=unit), "unit_id": unit_id, "bid_count": 0},
            api_url(),
            "marketplace",
        )

    if scenario == "bids_expire":
        # The window closes with no bid taken. Section 5.1: this reopens bidding
        # once; a second expiry is what reaches NO_BIDS.
        background.add_task(
            service.deliver_after,
            _delay("MOCK_BID_DELAY_S", 3.0) + _delay("MOCK_EXPIRE_DELAY_S", 1.0),
            "bids.expired",
            {"case_id": case_id_for(unit=unit), "unit_id": unit_id, "bid_count": len(unit.bids)},
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
    """Idempotent: accepting the same bid twice announces it once."""
    unit = store.units.get(payload.unit_id)
    if unit is None:
        raise HTTPException(status_code=404, detail="Unknown factoring unit")
    if payload.case_id:
        remember_case(unit, payload.case_id)
    if not any(bid["bid_id"] == bid_id for bid in unit.bids):
        raise HTTPException(status_code=404, detail="Unknown bid")

    if unit.accepted_bid_id == bid_id:
        return {
            "unit_id": unit.unit_id,
            "bid_id": bid_id,
            "accepted_at": unit.accepted_at or _stamp(_now()),
            "duplicate": True,
        }

    unit.accepted_bid_id = bid_id
    unit.accepted_at = _stamp(_now())
    unit.accepted_amount = payload.amount or unit.amount

    case_id = case_id_for(unit=unit)
    background.add_task(
        service.deliver,
        "bid.accepted",
        {
            "case_id": case_id,
            "unit_id": unit.unit_id,
            "bid_id": bid_id,
            "amount": unit.accepted_amount,
        },
        api_url(),
        "marketplace",
    )
    if case_id:
        bank.note_bid_accepted(case_id, unit.accepted_amount, bid_id, background)

    return {
        "unit_id": unit.unit_id,
        "bid_id": bid_id,
        "accepted_at": unit.accepted_at,
        "duplicate": False,
    }
