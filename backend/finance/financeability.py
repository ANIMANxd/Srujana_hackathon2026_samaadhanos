"""Is this invoice financeable? (architecture_v4 section 5.4)

Pure: no I/O, no clock. `as_of` is passed in, never read.

Returns `{"financeable": bool, "reasons": [{"code", "message"}], "assumptions": [str]}`.
`reasons` holds only **blocking** reasons; `assumptions` is additive (the same
convention the engine uses) and records a decision taken because a constant is not
captured yet — it never blocks, because hiding the whole demo behind one missing
threshold is the trap the repo already recorded as CQ-33.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from backend.engine.gate import INELIGIBLE_STATUSES
from backend.finance.config import FinanceConfig, finance_config


@dataclass(frozen=True)
class CaseFacts:
    """The non-engine facts financeability needs.

    Built by the caller (route or workflow) from the case row, never by finance
    reaching into storage.
    """

    case_id: str
    accepted_amount: Decimal
    due_date: date
    has_written_objection: bool = False
    buyer_on_treds: bool | None = True
    user_declines_invite: bool = False
    recovery_state: str | None = None
    facts: Mapping[str, Any] = field(default_factory=dict)


def _reason(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def financeability(
    engine_result: Any,
    case_facts: CaseFacts,
    recovery_stage: int | None,
    as_of: date,
    config: Mapping[str, Any] | FinanceConfig,
) -> dict[str, Any]:
    """Apply the six section 5.4 tests and report every blocking reason.

    `engine_result` is a `CaseEvaluationResponse`: finance reads it, it never
    recomputes a legal rule. All six checks run, so the owner sees everything that
    is wrong at once rather than fixing one thing to discover the next.
    """
    cfg = config if isinstance(config, FinanceConfig) else finance_config(config)

    reasons: list[dict[str, str]] = []
    assumptions: list[str] = []

    # 1. The engine gate failed: not micro/small, a trader, or Udyam after supply.
    status = getattr(getattr(engine_result, "jurisdiction", None), "status", None)
    status_code = getattr(status, "value", status)
    if status_code in INELIGIBLE_STATUSES:
        remedy = getattr(getattr(engine_result, "jurisdiction", None), "alternative_remedy", None)
        message = (
            f"Financing is for micro and small suppliers. This case is {status_code} on the "
            "eligibility check."
        )
        if remedy:
            message = f"{message} The engine's alternative remedy still applies."
        reasons.append(_reason("GATE_BLOCKED", message))

    # 2. A written objection or dispute is recorded.
    if case_facts.has_written_objection:
        reasons.append(
            _reason(
                "WRITTEN_OBJECTION",
                "A written objection or dispute is recorded against this invoice, so a "
                "financier would treat the receivable as contested.",
            )
        )

    # 3. Recovery is already at Stage 3 or later (docs/state-machines.md section 3).
    if recovery_stage is not None and recovery_stage >= 3:
        reasons.append(
            _reason(
                "RECOVERY_STAGE_LOCKED",
                f"Recovery is already at stage {recovery_stage}. Once a dispute is formal, "
                "financing this invoice is no longer realistic.",
            )
        )

    # 4. The amount is below the configured minimum, if a minimum is configured.
    if cfg.min_amount is None:
        assumptions.append(
            "financing.min_amount is not configured, so no minimum invoice size was applied."
        )
    elif case_facts.accepted_amount < cfg.min_amount:
        reasons.append(
            _reason(
                "AMOUNT_BELOW_MINIMUM",
                f"The invoice is below the {cfg.min_amount} minimum this build will finance.",
            )
        )

    # 5. The buyer is not on the platform and the owner will not invite it.
    if case_facts.buyer_on_treds is False and case_facts.user_declines_invite:
        reasons.append(
            _reason(
                "BUYER_NOT_ON_TREDS",
                "Your buyer is not on the platform and you chose not to invite them. "
                "Your buyer must accept the invoice before financiers can bid.",
            )
        )

    # 6. The due date has passed by more than the configured allowance (OQ-11).
    overdue_days = (as_of - case_facts.due_date).days
    if overdue_days > cfg.max_overdue_days:
        reasons.append(
            _reason(
                "OVERDUE",
                f"The due date passed {overdue_days} day(s) ago. This build only finances "
                f"invoices up to {cfg.max_overdue_days} day(s) past the due date, so interest "
                "accrued so far would not be covered.",
            )
        )

    return {"financeable": not reasons, "reasons": reasons, "assumptions": assumptions}
