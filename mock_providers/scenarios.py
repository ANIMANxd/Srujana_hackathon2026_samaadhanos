"""Scenario injection for the judge console (architecture_v4 section 7.4).

Every scenario changes what the simulation does next, so a judge can ask "what if the
buyer says no?" and get a real state-machine answer rather than a slide.

    POST /mock/scenarios        {case_id, scenario}  -> activates it for that case
    GET  /mock/scenarios/{id}                        -> what is active for that case
    GET  /mock/scenarios                             -> the whole menu

Activating a scenario also records the case as the **active case**, so outgoing
webhooks can be routed to it even when the API's adapter does not send a case id.

The expected end state of each scenario is documented in `mock_providers/README.md`
and asserted by `mock_providers/tests/test_scenarios_e2e.py`.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from mock_providers.state import store

router = APIRouter(prefix="/mock", tags=["scenarios"])

# Every scenario in section 7.4, in the document's order.
SCENARIOS: tuple[str, ...] = (
    "happy_path",
    "buyer_rejects",
    "buyer_window_expires",
    "no_bids",
    "bids_expire",
    "esign_wrong_otp",
    "esign_expires",
    "webhook_duplicate",
    "webhook_out_of_order",
    "webhook_bad_signature",
    "webhook_delayed",
    "payout_failed_then_succeeds",
    "buyer_defaults_after_disbursal",
)

# What each scenario is supposed to prove. Kept next to the list so a new scenario
# has to say what it demonstrates.
SCENARIO_NOTES: dict[str, str] = {
    "happy_path": "Buyer accepts, three bids, signed, paid.",
    "buyer_rejects": "The buyer declines on the platform; Option 1 ends, Option 2 stays.",
    "buyer_window_expires": "The acceptance window closes without a decision.",
    "no_bids": "Financeable, but no financier bids.",
    "bids_expire": "The bid window reopens exactly once after expiry.",
    "esign_wrong_otp": "Three wrong OTPs fail the signature.",
    "esign_expires": "The signing session expires before it is used.",
    "webhook_duplicate": "The same event arrives three times and is applied once.",
    "webhook_out_of_order": "The payout arrives before the signature, is parked, then applied.",
    "webhook_bad_signature": "A forged delivery is rejected and changes nothing.",
    "webhook_delayed": "A late delivery still applies when it finally lands.",
    "payout_failed_then_succeeds": "A failed payout is retried and settles.",
    "buyer_defaults_after_disbursal": "The buyer defaults after the supplier is paid.",
}


class ScenarioIn(BaseModel):
    case_id: str
    scenario: str


@router.get("/scenarios")
def list_scenarios() -> dict:
    return {
        "scenarios": list(SCENARIOS),
        "notes": dict(SCENARIO_NOTES),
        "active": dict(store.scenarios),
        "active_case_id": store.active_case_id,
    }


@router.post("/scenarios")
def set_scenario(payload: ScenarioIn) -> dict:
    if payload.scenario not in SCENARIOS:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "UNKNOWN_SCENARIO",
                    "message": (
                        f"Unknown scenario {payload.scenario!r}; expected one of "
                        f"{list(SCENARIOS)}"
                    ),
                    "details": {"scenario": payload.scenario},
                }
            },
        )
    store.scenarios[payload.case_id] = payload.scenario
    store.active_case_id = payload.case_id
    return {
        "case_id": payload.case_id,
        "scenario": payload.scenario,
        "note": SCENARIO_NOTES.get(payload.scenario, ""),
    }


@router.get("/scenarios/{case_id}")
def get_scenario(case_id: str) -> dict:
    scenario = store.scenarios.get(case_id)
    return {
        "case_id": case_id,
        "scenario": scenario or "happy_path",
        "active": scenario is not None,
        "note": SCENARIO_NOTES.get(scenario or "happy_path", ""),
    }
