"""readiness.py — the evidence readiness score (architecture.md section 6.6).

Returns a 0-100 score with `reasons[]`, the evidence still needed in `missing[]`,
`blocked_stages`, and the stage the case should move to next.

**The score is arithmetic over its own reasons, nothing else.** It starts at
`BASE_SCORE` (100) and each reason subtracts its `delta`, so a reader can add up
the list and land on the number: `score = clamp(BASE + sum(deltas), 0, 100)`.
Where delivery proof is missing the score is additionally capped, because the
document says a case without it cannot be complete (section 6.2 and 6.6); that
cap is applied after the sum and is named in the reason's text so it is not a
hidden adjustment.

Two inputs drive two separate outputs, and they are kept separate on purpose:

- The **score** reflects evidence only.
- The **band** reflects the gate: a Silpi, trader or medium block sets it to
  `BLOCKED` without moving the score at all, which is why that reason carries a
  delta of zero.

Bands are `EVIDENCE_COMPLETE`, `ACTION_NEEDED` and `BLOCKED`.

Nothing in this module states or implies how any argument would be decided. It
scores paperwork, and says only that paperwork is or is not held.

Pure: no config reads, no file I/O, no clock — `days_overdue` and every date
arrive in the request.
"""

from dataclasses import dataclass
from datetime import date
from typing import Protocol, Sequence

from backend.engine.gate import GateCitation, GateWarning

# Bands, matching the names the spec renamed them to (see CR-3 in
# frontend/CONTRACT-REQUESTS.md).
BAND_EVIDENCE_COMPLETE = "EVIDENCE_COMPLETE"
BAND_ACTION_NEEDED = "ACTION_NEEDED"
BAND_BLOCKED = "BLOCKED"

# The score starts here and only ever loses points.
BASE_SCORE = 100

# A case without delivery proof cannot be complete, so the score stops here
# (section 6.2: readiness capped, Stage 4 blocked). The deduction below is
# derived from this cap - BASE minus the cap - so the stated invariant
# `score = BASE + sum(deltas)` still reproduces the number exactly while the cap
# holds on its own: every other delta is zero or negative, so once 50 points are
# gone the score cannot climb back above 50.
DELIVERY_PROOF_SCORE_CAP = 50

# Gate outcomes that set the band to BLOCKED without touching the score.
GATE_BLOCKING = frozenset({"BARRED_SILPI", "EXCLUDED_TRADER", "EXCLUDED_MEDIUM"})
GATE_ELIGIBLE = "ELIGIBLE"
GATE_INSUFFICIENT_DATA = "INSUFFICIENT_DATA"

# Evidence that is worth points when it is absent. WhatsApp messages are optional
# by nature, so they are never deducted and never appear in missing[].
# (code, points deducted, evidence label used in the reason's text)
_CORE_EVIDENCE: tuple[tuple[str, int, str], ...] = (
    ("PO", 15, "Purchase order"),
    ("INVOICE", 15, "GST invoice"),
    ("UDYAM", 10, "Udyam certificate"),
    ("GST_RETURN", 5, "GST return evidence"),
)

_DELIVERY_PROOF_POINTS = BASE_SCORE - DELIVERY_PROOF_SCORE_CAP
_ELIGIBILITY_POINTS = 10
_ACCEPTANCE_POINTS = 10

# Stage numbers are the escalation ladder from section 2 and section 6.2.
STAGE_BALANCE_CONFIRMATION = 1
STAGE_MEMO = 2
STAGE_SETTLEMENT = 3
STAGE_EVIDENCE_PACK = 4


class EvidenceLike(Protocol):
    """The shape of an evidence item this module needs (contract: EvidenceItem)."""

    kind: str
    present: bool
    ref: str | None


# ------------------------------------------------------------ result types ----


@dataclass(frozen=True)
class ReadinessReason:
    """One line of the score. `delta` is a deduction, so it is zero or negative."""

    code: str
    delta: int
    text: str

    def to_dict(self) -> dict[str, object]:
        return {"code": self.code, "delta": self.delta, "text": self.text}


