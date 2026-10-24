"""Whether a case can produce a given artifact, and why not when it cannot.

The rules are structural and read only the evaluation the engine returned:

- A case the eligibility gate stopped produces **no** escalation draft at all.
  Architecture.md section 7: medium, trader and Silpi-barred suppliers are
  "stopped at the gate with an honest explanation", so the note explains the
  block (quoting the engine's own check details and alternative remedy) rather
  than writing a document the ladder cannot stand behind.
- A stage that needs a figure the engine did not compute says so instead of
  printing a zero (golden rule 7: no invented numbers, and never zeros where
  the block is merely absent).

Nothing here decides a legal question: every reason line is either engine text
quoted verbatim or a plain restatement of an engine status enum.
"""

from dataclasses import dataclass, field

from backend.app.schemas import CaseEvaluationRequest, CaseEvaluationResponse
from backend.artifacts.kinds import ArtifactKind, KIND_TITLES, STAGE_BY_KIND
from backend.engine.gate import INELIGIBLE_STATUSES

# The readiness reason code that shuts Stage 4 (backend/engine/readiness.py).
REASON_MISSING_DELIVERY_PROOF = "MISSING_DELIVERY_PROOF"


@dataclass(frozen=True)
class Availability:
    """The verdict for one kind on one case, with engine-sourced reasons."""

    available: bool
    stage: int
    title: str
    reasons: tuple[str, ...] = field(default_factory=tuple)
    remedy: str | None = None

    @property
    def heading(self) -> str:
        return f"Stage {self.stage}: {self.title}"


def availability(
    kind: ArtifactKind,
    evaluation: CaseEvaluationResponse,
    request: CaseEvaluationRequest,
) -> Availability:
    """Decide whether `kind` can be built from this evaluation.

    `request` is only consulted for the evidence the readiness output does not
    carry; every figure and date comes from `evaluation`.
    """
    stage = STAGE_BY_KIND[kind]
    title = KIND_TITLES[kind]

    gate_reasons = _gate_reasons(evaluation, stage)
    if gate_reasons:
        return Availability(
            available=False,
            stage=stage,
            title=title,
            reasons=gate_reasons,
            remedy=evaluation.jurisdiction.alternative_remedy,
        )

    reasons: list[str] = []

    if kind in (
        ArtifactKind.STAGE1_ACCEPTANCE_NOTE,
        ArtifactKind.STAGE1_BALANCE_CONFIRMATION,
    ):
        if evaluation.timeline is None:
            reasons.append(
                "No timeline could be worked out for this case, so there are no dates "
                "for this draft to refer to."
            )

    if (
        kind == ArtifactKind.STAGE1_BALANCE_CONFIRMATION
        and evaluation.financials is None
    ):
        reasons.append(_money_absent_reason(evaluation))

    if kind == ArtifactKind.STAGE2_CFO_MEMO:
        if evaluation.financials is None:
            reasons.append(_money_absent_reason(evaluation))
        if evaluation.buyer_cost is None:
            reasons.append(
                "No cost lines were computed for this case, and the finance note exists "
                "to show those lines separately."
            )

    if (
        kind == ArtifactKind.STAGE3_SETTLEMENT_TERMSHEET
        and evaluation.financials is None
    ):
        reasons.append(_money_absent_reason(evaluation))
        reasons.append(
            "A term sheet prices a settlement against the claim the engine computed, and "
            "there is no claim figure here to price."
        )

    if kind == ArtifactKind.STAGE4_EVIDENCE_PACK:
        blocked = evaluation.evidence_readiness.blocked_stages
        if stage in blocked:
            reasons.extend(_stage4_block_reasons(evaluation))
        if evaluation.financials is None:
            reasons.append(
                "The interest calculation sheet would have to come from this case's "
                "ledger, and no ledger was computed for it."
            )

    return Availability(
        available=not reasons,
        stage=stage,
        title=title,
        reasons=tuple(reasons),
    )


def _gate_reasons(evaluation: CaseEvaluationResponse, stage: int) -> tuple[str, ...]:
    """Plain restatement of the gate verdict, plus the engine's check details."""
    status = evaluation.jurisdiction.status
    if status.value not in INELIGIBLE_STATUSES:
        return ()
    failed = [c.detail for c in evaluation.jurisdiction.checks if c.passed is False]
    reasons = [
        f"The eligibility gate stopped this case with status {status.value}.",
        *failed,
        (
            "Because of that, this case carries no computed claim, no cost lines and no "
            "interest sheet, so Stage "
            f"{stage} cannot be built from it. Those figures are absent on purpose, "
            "not zero."
        ),
        "This tool does not write escalation drafts for a case the gate has stopped.",
    ]
    return tuple(reasons)


def _money_absent_reason(evaluation: CaseEvaluationResponse) -> str:
    """Why no outstanding amount exists, taken from the engine's own statuses."""
    timeline = evaluation.timeline
    if timeline is None:
        return (
            "No outstanding amount was computed for this case, so there is nothing to "
            "state or split."
        )
    status = timeline.objection_status
    if status.value == "NO_DELIVERY_PROOF":
        return (
            "Delivery proof is not in this case, so acceptance and the due date are "
            "unresolved and no outstanding amount has been computed."
        )
    if status.value == "PENDING_RESOLUTION":
        return (
            "A written objection is still open in this case, so no due date has been "
            "fixed and no outstanding amount has been computed."
        )
    return (
        "No due date has been fixed for this case yet, so the delay has not started and "
        "no outstanding amount has been computed."
    )


def _stage4_block_reasons(evaluation: CaseEvaluationResponse) -> list[str]:
    """The readiness engine's own words for why Stage 4 is shut."""
    texts = [
        r.text
        for r in evaluation.evidence_readiness.reasons
        if r.code == REASON_MISSING_DELIVERY_PROOF
    ]
    if not texts:
        return [
            "The readiness output lists Stage 4 among this case's blocked stages, so the "
            "pack is not available yet."
        ]
    return texts
