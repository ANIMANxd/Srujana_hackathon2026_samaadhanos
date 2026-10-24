"""acceptance.py — acceptance and due dates (architecture.md section 6.2).

The clock is anchored on **delivery_date**, never the invoice date (demo-critical
fact, section 7). From there:

- window end = delivery + `objection_window_days` (config only).
- A written objection raised on or before the window end holds the clock: the
  status stays PENDING_RESOLUTION until `resolved_date` exists, then acceptance
  becomes that resolved date. A qualifying objection that is never resolved
  leaves acceptance null rather than guessed at.
- Objections that are not written, or were raised after the window, are recorded
  in `late_complaints` and never move the clock.
- With no qualifying objection, acceptance is the delivery date (deemed
  acceptance).

The applied period comes from the agreement: no written credit period means
`no_agreement_days`; otherwise `min(agreed, credit_cap_days)`, with `clamped`
set when the agreed period exceeded the cap. **There is no regime logic** — the
cap applies to every supply regardless of when it happened (trap 2). Window
length and cap are read from config, never from literals.

`due_date = acceptance + applied_days`, `appointed_day = due_date + 1`, and
`days_overdue` counts calendar days past the due date, staying null until the
appointed day arrives.

`invoice_date` is accepted as an input but deliberately never anchors anything;
it exists in the signature so the "anchor on delivery, not invoice" rule is
testable rather than merely asserted in prose.

Pure module: no file I/O, no clock. `calculation_date` always arrives in the
request.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Protocol, Sequence

from backend.engine.config import ConfigError, StatuteConfig
from backend.engine.gate import GateCitation, GateWarning

# Objection statuses, aligned with ObjectionStatus in backend/app/schemas.py.
STATUS_NO_DELIVERY_PROOF = "NO_DELIVERY_PROOF"
STATUS_PENDING_RESOLUTION = "PENDING_RESOLUTION"
STATUS_RESOLVED = "RESOLVED"
STATUS_DEEMED_ACCEPTANCE = "DEEMED_ACCEPTANCE"

# Warning codes this module can raise.
WARNING_PENDING_RESOLUTION = "PENDING_RESOLUTION"
WARNING_UNCLASSIFIED_OBJECTIONS = "UNCLASSIFIED_OBJECTIONS"

# Objection reason strings for late_complaints. Plain English (AGENTS.md 5).
REASON_NOT_WRITTEN = (
    "The objection was not in writing, so it does not pause the acceptance clock "
    "(section 6.2)."
)


class ObjectionLike(Protocol):
    """The shape of an objection this module needs.

    Structural, so the API's Pydantic `Objection` satisfies it without the engine
    importing app-layer models.
    """

    raised_date: date
    is_written: bool
    description: str | None
    resolved_date: date | None


# ------------------------------------------------------------- result types ----


@dataclass(frozen=True)
class LateComplaint:
    """An objection that could not move the clock, and why."""

    date: date
    description: str | None
    reason: str

    def to_dict(self) -> dict[str, object]:
        return {"date": self.date, "description": self.description, "reason": self.reason}


@dataclass(frozen=True)
class AcceptanceResult:
    """The section 6.2 timeline block plus what the response needs to cite it.

    Fields mirror the contract's `Timeline` one for one. Date fields are null
    when the fact is unknown (no delivery proof, objection still pending), never
    a substitute date.
    """

    status: str
    delivery_date: date | None
    objection_window_end: date | None
    acceptance_date: date | None
    agreed_days: int | None
    applied_days: int | None
    clamped: bool
    due_date: date | None
    appointed_day: date | None
    days_overdue: int | None
    late_complaints: list[LateComplaint]
    citations: list[GateCitation]
    warnings: list[GateWarning]
    assumptions: list[str]

    def to_dict(self) -> dict[str, object]:
        """JSON-ready form matching the contract's `Timeline` block."""
        return {
            "delivery_date": self.delivery_date,
            "objection_window_end": self.objection_window_end,
            "objection_status": self.status,
            "acceptance_date": self.acceptance_date,
            "agreed_days": self.agreed_days,
            "applied_days": self.applied_days,
            "clamped": self.clamped,
            "due_date": self.due_date,
            "appointed_day": self.appointed_day,
            "days_overdue": self.days_overdue,
            "late_complaints": [c.to_dict() for c in self.late_complaints],
        }