@dataclass(frozen=True)
class ReadinessResult:
    """The score, its band, and everything behind both."""

    score: int
    band: str
    reasons: list[ReadinessReason]
    missing: list[str]
    blocked_stages: list[int]
    recommended_stage: int
    citations: list[GateCitation]
    warnings: list[GateWarning]
    assumptions: list[str]

    def to_dict(self) -> dict[str, object]:
        """JSON-ready form matching the contract's `EvidenceReadiness` block."""
        return {
            "score": self.score,
            "band": self.band,
            "reasons": [r.to_dict() for r in self.reasons],
            "missing": list(self.missing),
            "blocked_stages": list(self.blocked_stages),
            "recommended_stage": self.recommended_stage,
        }


# ------------------------------------------------------------------ helpers ----


def _held(evidence: Sequence[EvidenceLike]) -> dict[str, bool]:
    """Which evidence kinds the request reports as present."""
    return {str(item.kind): bool(item.present) for item in evidence}


def _clamp(value: int) -> int:
    return max(0, min(100, value))


def _band(gate_status: str, missing: list[str]) -> str:
    """The band answers "how does this case stand?", the score "how is the paperwork?"."""
    if gate_status in GATE_BLOCKING:
        return BAND_BLOCKED
    if gate_status == GATE_ELIGIBLE and not missing:
        return BAND_EVIDENCE_COMPLETE
    return BAND_ACTION_NEEDED


def _recommended_stage(
    *,
    gate_status: str,
    delivery_missing: bool,
    due_date: date | None,
    days_overdue: int | None,
    band: str,
) -> int:
    """Which stage to move to next, from structural facts only.

    No day thresholds are invented: a case with nothing proven, a barred case,
    or one not yet past its appointed day has nothing to escalate, so it starts
    at Stage 1 (section 6.2 recommends the Stage 1 cure note when delivery proof
    is missing). Unresolved eligibility needs the internal memo before anything
    leaves the building. Everything held means build the pack; anything else
    outstanding means settle while the paperwork is gathered.

    A missing due date also stops at Stage 1 even when every document is held:
    without it there is no amount or date to put in front of anyone.
    """
    if (
        delivery_missing
        or gate_status in GATE_BLOCKING
        or due_date is None
        or days_overdue is None
    ):
        return STAGE_BALANCE_CONFIRMATION
    if gate_status == GATE_INSUFFICIENT_DATA:
        return STAGE_MEMO
    if band == BAND_EVIDENCE_COMPLETE:
        return STAGE_EVIDENCE_PACK
    return STAGE_SETTLEMENT


# ----------------------------------------------------------------- the rule ----


