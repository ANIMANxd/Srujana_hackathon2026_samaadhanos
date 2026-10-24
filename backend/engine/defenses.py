"""defenses.py — the buyer-argument panel (architecture.md section 6.6).

Seven rows, always all seven, so the panel is comparable across cases:
defective goods, never accepted, the PO's 90-day term, not eligible, an
arbitration clause, set-off, and time-bar.

Status comes from **engine state only** — the gate, the acceptance outcome, the
agreed credit period and the limitation band. Whether a document is also in the
request is reported separately in `evidence_have` / `evidence_missing`, so the
two columns stay independently checkable rather than one silently deciding the
other.

Arbitration clause and set-off are `OPEN_QUESTION` unconditionally (OQ-7):
neither is decided here, because deciding them would assert a contested position.
Where the engine genuinely cannot tell — no gate verdict, no accepted period, an
unknown limitation band — the row is `OPEN_QUESTION` rather than a guess in
either direction.

`rule_ref` follows the engine's existing shape, `<module>.<id>`, so the frontend
can build `rules.<code>.title` from it. Evidence entries are `EvidenceKind`
codes (`DELIVERY_PROOF`), which the frontend already translates.

Pure: no config reads, no file I/O, no clock. This module therefore adds no
`citations[]` entry of its own; each row carries its `rule_ref` instead.
"""

from dataclasses import dataclass
from typing import Protocol, Sequence

from backend.engine.gate import GateCitation, GateWarning

# Statuses, matching DefenseStatus in backend/app/schemas.py.
STATUS_STRONG = "STRONG"
STATUS_AT_RISK = "AT_RISK"
STATUS_OPEN_QUESTION = "OPEN_QUESTION"

# Gate outcomes that answer the "not eligible" argument.
GATE_ELIGIBLE = "ELIGIBLE"
GATE_INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
GATE_BLOCKING = frozenset({"BARRED_SILPI", "EXCLUDED_TRADER", "EXCLUDED_MEDIUM"})

# Acceptance outcomes that answer the acceptance-based arguments. Plain strings
# so they can be put in and out of sets freely (a nested set would compare by
# identity, never by value).
ACCEPTANCE_DEEMED = "DEEMED_ACCEPTANCE"
ACCEPTANCE_RESOLVED = "RESOLVED"
ACCEPTANCE_PENDING = "PENDING_RESOLUTION"
ACCEPTANCE_NO_DELIVERY = "NO_DELIVERY_PROOF"

# Limitation bands that answer the time-bar argument.
LIMITATION_IN_TIME = frozenset({"OK", "WARN_12M"})
LIMITATION_AT_RISK = frozenset({"WARN_6M", "EXPIRED"})


class EvidenceLike(Protocol):
    """The shape of an evidence item this module needs (contract: EvidenceItem)."""

    kind: str
    present: bool
    ref: str | None


# ------------------------------------------------------------------ row spec ----


@dataclass(frozen=True)
class _RowSpec:
    id: str
    buyer_says: str
    evidence: tuple[str, ...]  # EvidenceKind codes relevant to this argument


# The seven arguments, in the order section 6.6 lists them. Order matters: the
# guidance card picks the first AT_RISK row, so this is the priority order too.
_ROW_SPECS: tuple[_RowSpec, ...] = (
    _RowSpec(
        id="defective_goods",
        buyer_says="The goods were defective, so we do not owe for them.",
        evidence=("PO", "INVOICE", "DELIVERY_PROOF"),
    ),
    _RowSpec(
        id="never_accepted",
        buyer_says="The goods were never accepted, so nothing became due.",
        evidence=("DELIVERY_PROOF", "INVOICE", "PO"),
    ),
    _RowSpec(
        id="po_90_days",
        buyer_says="Our purchase order gives us 90 days to pay.",
        evidence=("PO", "INVOICE"),
    ),
    _RowSpec(
        id="not_eligible",
        buyer_says="The supplier is not a micro or small enterprise, so the Act does not apply.",
        evidence=("UDYAM", "GST_RETURN"),
    ),
    _RowSpec(
        id="arbitration_clause",
        buyer_says="The contract has an arbitration clause, so this belongs in arbitration.",
        evidence=("PO",),
    ),
    _RowSpec(
        id="set_off",
        buyer_says="We are owed other amounts, so we will set those off against this invoice.",
        evidence=("INVOICE", "GST_RETURN"),
    ),
    _RowSpec(
        id="time_barred",
        buyer_says="This claim is out of time.",
        evidence=("INVOICE", "DELIVERY_PROOF"),
    ),
)


# ------------------------------------------------------------ result types ----


@dataclass(frozen=True)
class Defense:
    """One row: the buyer's argument, the answer's strength, and the paperwork."""

    id: str
    buyer_says: str
    rule_ref: str
    status: str
    evidence_have: list[str]
    evidence_missing: list[str]

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "buyer_says": self.buyer_says,
            "rule_ref": self.rule_ref,
            "status": self.status,
            "evidence_have": list(self.evidence_have),
            "evidence_missing": list(self.evidence_missing),
        }


@dataclass(frozen=True)
class DefensesResult:
    """All seven rows plus what the response needs alongside them."""

    rows: list[Defense]
    citations: list[GateCitation]
    warnings: list[GateWarning]
    assumptions: list[str]

    def to_dict(self) -> list[dict[str, object]]:
        """JSON-ready form matching the contract's `defenses` block."""
        return [row.to_dict() for row in self.rows]


