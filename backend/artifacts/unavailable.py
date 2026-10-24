"""The note a blocked or under-specified case gets instead of a document.

When `availability()` says a stage cannot be produced, the caller still gets a
draft back: an honest status note that names the stage, explains why it is
unavailable in the engine's own words, and quotes the engine's alternative
remedy when the gate is what stopped the case (architecture.md section 7:
blocked cases are a first-class screen, not an error).

It carries the same DRAFT label, assumptions block and not-legal-advice footer
as every other artifact, because it is one - just one that reports a status
rather than drafting a message.
"""

from backend.app.schemas import CaseEvaluationRequest, CaseEvaluationResponse
from backend.artifacts.availability import Availability
from backend.artifacts.common import (
    assumptions_section,
    bullets,
    closing_footer,
    draft_banner,
    join_blocks,
    open_points_section,
)


def render_unavailable(
    request: CaseEvaluationRequest,
    evaluation: CaseEvaluationResponse,
    avail: Availability,
) -> str:
    """The status note for a stage this case cannot produce."""
    calc = evaluation.calculation_date.isoformat()

    status = "\n\n".join(
        [
            f"**What you asked for:** {avail.heading}",
            f"**Status:** not available for {evaluation.case_id} as on {calc}.",
        ]
    )

    reasons = "\n".join(
        [
            "## Why this stage is unavailable",
            "",
            bullets(avail.reasons),
        ]
    )

    remedy = ""
    if avail.remedy:
        remedy = "\n".join(
            [
                "## What the engine offers instead",
                "",
                "> " + avail.remedy.replace("\n", "\n> "),
            ]
        )

    assumptions = [
        (
            "This is a status note, not the "
            f"{avail.title}: no document of that stage was produced for this case."
        ),
        (
            "Every reason above is this case's own evaluation output as on "
            f"{calc}; the note adds no figure, no date and no opinion of its own."
        ),
        (
            "The stage becomes available once the case data says so - the evaluation is "
            "the single source, so regenerate after fixing the inputs rather than "
            "editing this note."
        ),
    ]

    banner = draft_banner(
        case_id=evaluation.case_id, calculation_date=evaluation.calculation_date
    )
    banner += "\n> This one reports a status instead of drafting a document."

    return join_blocks(
        f"# DRAFT \u2014 {evaluation.case_id}: {avail.heading} \u2014 not available",
        banner,
        status,
        reasons,
        remedy,
        assumptions_section(assumptions),
        open_points_section(evaluation.warnings),
        closing_footer(
            case_id=evaluation.case_id, calculation_date=evaluation.calculation_date
        ),
    )