# ------------------------------------------------------------------ helpers ----


def _cite(config: StatuteConfig, key: str, rule: str) -> GateCitation:
    """A citation for one config key.

    Reading the entry records usage, so the UNVERIFIED_CONSTANT warnings cover
    exactly the constants this module relied on (section 5).
    """
    entry = config.entry(key)
    return GateCitation(
        id=f"acceptance.{key}",
        rule=rule,
        statute_ref=entry.source_ref,
        config_key=key,
        verified=entry.verified,
    )


def _require(value, key: str, *, needed_for: str):
    """Read a statutory constant that must be present, or fail loudly.

    A null window length or cap would make the dates undecidable, and guessing
    one would be inventing law (golden rule 1), so this raises rather than
    defaulting. `StatuteConfig.warnings()` reports nulls separately.
    """
    if value is None:
        raise ConfigError(
            f"statute config value {key!r} is null, so {needed_for} cannot be computed; "
            "fill it from the statute sheet before evaluating this case"
        )
    return value


def _late_reason(objection: ObjectionLike, window_end: date | None) -> str:
    """Why this objection could not move the clock, covering every ground it hits."""
    grounds: list[str] = []
    if not objection.is_written:
        grounds.append("it was not in writing")
    if window_end is not None and objection.raised_date > window_end:
        grounds.append(
            f"it was raised on {objection.raised_date.isoformat()}, after the window "
            f"closed on {window_end.isoformat()}"
        )
    if not grounds:
        # Unreachable from the caller; kept so the reason is never blank.
        return REASON_NOT_WRITTEN
    return (
        "The objection does not pause the acceptance clock because "
        + " and ".join(grounds)
        + " (section 6.2)."
    )


# -------------------------------------------------------------- agreements ----


def _applied_period(
    config: StatuteConfig, written_credit_days: int | None
) -> tuple[int | None, int | None, bool, list[GateCitation], list[str]]:
    """Resolve agreed_days, applied_days and clamped (section 6.2, paragraph 3).

    No written credit period means `no_agreement_days`. Otherwise the applied
    period is `min(agreed, credit_cap_days)` and `clamped` records that the cap
    bit. The cap is read from config and applies to every supply.
    """
    citations: list[GateCitation] = []
    assumptions: list[str] = []

    if written_credit_days is None:
        applied = _require(
            config.no_agreement_days(), "no_agreement_days", needed_for="the no-agreement period"
        )
        citations.append(
            _cite(
                config,
                "no_agreement_days",
                "no written credit period was agreed, so the statutory period applies",
            )
        )
        assumptions.append(
            "No written credit period was supplied, so the period runs from the "
            "statute's no-agreement days. Whether some other document forms a written "
            "agreement is still open (OQ-5)."
        )
        return None, applied, False, citations, assumptions

    agreed = int(written_credit_days)
    cap = _require(
        config.credit_cap_days(), "credit_cap_days", needed_for="the credit-period cap"
    )
    citations.append(
        _cite(
            config,
            "credit_cap_days",
            "a written credit period was agreed, so the statutory cap is applied to it",
        )
    )
    assumptions.append(
        f"A written credit period of {agreed} days was supplied and is treated as a "
        "written agreement, such as a purchase order or a signed document. What "
        "counts as a written agreement is still open (OQ-5)."
    )
    return agreed, min(agreed, cap), agreed > cap, citations, assumptions


# ------------------------------------------------------------- objections ----


def _classify_objections(
    objections: Sequence[ObjectionLike], window_end: date
) -> tuple[list[ObjectionLike], list[LateComplaint]]:
    """Split objections into those that qualify and those recorded as late.

    A qualifying objection is written **and** raised on or before the window end,
    so the boundary day itself qualifies and the day after it does not.
    """
    qualifying: list[ObjectionLike] = []
    late: list[LateComplaint] = []
    for objection in objections:
        if objection.is_written and objection.raised_date <= window_end:
            qualifying.append(objection)
        else:
            late.append(
                LateComplaint(
                    date=objection.raised_date,
                    description=objection.description,
                    reason=_late_reason(objection, window_end),
                )
            )
    return qualifying, late


