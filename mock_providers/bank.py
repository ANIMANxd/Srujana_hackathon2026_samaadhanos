"""Mock bank (architecture_v4 section 7.3).

A payout is scheduled **only when both** `esign.completed` and `bid.accepted` are
known for the same case. That ordering is the point: money moves after the signature
and the accepted bid, never before.

`amount` is whatever the API sent when it accepted the bid — this service never
computes a discount, a fee or a net amount, so a simulation cannot introduce a money
bug. The UTR is `MOCKUTR<digits>`, which cannot be mistaken for a real reference.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from mock_providers.delivery import service
from mock_providers.state import Payout, store

router = APIRouter(prefix="/payouts", tags=["bank"])


def api_url() -> str:
    base = os.environ.get("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    return f"{base}/api/v1/webhooks/disbursement"


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _delay() -> float:
    try:
        return float(os.environ.get("MOCK_PAYOUT_DELAY_S", "5"))
    except ValueError:
        return 5.0


class PayoutIn(BaseModel):
    amount: str
    unit_id: str | None = None
    currency: str = "INR"


def note_esign(case_id: str, background: BackgroundTasks) -> None:
    """Record that the signature is done, and release the payout if the bid is too."""
    state = store.payout_triggers.setdefault(case_id, {})
    state["esign"] = True
    _maybe_pay(case_id, background)


def note_bid_accepted(case_id: str, amount: str, bid_id: str, background: BackgroundTasks) -> None:
    """Record the accepted bid and the amount the API sent, then maybe pay."""
    state = store.payout_triggers.setdefault(case_id, {})
    state["bid"] = True
    state["amount"] = amount
    state["bid_id"] = bid_id
    _maybe_pay(case_id, background)


def _maybe_pay(case_id: str, background: BackgroundTasks) -> None:
    state = store.payout_triggers.get(case_id) or {}
    if not (state.get("esign") and state.get("bid")):
        return
    if state.get("scheduled"):
        return  # both triggers can arrive in either order; pay once
    state["scheduled"] = True

    payout_id = f"MOCK_PAYOUT_{abs(hash(case_id)) % 10**10:010d}"
    scenario = store.scenarios.get(case_id) or os.environ.get("MOCK_SCENARIO", "happy_path")
    failing = scenario == "payout_failed_then_succeeds"
    utr = None if failing else store.next_utr()
    settled_at = None if failing else _now()

    payout = Payout(
        payout_ref=payout_id,
        amount=str(state.get("amount", "0.00")),
        status="FAILED" if failing else "PROCESSED",
        utr=utr,
        settled_at=settled_at,
        case_id=case_id,
    )
    store.payouts[payout_id] = payout

    background.add_task(
        service.deliver_after,
        _delay(),
        "payout.failed" if failing else "payout.processed",
        {
            "case_id": case_id,
            "payout_id": payout_id,
            "payout_ref": payout_id,
            "amount": payout.amount,
            "currency": "INR",
            "utr": utr,
            "settled_at": settled_at,
        },
        api_url(),
        "disbursement",
    )


@router.get("/{payout_ref}")
def get_payout(payout_ref: str) -> dict:
    payout = store.payouts.get(payout_ref)
    if payout is None:
        raise HTTPException(status_code=404, detail="Unknown payout")
    return payout.as_dict()


@router.get("")
def list_payouts() -> dict:
    return {"payouts": [payout.as_dict() for payout in store.payouts.values()]}


@router.post("")
def create_payout_manual(payload: PayoutIn, background: BackgroundTasks) -> dict:
    """Judge-console escape hatch: force a payout without the two triggers.

    Documented as a manual override so the demo can show the disbursement webhook
    without replaying the whole flow. The real path is `_maybe_pay`.
    """
    case_id = "manual"
    store.payout_triggers[case_id] = {"esign": True, "bid": True, "amount": payload.amount}
    _maybe_pay(case_id, background)
    payout = next(
        (item for item in store.payouts.values() if item.case_id == case_id), None
    )
    if payout is None:  # pragma: no cover - _maybe_pay always creates one
        raise HTTPException(status_code=500, detail="Payout was not scheduled")
    return payout.as_dict()