def evaluate_readiness(
    *,
    gate_status: str,
    delivery_date: date | None,
    due_date: date | None,
    days_overdue: int | None,
    evidence: Sequence[EvidenceLike] = (),
) -> ReadinessResult:
    """Score the evidence and pick the next stage (section 6.6).

    `gate_status` comes from gate, the dates from acceptance, and `evidence` is
    the request's list. Nothing is read from config, so this module adds no
    `citations[]` entry.
    """
    reasons: list[ReadinessReason] = []
    assumptions: list[str] = []
    held = _held(evidence)

    proof_held = held.get("DELIVERY_PROOF", False)
    # Either shape of the same gap: no delivery date, or no document for it.
    delivery_missing = delivery_date is None or not proof_held

    if delivery_missing:
        reasons.append(
            ReadinessReason(
                code="MISSING_DELIVERY_PROOF",
                delta=-_DELIVERY_PROOF_POINTS,
                text=(
                    "Delivery proof is not in this case, so acceptance cannot be shown. "
                    f"Deducted {_DELIVERY_PROOF_POINTS} points, which caps the score at "
                    f"{DELIVERY_PROOF_SCORE_CAP} while it is missing, and Stage 4 stays "
                    "shut until it is added."
                ),
            )
        )
        missing = ["DELIVERY_PROOF"]
    else:
        missing = []

    for kind, points, label in _CORE_EVIDENCE:
        if held.get(kind, False):
            continue
        missing.append(kind)
        reasons.append(
            ReadinessReason(
                code=f"MISSING_EVIDENCE_{kind}",
                delta=-points,
                text=f"{label} is not in this case. Deducted {points} points.",
            )
        )

    if gate_status == GATE_INSUFFICIENT_DATA:
        reasons.append(
            ReadinessReason(
                code="ELIGIBILITY_UNRESOLVED",
                delta=-_ELIGIBILITY_POINTS,
                text=(
                    "The gate could not settle eligibility from what was entered, so the "
                    f"case is not complete yet. Deducted {_ELIGIBILITY_POINTS} points."
                ),
            )
        )

    if due_date is None and not delivery_missing:
        reasons.append(
            ReadinessReason(
                code="ACCEPTANCE_UNRESOLVED",
                delta=-_ACCEPTANCE_POINTS,
                text=(
                    "There is still no due date because the objection window has not "
                    f"closed, so the clock has not started. Deducted {_ACCEPTANCE_POINTS} "
                    "points."
                ),
            )
        )

    if gate_status in GATE_BLOCKING:
        # Zero on purpose: the band is what this changes, not the score.
        reasons.append(
            ReadinessReason(
                code="GATE_BLOCKED",
                delta=0,
                text=(
                    f"The gate returned {gate_status}, so the band is BLOCKED. The score "
                    "still describes the evidence alone and is unchanged by this line."
                ),
            )
        )

    total = _clamp(BASE_SCORE + sum(r.delta for r in reasons))
    if delivery_missing:
        total = min(total, DELIVERY_PROOF_SCORE_CAP)

    # missing[] is already in evidence order: delivery proof first, because it
    # is the one that both caps the score and shuts Stage 4.
    band = _band(gate_status, missing)
    blocked = [STAGE_EVIDENCE_PACK] if delivery_missing else []
    stage = _recommended_stage(
        gate_status=gate_status,
        delivery_missing=delivery_missing,
        due_date=due_date,
        days_overdue=days_overdue,
        band=band,
    )

    assumptions.extend(
        [
            f"The score starts at {BASE_SCORE} and only loses points: it is "
            f"{BASE_SCORE} plus every reason's delta, clamped between 0 and 100, so "
            "adding up the reasons reproduces it exactly.",
            f"With delivery proof missing the score is also capped at "
            f"{DELIVERY_PROOF_SCORE_CAP}, which section 6.2 and 6.6 both call for. Its "
            f"deduction is exactly {BASE_SCORE} - {DELIVERY_PROOF_SCORE_CAP}, so the "
            "formula above still reproduces the capped number, and the reason says so in "
            "its own text rather than adjusting anything silently.",
            "The band comes from the gate, not from the score: a Silpi, trader or medium "
            "block sets BLOCKED and leaves the score where it is, which is why that "
            "reason carries a delta of zero.",
            "missing[] lists the evidence still needed for a complete pack. WhatsApp "
            "messages are treated as optional, so they are never deducted and never "
            "listed as missing.",
            "The next stage follows structural facts only - unresolved proof, a blocked "
            "gate, no due date yet, eligibility still open, evidence complete - with no "
            "day thresholds invented: Stage 1 to cure or wait, Stage 2 to resolve "
            "eligibility, Stage 3 to settle while paperwork is outstanding, Stage 4 when "
            "everything is held.",
        ]
    )

    return ReadinessResult(
        score=total,
        band=band,
        reasons=reasons,
        missing=missing,
        blocked_stages=blocked,
        recommended_stage=stage,
        citations=[],  # no config constant is read here
        warnings=[],
        assumptions=assumptions,
    )
