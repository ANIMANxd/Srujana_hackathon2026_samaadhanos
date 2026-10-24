"""limitation.py — the limitation clock (architecture.md section 6.5).

`expiry = due_date + limitation_years`, where `limitation_years` comes from
config and may be null.

Only **qualifying** acknowledgments move the clock: `is_signed` true and kind
in signed balance confirmation or part-payment. A WhatsApp promise is recorded
as a `potential_acknowledgment` warning and **never** restarts anything.

Status bands are read from `calculation_date`:

- `UNKNOWN` when `limitation_years` or the due date is unknown — an absence of
  a figure, never a finding that time has plenty left.
- `EXPIRED`, `WARN_6M`, `WARN_12M`, `OK` otherwise.

Two deliberate readings, both stated in `assumptions[]` rather than applied
silently: an acknowledgment only moves the clock *forward* from the current
anchor (a pre-due-date signature cannot shorten the window the statute gave),
and acknowledgments dated after the calculation date have not happened yet.

Pure: no file I/O, no clock. `calculation_date` always arrives in the request.
"""

from dataclasses import dataclass
from datetime import date
from typing import Protocol, Sequence

from backend.engine.config import StatuteConfig
from backend.engine.dates import add_months
from backend.engine.gate import GateCitation, GateWarning

# Status bands, matching LimitationStatus in backend/app/schemas.py.
STATUS_OK = "OK"
STATUS_WARN_12M = "WARN_12M"
STATUS_WARN_6M = "WARN_6M"
STATUS_EXPIRED = "EXPIRED"
STATUS_UNKNOWN = "UNKNOWN"

# The only kinds that can restart the clock (section 6.5).
RESTARTING_KINDS: frozenset[str] = frozenset(
    {"SIGNED_BALANCE_CONFIRMATION", "PART_PAYMENT"}
)

# Warning codes this module can raise.
WARNING_MISSING_LIMITATION_YEARS = "MISSING_LIMITATION_YEARS"
WARNING_NO_DUE_DATE = "NO_DUE_DATE"
WARNING_POTENTIAL_ACKNOWLEDGMENT = "POTENTIAL_ACKNOWLEDGMENT"

# Band boundaries, in calendar months measured from the calculation date.
WARN_6M_MONTHS = 6
WARN_12M_MONTHS = 12


class AcknowledgmentLike(Protocol):
    """The shape of an acknowledgment this module needs (contract: Acknowledgment)."""

    date: date
    kind: str
    is_signed: bool
    source_ref: str | None


# ------------------------------------------------------------ result types ----


@dataclass(frozen=True)
class LimitationEvent:
    """One acknowledgment as it appears on the clock: did it move the hand?"""

    date: date
    kind: str
    restarts_clock: bool

    def to_dict(self) -> dict[str, object]:
        return {"date": self.date, "kind": self.kind, "restarts_clock": self.restarts_clock}


@dataclass(frozen=True)
class LimitationResult:
    """The clock, its events, and everything the response needs to cite it."""

    expiry: date | None
    status: str
    events: list[LimitationEvent]
    citations: list[GateCitation]
    warnings: list[GateWarning]
    assumptions: list[str]

    def to_dict(self) -> dict[str, object]:
        """JSON-ready form matching the contract's `Limitation` block."""
        return {
            "expiry": self.expiry,
            "status": self.status,
            "events": [e.to_dict() for e in self.events],
        }


# ------------------------------------------------------------------ helpers ----


def _cite(config: StatuteConfig, key: str, rule: str) -> GateCitation:
    """A citation for one config key; reading it records usage (section 5)."""
    entry = config.entry(key)
    return GateCitation(
        id=f"limitation.{key}",
        rule=rule,
        statute_ref=entry.source_ref,
        config_key=key,
        verified=entry.verified,
    )


def _qualifies(ack: AcknowledgmentLike) -> bool:
    """Signed balance confirmations and part-payments only (section 6.5)."""
    return bool(ack.is_signed) and str(ack.kind) in RESTARTING_KINDS


def _band(expiry: date, calculation_date: date) -> str:
    """Where `expiry` sits relative to `calculation_date`.

    Calendar months, end-of-month clamped, so the band agrees with every other
    date step in the engine. The expiry date itself is still in time; only the
    day after it is expired.
    """
    if calculation_date > expiry:
        return STATUS_EXPIRED
    if expiry <= add_months(calculation_date, WARN_6M_MONTHS):
        return STATUS_WARN_6M
    if expiry <= add_months(calculation_date, WARN_12M_MONTHS):
        return STATUS_WARN_12M
    return STATUS_OK


