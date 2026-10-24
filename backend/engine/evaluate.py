"""evaluate.py — assemble one case evaluation (architecture.md section 8.3).

Runs the modules in the order the document specifies: **gate first**, because
everything downstream depends on its verdict. The response is then built from
their own outputs — nothing is recomputed here.

What a blocked case does (section 6.1):

- The ineligible statuses are the ones `gate.INELIGIBLE_STATUSES` names —
  `BARRED_SILPI`, `EXCLUDED_TRADER` and `EXCLUDED_MEDIUM`. For those, the
  interest and buyer-cost blocks come back **null** with a BLOCK warning that
  says so, so an empty figure on screen is explained rather than looking like a
  zero, and the alternative remedy is offered.
- `INSUFFICIENT_DATA` is *not* one of them. It means the gate could not settle
  a question (the Silpi test date is still null in the shipped config, so today
  it reaches every case), and section 5 is explicit that the engine still runs
  and warns. Nulling the money for an undecided case would hide every number in
  the demo behind one uncaptured constant, so the arithmetic still runs and the
  open question stays visible in `warnings[]`.
- Limitation, defenses and readiness are never null: the contract does not make
  them nullable, and a barred case still needs its dates and its explanation.

Hidden defaults are impossible to miss: every one this module applies (the
supply-date stand-in, the deferral-year figure, any `config_overrides`) is
recorded in `assumptions[]`.

Deterministic and fast: no clock, no I/O, no randomness — the config and the
request are the only inputs, so the same pair always produces the same response.
"""

from decimal import Decimal
from typing import Sequence

from backend.app.schemas import (
    CONTRACT_VERSION,
    CaseEvaluationRequest,
    CaseEvaluationResponse,
    Citation as CitationModel,
    Defense as DefenseModel,
    Financials,
    BuyerCost as BuyerCostModel,
    EvidenceReadiness,
    Jurisdiction,
    Limitation,
    Timeline,
    Warning as WarningModel,
)
from backend.engine.acceptance import evaluate_acceptance
from backend.engine.buyer_cost import evaluate_buyer_cost
from backend.engine.config import StatuteConfig
from backend.engine.defenses import evaluate_defenses
from backend.engine.gate import (
    INELIGIBLE_STATUSES,
    GateWarning,
    blocked_downstream_note,
    evaluate_gate,
)
from backend.engine.interest import evaluate_interest
from backend.engine.limitation import evaluate_limitation
from backend.engine.readiness import evaluate_readiness

# Section 6.4 calls years_deferred a request input with a UI default. When a
# caller omits it this is the stand-in, and it is stated in assumptions[].
DEFAULT_YEARS_DEFERRED = Decimal("1.00")

# Warning codes this module raises where a block could not be computed.
WARNING_NO_APPOINTED_DAY = "NO_APPOINTED_DAY"
WARNING_NO_DELAY_PRICED = "NO_DELAY_PRICED"
WARNING_CONFIG_OVERRIDDEN = "CONFIG_OVERRIDDEN"


def _merge_citations(groups: Sequence[Sequence]) -> list[CitationModel]:
    """One citation per id; the first writer wins so the order stays stable."""
    seen: set[str] = set()
    out: list[CitationModel] = []
    for group in groups:
        for citation in group:
            data = citation.to_dict()
            if data["id"] in seen:
                continue
            seen.add(data["id"])
            out.append(CitationModel(**data))
    return out


def _merge_warnings(groups: Sequence[Sequence]) -> list[WarningModel]:
    """Identical warnings collapse; the same code with different text stays.

    `UNVERIFIED_CONSTANT` arrives once per config key, each with its own text,
    so keying on code alone would hide all but one of them.
    """
    seen: set[tuple[str, str]] = set()
    out: list[WarningModel] = []
    for group in groups:
        for warning in group:
            data = warning.to_dict()
            key = (data["code"], data["text"])
            if key in seen:
                continue
            seen.add(key)
            out.append(WarningModel(**data))
    return out


def _merge_assumptions(groups: Sequence[Sequence[str]]) -> list[str]:
    """Distinct assumption text, first occurrence kept, order preserved."""
    seen: set[str] = set()
    out: list[str] = []
    for group in groups:
        for text in group:
            if text in seen:
                continue
            seen.add(text)
            out.append(text)
    return out


