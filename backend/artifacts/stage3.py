"""Stage 3: a plain settlement term sheet built from settlement arithmetic.

The split itself is the engine's - `backend.engine.settlement.evaluate_settlement`
- called with this case's principal and interest outstanding and with the terms
carried in the request. When the request carries no terms, the draft states the
neutral starting terms it was made with (no interest waived, the whole amount
payable now) and says so on the page, so a reader always sees which proposal
these numbers price.

The template prints that result. It does no arithmetic of its own: it never
adds, subtracts or rounds anything, and it never touches the buyer-cost lines
(golden rule 8).
"""

from backend.app.schemas import (
    CaseEvaluationRequest,
    CaseEvaluationResponse,
    SettlementTerms,
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
from backend.engine.settlement import PAYMENT_SECOND, evaluate_settlement

# The draft's neutral starting terms - negotiator's inputs, not statutory
# figures (the settlement engine says so in its own assumptions). Used only
# when the request carries no `settlement` block.
NEUTRAL_TERMS = SettlementTerms(
    upfront_pct="100", waiver_pct="0", days_to_second_payment=0
)

UNKNOWN = "\u2014"


def settlement_termsheet(
    request: CaseEvaluationRequest,
    evaluation: CaseEvaluationResponse,
    terms: SettlementTerms | None = None,
) -> str:
    """Build the Stage 3 term sheet from this case's claim and the offer terms."""
    financials = evaluation.financials
    assert financials is not None, "availability() only offers this draft with a claim"
    timeline = evaluation.timeline
    applied = terms or NEUTRAL_TERMS
    result = evaluate_settlement(
        principal_outstanding=financials.principal_outstanding,
        interest_outstanding=financials.interest_outstanding,
        upfront_pct=applied.upfront_pct,
        waiver_pct=applied.waiver_pct,
        days_to_second_payment=applied.days_to_second_payment,
    )
    calc = evaluation.calculation_date.isoformat()
    supplier = request.supplier.name
    buyer = request.buyer.name
    txn = request.transaction
    delivery = (
        timeline.delivery_date.isoformat()
        if timeline and timeline.delivery_date
        else UNKNOWN
    )
    due = timeline.due_date.isoformat() if timeline and timeline.due_date else UNKNOWN

    header = [
        f"**Parties:** {supplier} (the supplier) and {buyer} (the buyer)",
        (
            f"**About:** our invoice dated {txn.invoice_date.isoformat()}, delivered "
            f"{delivery}, payment due {due}"
        ),
        (
            "**Status:** a commercial proposal to discuss. Nothing is binding until both "
            "sides sign below, nothing has been filed, and nothing is sent from here."
        ),
    ]

    claim = md_table(
        ["The claim as on " + calc, "Amount"],
        [
            ["Principal outstanding", inr(financials.principal_outstanding)],
            ["Interest to " + calc, inr(financials.interest_outstanding)],
            ["Total claim", inr(financials.total_claim)],
        ],
    )

    # How the payment schedule reads: a draft that leaves nothing for later says
    # so, rather than describing a second payment of nothing.
    second = next((p for p in result.payments if p.kind == PAYMENT_SECOND), None)
    if second is None or second.amount == 0:
        schedule = "and the whole amount payable now"
        terms_short = f"{pct(applied.waiver_pct)} waiver, everything payable now"
    else:
        schedule = f"with the rest after {second.days_from_now} day(s)"
        terms_short = (
            f"{pct(applied.waiver_pct)} waiver, {pct(applied.upfront_pct)} payable now, "
            f"second payment after {applied.days_to_second_payment} day(s)"
        )

    proposed = [
        (
            f"This draft proposes {pct(applied.waiver_pct)} of the outstanding interest "
            f"waived {schedule}. Those are starting terms for a conversation, not a "
            "negotiated outcome."
        ),
        "",
        md_table(
            ["Proposed term", "Value"],
            [
                [
                    "Interest waived (" + pct(applied.waiver_pct) + ")",
                    inr(result.interest_waived),
                ],
                ["Interest payable after the waiver", inr(result.interest_paid)],
                ["Principal payable (not waived)", inr(result.principal_paid)],
                ["Total payable", inr(result.total_payable)],
                *_payment_rows(result.payments),
                ["Net recovery to the supplier", inr(result.net_recovery)],
            ],
        ),
    ]

    agreement = "\n".join(
        [
            "## Agreement (draft \u2014 unsigned)",
            "",
            "This term sheet records what the two sides are discussing. Neither side "
            "gives up any position by signing, and the signed copy belongs to whoever "
            "keeps it.",
            "",
            "**Supplier**",
            "",
            "Name and designation: ______________________________",
            "",
            "Signature: ______________________________    Date: ______________________________",
            "",
            "**Buyer**",
            "",
            "Name and designation: ______________________________",
            "",
            "Signature: ______________________________    Date: ______________________________",
        ]
    )

    artifact_assumptions = [
        (
            "The proposed terms above are the starting terms this draft was made with: "
            f"{terms_short}. They are negotiator's inputs, not statutory figures."
        ),
        (
            "The claim figures are this case's own calculation as on "
            f"{calc}; the split is the engine's settlement arithmetic over them, and "
            "this draft adds no arithmetic of its own."
        ),
        "This sheet never combines the buyer's cost lines with these figures.",
    ]

    return join_blocks(
        f"# DRAFT \u2014 {evaluation.case_id}: settlement term sheet",
        draft_banner(
            case_id=evaluation.case_id, calculation_date=evaluation.calculation_date
        ),
        "\n\n".join(header),
        "## The claim\n\n" + claim,
        "## Proposed terms\n\n" + "\n".join(proposed),
        agreement,
        assumptions_section(
            [*artifact_assumptions, *result.assumptions, *evaluation.assumptions]
        ),
        open_points_section(evaluation.warnings),
        closing_footer(
            case_id=evaluation.case_id, calculation_date=evaluation.calculation_date
        ),
    )


def _payment_rows(payments) -> list[list[str]]:
    """The payment schedule as rows; a single payment reads as one line.

    A zero-amount leg is dropped rather than printed as Rs 0.00, so the table
    says what the buyer actually pays.
    """
    live = [p for p in payments if p.amount > 0]
    if len(live) == 1:
        only = live[0]
        label = (
            "Single payment (today)"
            if only.days_from_now == 0
            else f"Single payment, day {only.days_from_now}"
        )
        return [[label, inr(only.amount)]]
    return [
        [f"Payment {index} of {len(live)}, day {p.days_from_now}", inr(p.amount)]
        for index, p in enumerate(live, start=1)
    ]
