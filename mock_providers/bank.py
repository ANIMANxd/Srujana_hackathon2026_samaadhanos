"""Mock bank: a payout with a MOCK UTR, announced by a signed webhook.

The UTR is `MOCK`-prefixed so a screenshot can never be mistaken for a real bank
reference, and no real money exists anywhere in this service.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from mock_providers import signer
from mock_providers.delivery import service
from mock_providers.state import Payout, store

router = APIRouter(prefix="/payouts", tags=["bank"])


def api_url() -> str:
    base = os.environ.get("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    return f"{base}/api/v1/webhooks/disbursement"


def _dates() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class PayoutIn(BaseModel):
    amount: str
    unit_id: str | None = None
    currency: str = "INR"


@router.post("")
def create_payout(payload: PayoutIn, background: BackgroundTasks) -> dict:
    scenario = os.environ.get("MOCK_SCENARIO", "happy_path")
    payout_ref = signer.new_id("PAYOUT")
    failed = scenario == "payout_failed_then_succeeds"

    payout = Payout(
        payout_ref=payout_ref,
        amount=payload.amount,
        status="FAILED" if failed else "PROCESSED",
        utr=None if failed else signer.new_id("MOCKUTR"),
        settled_at=None if failed else _dates(),
    )
    store.payouts[payout_ref] = payout

    background.add_task(
        service.deliver,
        "payout.failed" if failed else "payout.processed",
        {
            "case_id": os.environ.get("MOCK_LAST_CASE_ID"),
            "payout_ref": payout_ref,
            "amount": payout.amount,
            "utr": payout.utr,
        },
        api_url(),
        "disbursement",
    )
    return payout.as_dict()


@router.get("/{payout_ref}")
def get_payout(payout_ref: str) -> dict:
    payout = store.payouts.get(payout_ref)
    if payout is None:
        raise HTTPException(status_code=404, detail="Unknown payout")
    return payout.as_dict()
