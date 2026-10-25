"""Scenario injection for the judge console.

A scenario changes what the simulation does next, so a judge can ask "what if the
buyer says no?" and get a real answer from the state machine instead of a slide.

Supported: `happy_path`, `buyer_rejects`, `buyer_window_expires`, `no_bids`,
`webhook_duplicate`, `webhook_out_of_order`, `webhook_bad_signature`,
`payout_failed_then_succeeds`.

**Disabled in production**, like every other simulation control: the whole service
refuses to start there.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from mock_providers.state import store

router = APIRouter(prefix="/mock", tags=["scenarios"])

SCENARIOS = (
    "happy_path",
    "buyer_rejects",
    "buyer_window_expires",
    "no_bids",
    "webhook_duplicate",
    "webhook_out_of_order",
    "webhook_bad_signature",
    "payout_failed_then_succeeds",
)


class ScenarioIn(BaseModel):
    case_id: str | None = None
    unit_id: str | None = None
    scenario: str


@router.get("/scenarios")
def list_scenarios() -> dict:
    return {"scenarios": list(SCENARIOS), "active": dict(store.scenarios)}


@router.post("/scenarios")
def set_scenario(payload: ScenarioIn) -> dict:
    if payload.scenario not in SCENARIOS:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown scenario {payload.scenario!r}; expected one of {list(SCENARIOS)}",
        )
    key = payload.unit_id or payload.case_id or "default"
    store.scenarios[key] = payload.scenario
    return {"active": key, "scenario": payload.scenario}