def _resolve_acceptance(
    delivery_date: date, qualifying: Sequence[ObjectionLike]
) -> tuple[str, date | None, list[GateWarning]]:
    """Fix the acceptance date from the qualifying objections (section 6.2).

    No qualifying objection means acceptance is the delivery date. A resolved
    objection makes acceptance its `resolved_date`. An unresolved one leaves the
    date unknown, so it comes back null with a warning rather than a guess.
    """
    if not qualifying:
        return STATUS_DEEMED_ACCEPTANCE, delivery_date, []

    unresolved = [o for o in qualifying if o.resolved_date is None]
    if unresolved:
        descriptions = "; ".join(
            f"raised {o.raised_date.isoformat()} ({o.description or 'no description given'})"
            for o in unresolved
        )
        return (
            STATUS_PENDING_RESOLUTION,
            None,
            [
                GateWarning(
                    code=WARNING_PENDING_RESOLUTION,
                    severity="WARN",
                    text=(
                        "A written objection inside the objection window has not been "
                        f"resolved ({descriptions}), so the acceptance date is not fixed "
                        "yet. Interest, due dates and limitation all wait on that "
                        "resolution date; they are left empty rather than estimated."
                    ),
                )
            ],
        )

    # Every qualifying objection is resolved. The clock resumes on the latest of
    # them, since acceptance cannot be fixed until the last objection is cleared.
    resolved_dates = [o.resolved_date for o in qualifying if o.resolved_date is not None]
    return STATUS_RESOLVED, max(resolved_dates), []


# ----------------------------------------------------------------- the rule ----


def evaluate_acceptance(
    config: StatuteConfig,
    *,
    invoice_date: date,
    delivery_date: date | None,
    calculation_date: date,
    objections: Sequence[ObjectionLike] = (),
    written_credit_days: int | None = None,
) -> AcceptanceResult:
    """Fix acceptance, due date and appointed day (section 6.2).

    `invoice_date` is accepted for parity with the contract and never used to
    anchor anything: delivery anchors the clock. `calculation_date` arrives in
    the request because the engine never reads a clock (section 6).

    Raises ConfigError when a statutory constant this rule needs is null, rather
    than substituting a default.
    """
    agreed, applied, clamped, citations, assumptions = _applied_period(
        config, written_credit_days
    )

    if delivery_date is None:
        # No anchor: no acceptance, no due date (section 6.2, first line).
        warnings: list[GateWarning] = []
        if objections:
            warnings.append(
                GateWarning(
                    code=WARNING_UNCLASSIFIED_OBJECTIONS,
                    severity="WARN",
                    text=(
                        f"This case has {len(objections)} objection(s) but no delivery "
                        "date, so the objection window cannot be placed and none of them "
                        "could be classified. Add delivery proof to fix the window."
                    ),
                )
            )
        return AcceptanceResult(
            status=STATUS_NO_DELIVERY_PROOF,
            delivery_date=None,
            objection_window_end=None,
            acceptance_date=None,
            agreed_days=agreed,
            applied_days=applied,
            clamped=clamped,
            due_date=None,
            appointed_day=None,
            days_overdue=None,
            late_complaints=[],
            citations=citations,
            warnings=warnings,
            assumptions=assumptions,
        )

    window_days = _require(
        config.objection_window_days(),
        "objection_window_days",
        needed_for="the objection window",
    )
    citations.append(
        _cite(
            config,
            "objection_window_days",
            "the written-objection window is measured from the delivery date",
        )
    )
    window_end = delivery_date + timedelta(days=window_days)

    qualifying, late = _classify_objections(objections, window_end)
    status, acceptance, warnings = _resolve_acceptance(delivery_date, qualifying)

    assumptions.append(
        "days_overdue counts calendar days after the due date and stays empty until "
        "the appointed day; the appointed day is the due date plus one day (section 6.2)."
    )

    if acceptance is None:
        due_date = None
        appointed_day = None
        days_overdue = None
    else:
        due_date = acceptance + timedelta(days=applied)
        appointed_day = due_date + timedelta(days=1)
        days_overdue = None if calculation_date < appointed_day else (calculation_date - due_date).days

    return AcceptanceResult(
        status=status,
        delivery_date=delivery_date,
        objection_window_end=window_end,
        acceptance_date=acceptance,
        agreed_days=agreed,
        applied_days=applied,
        clamped=clamped,
        due_date=due_date,
        appointed_day=appointed_day,
        days_overdue=days_overdue,
        late_complaints=late,
        citations=citations,
        warnings=warnings,
        assumptions=assumptions,
    )