def _apply_overrides(config: StatuteConfig, overrides) -> tuple[StatuteConfig, list[str]]:
    """Honor `config_overrides` for this evaluation only (section 8.2).

    Overrides are not defaults - the caller asked for them - but each one is
    still spelled out in `assumptions[]`, so a live judge edit never changes a
    number silently. A Bank Rate override replaces every epoch with one undated
    epoch, because the caller is naming the rate for the whole delay rather
    than editing RBI history.
    """
    if overrides is None:
        return config, []

    raw = config.public_config()
    notes: list[str] = []

    if overrides.bank_rate_pct is not None:
        raw["bank_rate_epochs"]["value"] = [
            {"from": None, "bank_rate_pct": str(overrides.bank_rate_pct)}
        ]
        notes.append(
            f"Bank Rate overridden to {overrides.bank_rate_pct}% for this evaluation, "
            "replacing every configured epoch for the whole delay; the configured "
            "history is untouched."
        )
    if overrides.objection_window_days is not None:
        raw["objection_window_days"]["value"] = int(overrides.objection_window_days)
        notes.append(
            f"The written-objection window was overridden to "
            f"{int(overrides.objection_window_days)} days for this evaluation instead of "
            "the configured value."
        )
    if overrides.rate_mode is not None:
        raw["rate_mode_default"]["value"] = overrides.rate_mode.value
        notes.append(
            f"Rate mode overridden to {overrides.rate_mode.value} for this evaluation "
            "instead of the configured default."
        )
    if overrides.appropriation_mode is not None:
        raw["appropriation_mode_default"]["value"] = overrides.appropriation_mode.value
        notes.append(
            f"Appropriation mode overridden to {overrides.appropriation_mode.value} for "
            "this evaluation instead of the configured default."
        )
    if overrides.silpi_test_date is not None:
        raw["silpi_test_date"]["value"] = overrides.silpi_test_date.value
        notes.append(
            f"The Silpi test date was overridden to run from the "
            f"{overrides.silpi_test_date.value.lower()} for this evaluation instead of "
            "the configured value (OQ-2)."
        )

    if not notes:
        return config, []
    notes.append(
        "These overrides came from the request's config_overrides and apply to this "
        "evaluation only; nothing was written back to the statute config."
    )
    return StatuteConfig.from_dict(raw), notes


