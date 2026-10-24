"""Stage 1 drafts: the acceptance note and the balance-confirmation request.

Both are warm, operational documents with **no law in them** (AGENTS.md, task
B8): no statute, no rate, no interest, no entitlement is stated or implied, and
the assumptions block below each note is written for this draft rather than
copied from the engine's legal assumptions, so nothing legal leaks into a note
that will be pasted into an email or a chat thread as it stands.

Nothing here computes: dates come from `evaluation.timeline`, the one amount in
the balance confirmation comes from `financials.principal_outstanding`, and the
parties' names come from the request inputs.
"""

from backend.app.schemas import CaseEvaluationRequest, CaseEvaluationResponse
from backend.artifacts.common import (
    assumptions_section,
    closing_footer,
    draft_banner,
    inr,
    join_blocks,
)
from backend.engine.text import contract_str


def acceptance_note(
    request: CaseEvaluationRequest, evaluation: CaseEvaluationResponse
) -> str:
    """A short note asking the buyer to acknowledge delivery and acceptance.

    When the case has no delivery proof, this is the Stage 1 cure note
    architecture.md section 6.2 recommends: it asks for the receipt date instead
    of asserting one.
    """
    timeline = evaluation.timeline
    assert timeline is not None, "availability() only offers this draft with a timeline"
    buyer = request.buyer.name
    supplier = request.supplier.name
    invoice = request.transaction.invoice_date.isoformat()
    delivery = timeline.delivery_date
    contract = request.transaction.contract_date

    opening = (
        f"Thank you for your order dated {contract.isoformat()} and for"
        if contract
        else "Thank you for"
    )
    lines = [
        f"Dear {buyer} team,",
        "",
        f"{opening} the business behind our invoice dated {invoice}.",
    ]

    if delivery is None:
        lines += [
            "",
            "Our delivery record for that invoice is not in our file yet.",
            "",
            (
                "Could you confirm that the goods reached you, and the date they were "
                "received? One line by email is enough, and it keeps both our records "
                "lined up for the accounting."
            ),
        ]
    else:
        body = [
            "",
            f"Our records show the goods were delivered to you on {delivery.isoformat()}.",
        ]
        if _no_concern_recorded(evaluation):
            body += [
                "",
                "We have not had any concern raised with us about that delivery.",
            ]
        body += [
            "",
            (
                "Could you reply to confirm that the goods were received and accepted? "
                "One line by email is enough, and it keeps both our records lined up "
                "for the accounting."
            ),
        ]
        lines += body

    lines += ["", "With thanks,", supplier]

    assumptions = [
        (
            "Every date in this note comes from your case inputs and this case's "
            f"calculation as on {evaluation.calculation_date.isoformat()}; the draft "
            "works nothing out itself."
        ),
        (
            "The note states no amount, no rate and no claim. Stage 1 is operational: "
            "it asks the buyer to acknowledge the delivery and nothing more."
        ),
    ]
    if delivery is None:
        assumptions.append(
            "There is no delivery date in this case, so the note asks for the receipt "
            "date rather than naming one."
        )
    elif _no_concern_recorded(evaluation):
        assumptions.append(
            "The line about no concern raised reflects this case's record: no complaint "
            "about that delivery appears in it."
        )

    return join_blocks(
        f"# DRAFT \u2014 {evaluation.case_id}: acceptance note",
        draft_banner(
            case_id=evaluation.case_id, calculation_date=evaluation.calculation_date
        ),
        "\n".join(lines),
        assumptions_section(assumptions),
        closing_footer(
            case_id=evaluation.case_id, calculation_date=evaluation.calculation_date
        ),
    )


def balance_confirmation(
    request: CaseEvaluationRequest, evaluation: CaseEvaluationResponse
) -> str:
    """A request that the buyer confirm the outstanding amount and sign.

    The amount is the engine's `principal_outstanding`: this note covers what is
    unpaid for the goods, stated as on the calculation date, and deliberately
    stops there.
    """
    financials = evaluation.financials
    assert financials is not None, "availability() only offers this draft with figures"
    timeline = evaluation.timeline
    buyer = request.buyer.name
    supplier = request.supplier.name
    calc = evaluation.calculation_date.isoformat()
    invoice = request.transaction.invoice_date.isoformat()
    delivery = (
        timeline.delivery_date.isoformat()
        if timeline and timeline.delivery_date
        else None
    )

    delivered = f", delivered to you on {delivery}" if delivery else ""
    lines = [
        f"Dear {buyer} team,",
        "",
        f"Thank you for the business behind our invoice dated {invoice}{delivered}.",
        "",
        "Could you confirm the outstanding amount against that invoice, so both sets of books match?",
        "",
        f"**Outstanding amount as on {calc}: {inr(financials.principal_outstanding)}**",
        "",
        (
            "If that figure does not match what you show, please reply with your figure "
            "and its date - we would rather line the two up than talk past each other. "
            "Otherwise a confirmation by email with the same figure and date works for "
            "us, or the lines below signed and returned."
        ),
        "",
        "Amount confirmed: ______________________________",
        "",
        "Name and designation: ______________________________",
        "",
        "Signature: ______________________________    Date: ______________________________",
        "",
        "With thanks,",
        supplier,
    ]

    assumptions = [
        (
            "The amount shown is the outstanding principal this case's calculation "
            f"returned as on {calc}; the draft does not work the figure out itself."
        ),
        (
            "That calculation is still provisional while some of the values behind it "
            "await capture, so the figure is worth a look before the note goes out."
        ),
        (
            "This request covers that outstanding principal only, as on that date. It "
            "asks for a confirmation, not for payment, and it changes nothing else."
        ),
        (
            "Every other date in the note comes from your case inputs and the same "
            "calculation."
        ),
    ]

    return join_blocks(
        f"# DRAFT \u2014 {evaluation.case_id}: balance confirmation request",
        draft_banner(
            case_id=evaluation.case_id, calculation_date=evaluation.calculation_date
        ),
        "\n".join(lines),
        assumptions_section(assumptions),
        closing_footer(
            case_id=evaluation.case_id, calculation_date=evaluation.calculation_date
        ),
    )


def _no_concern_recorded(evaluation: CaseEvaluationResponse) -> bool:
    """True when this case records no complaint at all about the delivery.

    The sentence is dropped for any other objection status so the note never
    says something the case data contradicts.
    """
    timeline = evaluation.timeline
    if timeline is None:
        return False
    return (
        contract_str(timeline.objection_status) == "DEEMED_ACCEPTANCE"
        and not timeline.late_complaints
    )
