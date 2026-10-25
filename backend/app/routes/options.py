"""`GET /api/v1/cases/{id}/options` — the two-option comparison (contract v1.1).

This route is a thin adapter. Every number comes from somewhere else:

- Option 1 from `backend.finance` (discount, fee, net, the available/unavailable
  verdict and each blocking reason);
- Option 2's s.16 interest from the **frozen engine**, re-run at the expected
  payment date through the `interest_to_date` callable.

The route itself computes nothing, which is the point: it is the place where a
stray division would otherwise appear and quietly disagree with the module.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from backend.app import deps
from backend.app.config_loader import load_config
from backend.app.routes import cases as case_routes
from backend.app.schemas import CaseEvaluationRequest, CaseEvaluationResponse
from backend.app.schemas_v4 import OptionsResponse
from backend.engine.config import StatuteConfig
from backend.engine.evaluate import evaluate_case
from backend.finance import CaseFacts, compare_options, finance_config
from backend.store.db import session_scope
from backend.store.models import Case as CaseRow

router = APIRouter(prefix="/api/v1", tags=["options"])

# The documented default for Option 2's comparison date (architecture_v4 section 1.1:
# "default: today + 30 days, editable").
DEFAULT_EXPECTED_PAYMENT_DAYS = 30


def _interest_to_date(request: CaseEvaluationRequest, day: date) -> Decimal:
    """s.16 interest to `day`, from the existing engine.

    Only `calculation_date` moves: every other stored fact is what the owner entered,
    so the comparison cannot quietly benefit from a different input.
    """
    payload = {**request.model_dump(mode="json"), "transaction": {**request.model_dump(mode="json")["transaction"]}}
    payload["transaction"]["calculation_date"] = day.isoformat()
    engine_request = CaseEvaluationRequest.model_validate(payload)
    result: CaseEvaluationResponse = evaluate_case(
        StatuteConfig.from_dict(load_config()), engine_request
    )
    if result.financials is None:  # pragma: no cover - the demo case always evaluates
        return Decimal("0.00")
    return result.financials.interest_total


@router.get("/cases/{case_id}/options", response_model=OptionsResponse)
def get_options(
    case_id: str,
    expected_payment_date: date | None = Query(
        default=None,
        description="The date Option 2 is measured to. Defaults to as_of + 30 days.",
    ),
):
    """Both options with numbers, and never a recommendation.

    `recommendation` is `null` by construction: it is a `None` field on the model and
    a test asserts it stays that way (golden rule 20).
    """
    with session_scope() as session:
        case = session.get(CaseRow, case_id)
        if case is None:
            raise case_routes._not_found(case_id)

        evaluation_row = case_routes._ensure_evaluation(session, case)
        evaluation = CaseEvaluationResponse.model_validate(evaluation_row.response_json)
        request = CaseEvaluationRequest.model_validate(case.input_json)

        as_of = deps.get_adapters().clock.now().date()
        target = expected_payment_date or (as_of + timedelta(days=DEFAULT_EXPECTED_PAYMENT_DAYS))

        due_date = evaluation.timeline.due_date if evaluation.timeline else request.transaction.invoice_date
        facts = CaseFacts(
            case_id=case.id,
            accepted_amount=Decimal(str(request.transaction.principal)),
            due_date=due_date,
            has_written_objection=any(item.is_written for item in request.objections),
            recovery_state=_recovery_state(session, case.id),
        )

        body: dict[str, Any] = compare_options(
            evaluation,
            facts,
            target,
            lambda day: _interest_to_date(request, day),
            finance_config(load_config()),
            as_of=as_of,
            simulation=deps.simulation_enabled(),
        )

    # `compare_options` adds an `assumptions[]` key when a constant is uncaptured. It
    # is additive and useful, but it is not in the published schema, so it is dropped
    # here rather than returned as an undeclared field.
    body.pop("assumptions", None)
    return OptionsResponse.model_validate(body)


def _recovery_state(session, case_id: str) -> str | None:
    """The active recovery track's state, so Option 2 shows the right stage."""
    from sqlmodel import select

    from backend.store.models import Track

    row = session.exec(
        select(Track).where(
            Track.case_id == case_id, Track.kind == "RECOVERY", Track.closed_at.is_(None)
        )
    ).first()
    return row.state if row is not None else None


__all__ = ["router", "DEFAULT_EXPECTED_PAYMENT_DAYS"]