def evaluate_case(config: StatuteConfig, request: CaseEvaluationRequest) -> CaseEvaluationResponse:
    """Build the full response for one request (sections 6.1-6.6, 8.3).

    Every block comes from the module that owns it; this function only decides
    which blocks apply, merges the citations, assumptions and warnings without
    repeating them, and applies the request's documented defaults.
    """
    txn = request.transaction
    evaluation_notes: list[str] = []

    config, override_notes = _apply_overrides(config, request.config_overrides)
    # Usage tracking is per-evaluation state: without this, a caller reusing one
    # config across cases would report constants as used by cases that never
    # touched them (which is exactly how the fixture export drifted).
    config.reset_usage()
    evaluation_notes.extend(override_notes)

    # -- documented defaults, each surfaced in assumptions[] ----------------
    delivery_date = txn.delivery_date
    supply_date = txn.supply_date if txn.supply_date is not None else delivery_date
    if txn.supply_date is None and delivery_date is not None:
        evaluation_notes.append(
            "supply_date was not given, so the delivery date stands in for it: the "
            "documented default in section 8.2, not a computed date."
        )

    years_deferred = txn.years_deferred
    if years_deferred is None:
        years_deferred = DEFAULT_YEARS_DEFERRED
        evaluation_notes.append(
            f"years_deferred was not given, so {DEFAULT_YEARS_DEFERRED} is used on the "
            "deferral line (section 6.4 treats it as a request input with a UI default); "
            "change it to price a different deferral."
        )

    # -- 1. gate first ------------------------------------------------------
    gate = evaluate_gate(
        config,
        enterprise_class=request.supplier.enterprise_class.value,
        activity=request.supplier.activity.value,
        nic_codes=list(request.supplier.nic_codes),
        contract_date=txn.contract_date,
        supply_date=supply_date,
        investment_cr=request.supplier.investment_cr,
        turnover_cr=request.supplier.turnover_cr,
    )
    hard_blocked = gate.status in INELIGIBLE_STATUSES

    # -- 2. acceptance / timeline -------------------------------------------
    acceptance = None
    timeline_payload: dict | None = None
    if hard_blocked and delivery_date is None:
        # Section 8.3: null when the gate blocks and no dates are computable.
        timeline_payload = None
    else:
        acceptance = evaluate_acceptance(
            config,
            invoice_date=txn.invoice_date,
            delivery_date=delivery_date,
            calculation_date=txn.calculation_date,
            objections=request.objections,
            written_credit_days=txn.written_credit_days,
        )
        timeline_payload = acceptance.to_dict()

    # -- 3. interest (skipped for an ineligible case, section 6.1) ----------
    interest = None
    financials_payload: dict | None = None
    block_warnings: list = []
    if hard_blocked:
        block_warnings.append(blocked_downstream_note(gate))
    elif acceptance is None or acceptance.appointed_day is None:
        block_warnings.append(
            _warn(
                WARNING_NO_APPOINTED_DAY,
                "WARN",
                "There is no appointed day on this case yet - there is no delivery "
                "date, or an objection inside the window is still unresolved - so no "
                "interest could be calculated. The financials block is empty because "
                "no calculation ran, not because the amount is zero.",
            )
        )
    else:
        interest = evaluate_interest(
            config,
            principal=txn.principal,
            appointed_day=acceptance.appointed_day,
            calculation_date=txn.calculation_date,
            part_payments=request.part_payments,
            rate_mode=None,  # config default, cited by the interest module
            appropriation_mode=None,
        )
        financials_payload = interest.to_dict()

    # -- 4. buyer cost (section 6.4: three lines, only when money exists) ---
    buyer_cost_payload: dict | None = None
    buyer_cost_result = None
    if interest is not None:
        if not interest.rate_segments:
            # Evaluation lands on or before the appointed day: nothing has run yet.
            block_warnings.append(
                _warn(
                    WARNING_NO_DELAY_PRICED,
                    "WARN",
                    "The calculation date is on or before the appointed day, so no day "
                    "of delay has accrued. The buyer-cost block is empty because there "
                    "is nothing to price yet, not because the costs are zero.",
                )
            )
        else:
            buyer_cost_result = evaluate_buyer_cost(
                config,
                interest_total=interest.interest_total,
                # The rate of the last segment is the rate in force at the
                # calculation date under either mode: FLOATING's final segment,
                # or the single frozen segment (CQ-22).
                statutory_rate_pct=interest.rate_segments[-1].statutory_rate_pct,
                buyer_tax_rate_pct=request.buyer.tax_rate_pct,
                due_date=acceptance.due_date,
                calculation_date=txn.calculation_date,
                cost_of_capital_pct=request.buyer.cost_of_capital_pct,
                years_deferred=years_deferred,
                principal_timeline=interest.principal_timeline,
            )
            buyer_cost_payload = buyer_cost_result.to_dict()

    # -- 5-7. limitation, defenses, readiness: never null (section 8.3) -----
    due_date = acceptance.due_date if acceptance is not None else None
    days_overdue = timeline_payload["days_overdue"] if timeline_payload is not None else None

    limitation = evaluate_limitation(
        config,
        due_date=due_date,
        calculation_date=txn.calculation_date,
        acknowledgments=request.acknowledgments,
    )
    defenses = evaluate_defenses(
        gate_status=gate.status,
        acceptance_status=acceptance.status if acceptance is not None else None,
        agreed_days=acceptance.agreed_days if acceptance is not None else None,
        credit_clamped=acceptance.clamped if acceptance is not None else False,
        limitation_status=limitation.status,
        evidence=request.evidence.items,
    )
    readiness = evaluate_readiness(
        gate_status=gate.status,
        delivery_date=delivery_date,
        due_date=due_date,
        days_overdue=days_overdue,
        evidence=request.evidence.items,
    )

    # -- merge everything, de-duplicated ------------------------------------
    citations = _merge_citations(
        [
            gate.citations,
            acceptance.citations if acceptance else [],
            interest.citations if interest else [],
            buyer_cost_result.citations if buyer_cost_result else [],
            limitation.citations,
            defenses.citations,
            readiness.citations,
        ]
    )
    warnings = _merge_warnings(
        [
            gate.warnings,
            acceptance.warnings if acceptance else [],
            interest.warnings if interest else [],
            buyer_cost_result.warnings if buyer_cost_result else [],
            limitation.warnings,
            defenses.warnings,
            readiness.warnings,
            block_warnings,
            config.warnings(),  # UNVERIFIED_CONSTANT for every constant used
        ]
    )
    assumptions = _merge_assumptions(
        [
            gate.assumptions,
            acceptance.assumptions if acceptance else [],
            interest.assumptions if interest else [],
            buyer_cost_result.assumptions if buyer_cost_result else [],
            limitation.assumptions,
            defenses.assumptions,
            readiness.assumptions,
            evaluation_notes,
        ]
    )

    return CaseEvaluationResponse(
        contract_version=CONTRACT_VERSION,
        case_id=request.case_id,
        calculation_date=txn.calculation_date,
        jurisdiction=Jurisdiction(**gate.to_dict()),
        timeline=Timeline(**timeline_payload) if timeline_payload is not None else None,
        financials=Financials(**financials_payload) if financials_payload is not None else None,
        buyer_cost=BuyerCostModel(**buyer_cost_payload) if buyer_cost_payload is not None else None,
        limitation=Limitation(**limitation.to_dict()),
        defenses=[DefenseModel(**row) for row in defenses.to_dict()],
        evidence_readiness=EvidenceReadiness(**readiness.to_dict()),
        citations=citations,
        assumptions=assumptions,
        warnings=warnings,
    )


def _warn(code: str, severity: str, text: str) -> GateWarning:
    """A warning shaped like the contract's, built where the engine needs one."""
    return GateWarning(code=code, severity=severity, text=text)
