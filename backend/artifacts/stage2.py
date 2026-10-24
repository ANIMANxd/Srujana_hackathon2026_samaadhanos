"""Stage 2: the advisory note for the buyer's finance team.

The memo shows the engine's **three buyer-cost lines separately and never
totalled** (golden rule 8), carries the supplier's Udyam number, and keeps an
advisory tone: no deadline, no ultimatum, no threatened filing - the memo asks
for a payment date and leaves the escalation talk out.

Gated pressure points appear **only when their rule is verified**: the engine
emits them when a config flag is on, and it also warns that the flag is an open
question (OQ-8), so any point the evaluation flags as unverified is left out of
the memo body and named in the open points instead.

Every figure printed here already exists in `evaluation` - the memo computes
nothing.
"""

from backend.app.schemas import (
    BuyerCost,
    CaseEvaluationRequest,
    CaseEvaluationResponse,
    Financials,
    RateMode,
)
from backend.artifacts.common import (
    assumptions_section,
    closing_footer,
    draft_banner,
    inr,
    join_blocks,
    md_table,
    open_points_section,
    pct,
)
from backend.engine.buyer_cost import WARNING_UNVERIFIED_GATED_FEATURE

# Placeholder used when a cell has no value in this case (never a zero).
UNKNOWN = "\u2014"


def cfo_memo(request: CaseEvaluationRequest, evaluation: CaseEvaluationResponse) -> str:
    """Build the Stage 2 memo from an evaluation that has both money blocks."""
    financials = evaluation.financials
    buyer_cost = evaluation.buyer_cost
    assert (
        financials is not None and buyer_cost is not None
    ), "availability() only offers this draft when both blocks were computed"
    calc = evaluation.calculation_date.isoformat()
    supplier = request.supplier
    buyer = request.buyer
    txn = request.transaction

    addressing = [
        f"**To:** Finance team, {buyer.name}"
        + (f" (GSTIN {buyer.gstin})" if buyer.gstin else ""),
        (
            f"**From:** {supplier.name} \u00b7 Udyam registration "
            + (
                supplier.udyam_number
                if supplier.udyam_number
                else "not in this case's inputs"
            )
        ),
        f"**Subject:** Our invoice dated {txn.invoice_date.isoformat()} \u2014 the balance as on {calc}",
    ]

    timeline = evaluation.timeline
    delivery = (
        timeline.delivery_date.isoformat()
        if timeline and timeline.delivery_date
        else UNKNOWN
    )
    due = timeline.due_date.isoformat() if timeline and timeline.due_date else UNKNOWN
    overdue = (
        timeline.days_overdue
        if timeline and timeline.days_overdue is not None
        else UNKNOWN
    )

    standing = md_table(
        ["Where things stand", "As on " + calc],
        [
            ["Supply delivered", delivery],
            ["Payment due", due],
            ["Days past due", overdue],
            ["Outstanding principal", inr(financials.principal_outstanding)],
            ["Interest so far", inr(financials.interest_outstanding)],
            ["Total outstanding", inr(financials.total_claim)],
            ["Movement on this balance per day", inr(financials.daily_accrual)],
        ],
    )

    cost_lines = _cost_lines(buyer_cost, financials, calc, evaluation.warnings)

    ask = (
        "## What we would like to agree\n\n"
        "We would like to agree a date for clearing the balance above. If a split suits "
        "your cash flow, say so and we will work to a schedule that does. A reply from "
        "your finance team is enough to start."
    )

    artifact_assumptions = [
        (
            "Every figure above comes from this case's calculation as on "
            f"{calc}; none of it is worked out in this draft."
        ),
        (
            "The three cost lines are shown separately and are never totalled into one "
            "number: what is lost permanently, what is deferred, and what must be "
            "disclosed are different things."
        ),
        (
            "The rate, the buyer tax rate and the cost of capital are the values in "
            "this case's inputs and statute config; where one is not yet verified "
            "against the statute sheet, the open points below say so."
        ),
    ]

    return join_blocks(
        f"# DRAFT \u2014 {evaluation.case_id}: note for the buyer's finance team",
        draft_banner(
            case_id=evaluation.case_id, calculation_date=evaluation.calculation_date
        ),
        "\n\n".join(addressing),
        (
            "A short note on where the supply under our invoice dated "
            f"{txn.invoice_date.isoformat()} stands, and what the delay is costing your "
            "side. We would rather agree a date than argue one."
        ),
        "## Where things stand\n\n" + standing,
        cost_lines,
        ask,
        assumptions_section([*artifact_assumptions, *evaluation.assumptions]),
        open_points_section(evaluation.warnings),
        closing_footer(
            case_id=evaluation.case_id, calculation_date=evaluation.calculation_date
        ),
    )


