"""The two-option comparison (architecture_v4 sections 1.1 and 9).

Pure: no I/O, no clock. `as_of` and `expected_payment_date` are passed in.

The s.16 interest for Option 2 is **not computed here**. It arrives through the
`interest_to_date` callable, which the caller wires to the frozen engine
(`backend.engine.evaluate.evaluate_case`) at the requested date. Reimplementing
interest in this module would create a second source of legal truth.

`recommendation` is always `None`, and the field exists so that nobody adds one
later (golden rule 20).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import date
from decimal import Decimal
from typing import Any

from backend.finance.config import FinanceConfig, finance_config
from backend.finance.discount import discount, fee, net_receivable
from backend.finance.financeability import CaseFacts, financeability


def _principal(engine_result: Any, case_facts: CaseFacts) -> Decimal:
    """The outstanding principal from the engine, else the accepted amount.

    The engine owns part-payments, so its figure wins whenever it produced one.
    """
    financials = getattr(engine_result, "financials", None)
    outstanding = getattr(financials, "principal_outstanding", None) if financials else None
    return Decimal(str(outstanding)) if outstanding is not None else case_facts.accepted_amount


def _indicative(
    case_facts: CaseFacts,
    tenor_days: int,
    cfg: FinanceConfig,
) -> dict[str, Any]:
    """The Option 1 range: what you receive at the best and worst rate in the band."""
    amount = case_facts.accepted_amount
    net_at_low = net_receivable(
        amount, cfg.rate_band_low, tenor_days, cfg.day_count, cfg.platform_fee_pct
    )
    net_at_high = net_receivable(
        amount, cfg.rate_band_high, tenor_days, cfg.day_count, cfg.platform_fee_pct
    )
    low, high = sorted((net_at_low, net_at_high))
    return {
        "accepted_amount": format(amount, "f"),
        "tenor_days": tenor_days,
        "rate_band_pct": {
            "low": format(cfg.rate_band_low, "f"),
            "high": format(cfg.rate_band_high, "f"),
            "label": cfg.rate_band_label,
        },
        "platform_fee_pct": format(cfg.platform_fee_pct, "f"),
        "net_receivable_range": {"low": format(low, "f"), "high": format(high, "f")},
        "settlement": f"T+{cfg.settlement_days} after bid acceptance (config: treds.settlement_days)",
    }


def compare_options(
    engine_result: Any,
    case_facts: CaseFacts,
    expected_payment_date: date,
    interest_to_date: Callable[[date], Decimal],
    config: Mapping[str, Any] | FinanceConfig,
    *,
    as_of: date,
    simulation: bool = True,
) -> dict[str, Any]:
    """Build the `OptionsResponse` body: both options with numbers, no winner.

    `interest_to_date(date)` must return the s.16 interest accrued to that date
    from the frozen engine. It is called exactly once, for Option 2.
    """
    cfg = config if isinstance(config, FinanceConfig) else finance_config(config)
    tenor_days = (case_facts.due_date - as_of).days

    verdict = financeability(engine_result, case_facts, _stage_number(case_facts), as_of, cfg)
    available = bool(verdict["financeable"])

    get_paid_early: dict[str, Any] = {
        "available": available,
        "unavailable_reasons": [reason["message"] for reason in verdict["reasons"]],
        "indicative": _indicative(case_facts, tenor_days, cfg) if available else None,
        "notes": [
            "Your buyer must accept the invoice on the platform first.",
            "Interest accrued so far is not included.",
        ],
        "citations": [
            {"source": cfg.treds_source, "ref": "config:treds.settlement_days"},
        ],
    }

    principal = _principal(engine_result, case_facts)
    interest = Decimal(str(interest_to_date(expected_payment_date)))
    if not interest.is_finite():
        raise ValueError(f"interest_to_date returned a non-finite value: {interest!r}")

    recover_with_law: dict[str, Any] = {
        "available": True,
        "expected_payment_date": expected_payment_date.isoformat(),
        "principal": format(principal, "f"),
        "interest_to_expected_date": format(interest, "f"),
        "total_if_paid": format(principal + interest, "f"),
        "current_stage": case_facts.recovery_state,
        "notes": [
            "Only received if the buyer pays.",
            "You send every message yourself.",
        ],
        "citations": [
            {"source": cfg.interest_source, "ref": "config:interest_multiplier"},
        ],
    }

    body: dict[str, Any] = {
        "case_id": case_facts.case_id,
        "as_of": as_of.isoformat(),
        "simulation": simulation,
        "get_paid_early": get_paid_early,
        "recover_with_law": recover_with_law,
        "recommendation": None,
    }
    if verdict["assumptions"]:
        # Additive, mirroring the engine's `assumptions[]`: it records what a
        # missing constant forced, and never changes which option is available.
        body["assumptions"] = list(verdict["assumptions"])
    return body


def _stage_number(case_facts: CaseFacts) -> int | None:
    """Derive the recovery stage number from the track state name."""
    state = case_facts.recovery_state
    if not state:
        return None
    if state == "NEW":
        return 0
    if state.startswith("STAGE_"):
        head = state.split("_")[1]
        return int(head) if head.isdigit() else None
    return None


def bid_quote(
    amount: Decimal,
    annual_rate_pct: Decimal,
    tenor_days: int,
    cfg: FinanceConfig,
) -> dict[str, Decimal]:
    """Discount, fee and net for one bid, from this module (never from a mock)."""
    return {
        "discount": discount(amount, annual_rate_pct, tenor_days, cfg.day_count),
        "fee": fee(amount, cfg.platform_fee_pct),
        "net_amount": net_receivable(
            amount, annual_rate_pct, tenor_days, cfg.day_count, cfg.platform_fee_pct
        ),
    }