# ------------------------------------------------------------------ helpers ----


def _evidence_split(
    wanted: tuple[str, ...], held: dict[str, EvidenceLike]
) -> tuple[list[str], list[str]]:
    """Which of `wanted` the request holds, and which it does not.

    A kind the request never mentions counts as missing: silence is not
    evidence. Codes are returned as-is so the frontend can translate them.
    """
    have: list[str] = []
    missing: list[str] = []
    for kind in wanted:
        item = held.get(kind)
        (have if item is not None and item.present else missing).append(kind)
    return have, missing


def _defend(
    spec: _RowSpec, status: str, held: dict[str, EvidenceLike]
) -> Defense:
    have, missing = _evidence_split(spec.evidence, held)
    return Defense(
        id=spec.id,
        buyer_says=spec.buyer_says,
        rule_ref=f"defenses.{spec.id}",
        status=status,
        evidence_have=have,
        evidence_missing=missing,
    )


# Acceptance states in which the clock has been fixed by the engine, so the
# buyer's "you never accepted" / "it was defective" answer is on record.
ACCEPTANCE_FIXED = frozenset({ACCEPTANCE_DEEMED, ACCEPTANCE_RESOLVED})
# Acceptance states in which it is not fixed yet, so those answers stand open.
ACCEPTANCE_UNSETTLED = frozenset({ACCEPTANCE_PENDING, ACCEPTANCE_NO_DELIVERY})


def _acceptance_verdict(acceptance_status: str | None) -> str:
    """One answer for the two acceptance-driven arguments.

    Fixed acceptance (deemed, or an objection raised in time and resolved) means
    the argument is answered; unfixed acceptance means it is not; no verdict at
    all means this module does not guess.
    """
    if acceptance_status is None:
        return STATUS_OPEN_QUESTION
    if acceptance_status in ACCEPTANCE_FIXED:
        return STATUS_STRONG
    if acceptance_status in ACCEPTANCE_UNSETTLED:
        return STATUS_AT_RISK
    return STATUS_OPEN_QUESTION  # a status this module does not recognise


# ----------------------------------------------------------------- the rule ----


def evaluate_defenses(
    *,
    gate_status: str,
    acceptance_status: str | None,
    agreed_days: int | None,
    credit_clamped: bool,
    limitation_status: str,
    evidence: Sequence[EvidenceLike] = (),
) -> DefensesResult:
    """Answer the seven buyer arguments from engine state (section 6.6).

    `gate_status`, `acceptance_status`, `agreed_days`/`credit_clamped` and
    `limitation_status` are the engine's own results from gate, acceptance and
    limitation. `evidence` is the request's evidence list.
    """
    held: dict[str, EvidenceLike] = {}
    for item in evidence:
        held[str(item.kind)] = item

    statuses: dict[str, str] = {}

    # -- defective goods and never accepted: is acceptance fixed? -----------
    verdict = _acceptance_verdict(acceptance_status)
    statuses["defective_goods"] = verdict
    statuses["never_accepted"] = verdict

    # -- the PO's longer credit period: did the statutory cap bite? ----------
    if agreed_days is None:
        # No written period held, and what counts as written is OQ-5.
        statuses["po_90_days"] = STATUS_OPEN_QUESTION
    elif credit_clamped:
        statuses["po_90_days"] = STATUS_STRONG
    else:
        statuses["po_90_days"] = STATUS_AT_RISK

    # -- not eligible: the gate's own verdict --------------------------------
    if gate_status == GATE_ELIGIBLE:
        statuses["not_eligible"] = STATUS_STRONG
    elif gate_status == GATE_INSUFFICIENT_DATA:
        statuses["not_eligible"] = STATUS_AT_RISK
    elif gate_status in GATE_BLOCKING:
        statuses["not_eligible"] = STATUS_AT_RISK
    else:
        statuses["not_eligible"] = STATUS_OPEN_QUESTION

    # -- arbitration and set-off are never decided here (OQ-7) ---------------
    statuses["arbitration_clause"] = STATUS_OPEN_QUESTION
    statuses["set_off"] = STATUS_OPEN_QUESTION

    # -- time-barred: read straight off the limitation band ------------------
    if limitation_status in LIMITATION_AT_RISK:
        statuses["time_barred"] = STATUS_AT_RISK
    elif limitation_status in LIMITATION_IN_TIME:
        statuses["time_barred"] = STATUS_STRONG
    else:
        # UNKNOWN, or a band this module does not recognise: no assertion.
        statuses["time_barred"] = STATUS_OPEN_QUESTION

    rows = [_defend(spec, statuses[spec.id], held) for spec in _ROW_SPECS]

    assumptions = [
        "A row's status answers the argument from the engine's own verdicts only; "
        "whether a document is also in the request is reported separately as evidence "
        "held or missing, so the two columns can be checked independently.",
        "An arbitration clause and a set-off claim are always shown as an open question "
        "and are never decided here (OQ-7).",
        "Where the engine has no verdict - no gate result, no agreed period, or an "
        "unknown limitation band - the row reads as an open question rather than "
        "guessing in either direction.",
        "All seven rows are always returned, in the same order, so the panel can be "
        "compared between cases and the guidance card's first at-risk row is stable.",
    ]

    return DefensesResult(
        rows=rows,
        citations=[],  # no config constant is read here; each row carries rule_ref
        warnings=[],
        assumptions=assumptions,
    )