def _cost_lines(
    buyer_cost: BuyerCost, financials: Financials, calc: str, warnings
) -> str:
    """The three lines, in their own words, never combined (golden rule 8)."""
    permanent = buyer_cost.permanent_loss
    intro = (
        "## What the delay is costing you\n\n"
        "These are three separate lines. They are kept separate on purpose: they are "
        "different kinds of cost and are not added into one number."
    )

    rate_row: list[str] = []
    if financials.rate_segments:
        segment = financials.rate_segments[-1]
        if financials.rate_mode == RateMode.FLOATING:
            rate_head = f"Rate in force on {calc}"
        else:
            rate_head = "Rate fixed for this delay from the appointed day"
        rate_row = [
            rate_head,
            f"{pct(segment.statutory_rate_pct)} a year (Bank Rate {pct(segment.bank_rate_pct)})",
        ]

    line_one = [
        "### 1. Permanent loss \u2014 interest that is not deductible\n",
        "",
        md_table(
            ["Line", "Figure"],
            [
                [
                    "Interest accrued and not deductible as on " + calc,
                    inr(permanent.interest_non_deductible),
                ],
                [
                    "Pre-tax equivalent of the rate used",
                    pct(permanent.pretax_equivalent_rate_pct),
                ],
                *([rate_row] if rate_row else []),
            ],
        ),
        "",
        f"At this balance the outstanding figure moves by {inr(financials.daily_accrual)} a day.",
    ]

    line_two = _deferral_line(buyer_cost, calc)
    line_three = _disclosure_line(buyer_cost, warnings)
    return "\n\n".join([intro, "\n".join(line_one), line_two, line_three])


def _deferral_line(buyer_cost: BuyerCost, calc: str) -> str:
    deferral = buyer_cost.deferral
    head = "### 2. Deferral \u2014 the tax timing effect at each year end\n\n"
    if not deferral.applies:
        return (
            head
            + "No qualifying 31 March checkpoint fell in this window with principal still "
            f"unpaid, so this line reads nil as on {calc}. That is an absence of a cost "
            "in this case, not a finding that deferral never applies. If a checkpoint "
            f"appears, the inputs are cost of capital {pct(deferral.inputs.cost_of_capital_pct)} "
            f"and {deferral.inputs.years_deferred} year(s) deferred."
        )
    rows = [
        [c.fy_end.isoformat(), inr(c.unpaid_principal), inr(c.tax_timing_effect)]
        for c in deferral.checkpoints
    ]
    table = md_table(
        ["31 March checkpoint", "Unpaid principal", "Tax timing effect"], rows
    )
    total = (
        f"Cost of deferring this: {inr(deferral.deferral_cost)} "
        f"(cost of capital {pct(deferral.inputs.cost_of_capital_pct)}, "
        f"{deferral.inputs.years_deferred} year(s) deferred)"
        if deferral.deferral_cost is not None
        else ""
    )
    return (
        head
        + table
        + "\n\n"
        + total
        + "\n\n"
        + "The tax timing effect stays on this line and is never added to the interest "
        "line above."
    )


def _disclosure_line(buyer_cost: BuyerCost, evaluation_warnings) -> str:
    """Line 3 plus the gated points, which appear only when verified."""
    head = "### 3. Disclosure \u2014 what the buyer's accounts carry\n\n"
    rows = []
    for flag in buyer_cost.disclosure_flags:
        if flag.verified:
            rows.append(f"- {flag.text} *(checked against the statute sheet)*")
        else:
            rows.append(
                f"- {flag.text} *(wording not yet checked against a captured source \u2014 "
                "confirm it before relying on it)*"
            )
    rows.append(_pressure_point_line(buyer_cost, evaluation_warnings))
    return head + "\n".join(rows)


def _pressure_point_line(buyer_cost: BuyerCost, evaluation_warnings) -> str:
    """Gated points are printed only when the evaluation does not flag them open."""
    points = buyer_cost.other_pressure_points
    if not points:
        return (
            "- No other gated points are switched on for this calculation, so none are "
            "listed here."
        )
    unverified = any(
        w.code == WARNING_UNVERIFIED_GATED_FEATURE for w in evaluation_warnings
    )
    if unverified:
        return (
            "- Some gated points exist for this case but are left out here: their rule is "
            "still an open question, so they are named under the open points below "
            "instead of being stated as consequences."
        )
    return "\n".join(f"- {p.text}" for p in points)