# ----------------------------------------------------------------- the rule ----


def evaluate_limitation(
    config: StatuteConfig,
    *,
    due_date: date | None,
    calculation_date: date,
    acknowledgments: Sequence[AcknowledgmentLike] = (),
) -> LimitationResult:
    """Fix the expiry date, the status band, and which acknowledgments counted.

    `limitation_years` and the anchor date are read from config and the request;
    nothing here consults a clock or guesses a period.
    """
    citations: list[GateCitation] = []
    warnings: list[GateWarning] = []
    assumptions: list[str] = []

    years = config.limitation_years()
    citations.append(
        _cite(
            config,
            "limitation_years",
            "the limitation period for the price of goods or services",
        )
    )

    ordered = sorted(acknowledgments, key=lambda a: a.date)
    anchor = due_date
    events: list[LimitationEvent] = []
    potential: list[AcknowledgmentLike] = []

    for ack in ordered:
        qualifies = _qualifies(ack)
        restarts = False
        if not qualifies:
            if str(ack.kind) == "WHATSAPP_PROMISE":
                potential.append(ack)
        elif anchor is None:
            # No due date, so no clock is running yet: nothing to restart. The
            # expiry is unknown below and the warning says so.
            restarts = False
        elif ack.date > calculation_date:
            # Not happened as of the calculation date.
            restarts = False
        elif ack.date >= anchor:
            restarts = True
            anchor = ack.date  # the clock restarts from this acknowledgment
        events.append(
            LimitationEvent(date=ack.date, kind=str(ack.kind), restarts_clock=restarts)
        )

    if potential:
        listed = ", ".join(p.date.isoformat() for p in potential)
        warnings.append(
            GateWarning(
                code=WARNING_POTENTIAL_ACKNOWLEDGMENT,
                severity="INFO",
                text=(
                    "These promises to pay are recorded as potential acknowledgments "
                    f"but do not restart the limitation clock ({listed}). A promise in a "
                    "chat thread is not a signed balance confirmation or a part-payment; "
                    "only those two move the date shown here."
                ),
            )
        )

    expiry: date | None = None
    if years is None:
        warnings.append(
            GateWarning(
                code=WARNING_MISSING_LIMITATION_YEARS,
                severity="WARN",
                text=(
                    "The config has no limitation period, so no expiry date could be "
                    "computed. The status below is UNKNOWN: this is an absence of a "
                    "figure, not a finding that there is plenty of time left."
                ),
            )
        )
        status = STATUS_UNKNOWN
    elif due_date is None:
        warnings.append(
            GateWarning(
                code=WARNING_NO_DUE_DATE,
                severity="WARN",
                text=(
                    "There is no due date on this case, so the limitation clock has no "
                    "anchor. The status below is UNKNOWN until the due date is fixed."
                ),
            )
        )
        status = STATUS_UNKNOWN
    else:
        # add_months handles the leap-year clamp: 29 Feb + 12 years -> 28 Feb.
        expiry = add_months(anchor, 12 * years)  # type: ignore[arg-type]
        status = _band(expiry, calculation_date)

    assumptions.extend(
        [
            f"The expiry is the anchor date plus {years if years is not None else 'unknown'} "
            "year(s), where the anchor is the due date or, once one exists, the latest "
            "qualifying acknowledgment.",
            "Only a signed balance confirmation or a part-payment restarts the clock, and "
            "only when its date falls on or after the current anchor, so an older signature "
            "can never shorten the period the statute allows.",
            "Acknowledgments dated after the calculation date have not happened yet and "
            "are shown without restarting the clock.",
            "Bands are measured in calendar months from the calculation date: the expiry "
            "date itself is still in time, and the day after it reads EXPIRED.",
        ]
    )
    if status == STATUS_UNKNOWN:
        assumptions.append(
            "UNKNOWN means the inputs do not support a date, not that time remains."
        )

    return LimitationResult(
        expiry=expiry,
        status=status,
        events=events,
        citations=citations,
        warnings=warnings,
        assumptions=assumptions,
    )
