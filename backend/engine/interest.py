"""interest.py — the s.16 interest ledger (architecture.md section 6.3).

Statutory rate on any day is `interest_multiplier x bank_rate(day)`. Under
`FLOATING` the rate changes at Bank Rate epoch boundaries and the delay period is
split into segments; under `FROZEN_AT_APPOINTED_DAY` the epoch rate in force on
the appointed day applies to the whole period. `rate_segments[]` carries that
breakdown.

Monthly rests fall on `appointed_day + k calendar months`, end-of-month clamped.
Interest is simple inside each period and capitalised at the period boundary, so
**compounding applies to principal plus interest** — the balance has two buckets
and the accrual base is their sum. The final stub (last rest to the calculation
date) accrues simple interest.

Part-payments follow `PAYMENT_DATE_IS_REST_BOUNDARY`: interest accrues to the
payment date, is capitalised, the payment is applied, then a new rest cycle
starts from that date. The convention is stated in `assumptions[]` and is open
for lawyer review (OQ-3). A payment before the appointed day reduces principal
with no interest effect; a payment larger than the balance clears it and warns.

`INTEREST_FIRST` (default) drains the interest bucket before principal;
`PRINCIPAL_FIRST` does the reverse. The total balance is identical either way —
only the split differs, and `principal_outstanding` comes from that split.

Every ledger row is rounded half-up to 0.01, so `interest_total` equals the sum
of the rows exactly. Money is `decimal.Decimal`; there is no float arithmetic
anywhere in this module.

Pure: no file I/O, no clock. The calculation date always arrives in the request.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol, Sequence

from backend.engine.config import ConfigError, StatuteConfig
from backend.engine.dates import add_months
from backend.engine.gate import GateCitation, GateWarning
from backend.engine.money import as_percent, parse_money, rupees

# Rate modes (config `rate_mode_default`, OQ-4).
RATE_MODE_FLOATING = "FLOATING"
RATE_MODE_FROZEN = "FROZEN_AT_APPOINTED_DAY"
RATE_MODES = (RATE_MODE_FLOATING, RATE_MODE_FROZEN)

# Appropriation modes (config `appropriation_mode_default`).
APPROPRIATION_INTEREST_FIRST = "INTEREST_FIRST"
APPROPRIATION_PRINCIPAL_FIRST = "PRINCIPAL_FIRST"
APPROPRIATION_MODES = (APPROPRIATION_INTEREST_FIRST, APPROPRIATION_PRINCIPAL_FIRST)

# The payment convention this module implements (OQ-3).
CONVENTION_PAYMENT_DATE_IS_REST_BOUNDARY = "PAYMENT_DATE_IS_REST_BOUNDARY"

# Ledger row kinds, matching LedgerKind in backend/app/schemas.py.
KIND_REST = "REST"
KIND_PAYMENT = "PAYMENT"
KIND_STUB = "STUB"

# Warning codes this module can raise.
WARNING_OVERPAYMENT = "OVERPAYMENT"


class InterestInputError(ValueError):
    """An input is unusable for interest math. Plain English, no guessing."""


class PaymentLike(Protocol):
    """The shape of a part-payment this module needs (contract: PartPayment)."""

    date: date
    amount: object


# ------------------------------------------------------------ result types ----


@dataclass(frozen=True)
class RateSegment:
    """A span of days at one constant statutory rate.

    Half-open: `from_date` is the first day at this rate, `to_date` is the
    exclusive end, so consecutive segments abut without double-counting a day
    and the segment days sum to `to_date - from_date` over the whole period.
    """

    from_date: date
    to_date: date
    bank_rate_pct: Decimal
    statutory_rate_pct: Decimal

    @property
    def days(self) -> int:
        return (self.to_date - self.from_date).days

    def to_dict(self) -> dict[str, object]:
        return {
            "from": self.from_date,
            "to": self.to_date,
            "bank_rate_pct": self.bank_rate_pct,
            "statutory_rate_pct": self.statutory_rate_pct,
        }


@dataclass(frozen=True)
class LedgerRow:
    """One row of the printed ledger. `opening + interest - payment = closing`."""

    kind: str
    from_date: date
    to_date: date
    opening: Decimal
    interest: Decimal
    payment: Decimal
    closing: Decimal
    rate_pct: Decimal
    note: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "from": self.from_date,
            "to": self.to_date,
            "opening": self.opening,
            "interest": self.interest,
            "payment": self.payment,
            "closing": self.closing,
            "rate_pct": self.rate_pct,
            "note": self.note,
        }


@dataclass(frozen=True)
class InterestResult:
    """Everything section 6.3 asks the ledger to output, plus citation blocks."""

    rate_mode: str
    appropriation_mode: str
    payment_boundary_convention: str
    rate_segments: list[RateSegment]
    ledger: list[LedgerRow]
    interest_total: Decimal
    principal_outstanding: Decimal
    interest_outstanding: Decimal
    total_claim: Decimal
    daily_accrual: Decimal
    citations: list[GateCitation]
    warnings: list[GateWarning]
    assumptions: list[str]
    # Engine-internal, not part of to_dict(): (effective from date, principal
    # bucket) ascending, used by buyer_cost for the 43B(h) checkpoints.
    principal_timeline: list[tuple[date, Decimal]]

    def to_dict(self) -> dict[str, object]:
        """JSON-ready form matching the contract's `Financials` block."""
        return {
            "rate_mode": self.rate_mode,
            "appropriation_mode": self.appropriation_mode,
            "payment_boundary_convention": self.payment_boundary_convention,
            "rate_segments": [s.to_dict() for s in self.rate_segments],
            "ledger": [r.to_dict() for r in self.ledger],
            "interest_total": self.interest_total,
            "principal_outstanding": self.principal_outstanding,
            "interest_outstanding": self.interest_outstanding,
            "total_claim": self.total_claim,
            "daily_accrual": self.daily_accrual,
        }


# ------------------------------------------------------------------ helpers ----


def _cite(config: StatuteConfig, key: str, rule: str) -> GateCitation:
    """A citation for one config key; reading it records usage (section 5)."""
    entry = config.entry(key)
    return GateCitation(
        id=f"interest.{key}",
        rule=rule,
        statute_ref=entry.source_ref,
        config_key=key,
        verified=entry.verified,
    )


def _require(value, key: str, *, needed_for: str):
    """Read a statutory constant that must be present, or fail loudly."""
    if value is None:
        raise ConfigError(
            f"statute config value {key!r} is null, so {needed_for} cannot be computed; "
            "fill it from the statute sheet before evaluating this case"
        )
    return value


def _mode(value: str | None, *, from_config, config: StatuteConfig, key: str, allowed, needed_for) -> tuple[str, list[GateCitation]]:
    """Resolve a mode from the argument, else the configured default.

    Falling back to config records a citation so the default's verified flag
    reaches the response rather than being applied silently.
    """
    citations: list[GateCitation] = []
    if value is None:
        value = _require(from_config(), key, needed_for=needed_for)
        citations.append(_cite(config, key, f"the {needed_for} came from the configured default"))
    resolved = str(value).upper()
    if resolved not in allowed:
        raise ConfigError(
            f"{needed_for} must be one of {', '.join(allowed)}, not {value!r}"
        )
    return resolved, citations


def _segments_overlapping(
    segments: Sequence[RateSegment], from_d: date, to_d: date
) -> list[tuple[RateSegment, int]]:
    """The parts of `segments` inside [from_d, to_d), with each part's day count."""
    out: list[tuple[RateSegment, int]] = []
    for segment in segments:
        lo = max(segment.from_date, from_d)
        hi = min(segment.to_date, to_d)
        if lo < hi:
            out.append((segment, (hi - lo).days))
    return out


def _accrual(
    segments: Sequence[RateSegment], base: Decimal, from_d: date, to_d: date, day_count: int
) -> Decimal:
    """Unrounded simple interest on `base` across [from_d, to_d).

    Each rate-constant sub-span accrues on the same base, because interest inside
    a period is simple: only a rest, a payment or the calculation date changes
    the balance. Rounding happens once per ledger row, not per sub-span.
    """
    total = Decimal("0")
    for segment, days in _segments_overlapping(segments, from_d, to_d):
        total += base * as_percent(segment.statutory_rate_pct) * days
    if total == 0:
        return Decimal("0")
    return total / day_count


def _appropriate(
    principal_bal: Decimal, interest_bal: Decimal, applied: Decimal, mode: str
) -> tuple[Decimal, Decimal]:
    """Split an applied payment across the two buckets.

    The buckets always sum to `balance - applied`, so the total is identical in
    either mode; only the split differs.
    """
    if mode == APPROPRIATION_INTEREST_FIRST:
        from_interest = min(applied, interest_bal)
        interest_bal -= from_interest
        principal_bal -= applied - from_interest
    else:
        from_principal = min(applied, principal_bal)
        principal_bal -= from_principal
        interest_bal -= applied - from_principal
    return principal_bal, interest_bal


def _build_segments(
    config: StatuteConfig,
    start: date,
    end: date,
    rate_mode: str,
    multiplier: Decimal,
    frozen_bank_rate: Decimal | None,
) -> list[RateSegment]:
    """The rate-constant spans covering [start, end) for the active rate mode."""
    if end <= start:
        return []
    if rate_mode == RATE_MODE_FROZEN:
        assert frozen_bank_rate is not None
        return [RateSegment(start, end, frozen_bank_rate, multiplier * frozen_bank_rate)]

    boundaries = sorted(
        {
            epoch.from_date
            for epoch in config.bank_rate_epochs()
            if epoch.from_date is not None and start < epoch.from_date < end
        }
    )
    segments: list[RateSegment] = []
    cursor = start
    for boundary in [*boundaries, end]:
        if boundary > cursor:
            bank_rate = config.bank_rate_on(cursor)
            segments.append(
                RateSegment(cursor, boundary, bank_rate, multiplier * bank_rate)
            )
            cursor = boundary
    return segments


def _rate_on(
    config: StatuteConfig,
    day: date,
    rate_mode: str,
    multiplier: Decimal,
    frozen_bank_rate: Decimal | None,
) -> Decimal:
    """The statutory rate in force on `day` under the active rate mode."""
    if rate_mode == RATE_MODE_FROZEN:
        assert frozen_bank_rate is not None
        return multiplier * frozen_bank_rate
    return config.statutory_rate_on(day)


# ----------------------------------------------------------------- the rule ----


def evaluate_interest(
    config: StatuteConfig,
    *,
    principal,
    appointed_day: date,
    calculation_date: date,
    part_payments: Sequence[PaymentLike] = (),
    rate_mode: str | None = None,
    appropriation_mode: str | None = None,
) -> InterestResult:
    """Build the interest ledger (section 6.3).

    `principal` may be a Decimal or a decimal string; floats are rejected.
    `rate_mode` and `appropriation_mode` default to their config values when
    omitted, which is what records their citation.

    Raises ConfigError for a null statutory constant or an unknown mode, and
    InterestInputError for an unusable principal or payment amount.
    """
    citations: list[GateCitation] = []
    warnings: list[GateWarning] = []
    assumptions: list[str] = []

    principal_bal = parse_money(principal)
    if principal_bal < 0:
        raise InterestInputError("principal cannot be negative")

    day_count = _require(
        config.day_count_fraction_days(),
        "day_count_fraction_days",
        needed_for="stub interest",
    )
    citations.append(
        _cite(
            config,
            "day_count_fraction_days",
            "interest for a partial period is divided by the day-count fraction",
        )
    )

    multiplier_entry = config.entry("interest_multiplier")
    if multiplier_entry.value is None:
        raise ConfigError(
            "statute config value 'interest_multiplier' is null, so the statutory rate "
            "cannot be computed; fill it from the statute sheet before evaluating this case"
        )
    multiplier = Decimal(str(multiplier_entry.value))
    citations.append(
        GateCitation(
            id="interest.interest_multiplier",
            rule="the statutory rate is the configured multiple of the Bank Rate",
            statute_ref=multiplier_entry.source_ref,
            config_key="interest_multiplier",
            verified=multiplier_entry.verified,
        )
    )

    rate_mode, rate_citations = _mode(
        rate_mode,
        from_config=config.rate_mode_default,
        config=config,
        key="rate_mode_default",
        allowed=RATE_MODES,
        needed_for="rate mode",
    )
    citations.extend(rate_citations)

    appropriation_mode, app_citations = _mode(
        appropriation_mode,
        from_config=config.appropriation_mode_default,
        config=config,
        key="appropriation_mode_default",
        allowed=APPROPRIATION_MODES,
        needed_for="appropriation mode",
    )
    citations.extend(app_citations)

    convention = _require(
        config.payment_boundary_convention(),
        "payment_boundary_convention",
        needed_for="the part-payment convention",
    )
    if convention != CONVENTION_PAYMENT_DATE_IS_REST_BOUNDARY:
        raise ConfigError(
            f"payment_boundary_convention {convention!r} is not implemented; this module "
            f"only supports {CONVENTION_PAYMENT_DATE_IS_REST_BOUNDARY}"
        )
    citations.append(
        _cite(
            config,
            "payment_boundary_convention",
            "part-payments are treated as rest boundaries (OQ-3)",
        )
    )

    frozen_bank_rate: Decimal | None = None
    # The rate is only read once there is a period to price. Before the appointed
    # day nothing accrues, so reading (and citing) it would report a constant no
    # computation used.
    rates_read = calculation_date >= appointed_day
    if rates_read and rate_mode == RATE_MODE_FROZEN:
        # The epoch rate in force on the appointed day governs the whole period.
        frozen_bank_rate = config.bank_rate_on(appointed_day)

    segments = _build_segments(
        config, appointed_day, calculation_date, rate_mode, multiplier, frozen_bank_rate
    )
    if rates_read:
        citations.append(
            _cite(
                config,
                "bank_rate_epochs",
                "the statutory rate follows the Bank Rate in force on each day of the delay",
            )
        )

    assumptions.extend(
        [
            f"Part-payments follow {convention}: interest accrues to the payment date, is "
            "capitalised, the payment is applied, and the monthly rest cycle restarts "
            "from that date. The convention is shown on screen and is flagged for lawyer "
            "review (OQ-3).",
            (
                f"Rate mode {rate_mode}: "
                + (
                    "the Bank Rate epoch in force on the appointed day applies to the "
                    "whole delay, so no rate change mid-delay alters the figure (OQ-4)."
                    if rate_mode == RATE_MODE_FROZEN
                    else "the rate changes at each Bank Rate epoch boundary inside the "
                    "delay, so a mid-delay change is split across rate segments (OQ-4)."
                )
            ),
            f"Appropriation mode {appropriation_mode} changes only how a payment is split "
            "between principal and interest; the total balance is the same either way. "
            "The split feeds the 43B(h) base, it is not added to interest loss.",
            "rate_segments cover [from, to): `from` is the first day at that rate and "
            "`to` is the exclusive end, so segment days sum to the delay length.",
        ]
    )

    interest_bal = Decimal("0")
    ledger: list[LedgerRow] = []
    # Principal bucket over time, (effective from date, balance). Starts at
    # date.min so any later date resolves to the opening principal, and gains an
    # entry after every payment. Section 6.4 needs the principal outstanding at
    # each 31 March, which only this walk knows; it is engine-internal and is
    # deliberately absent from to_dict(), so the contract is untouched.
    principal_timeline: list[tuple[date, Decimal]] = [(date.min, principal_bal)]

    def _balance() -> Decimal:
        return principal_bal + interest_bal

    def _rate_at(day: date) -> Decimal:
        return _rate_on(config, day, rate_mode, multiplier, frozen_bank_rate)

    def _emit_accrual(from_d: date, to_d: date, kind: str, note: str | None) -> None:
        nonlocal interest_bal
        opening = _balance()
        interest = rupees(_accrual(segments, opening, from_d, to_d, day_count))
        overlap = _segments_overlapping(segments, from_d, to_d)
        if len(overlap) > 1:
            changed = "Rate changed during this row; see rate_segments for the split. "
            note = (changed + note) if note else changed.rstrip()
        ledger.append(
            LedgerRow(
                kind=kind,
                from_date=from_d,
                to_date=to_d,
                opening=opening,
                interest=interest,
                payment=Decimal("0.00"),
                closing=opening + interest,
                rate_pct=_rate_at(from_d),
                note=note,
            )
        )
        interest_bal += interest  # capitalised onto the balance

    # Payments dated before the appointed day reduce principal only: no interest
    # has accrued yet, and they do not move the rest cycle.
    overdue = [p for p in part_payments if p.date < appointed_day]
    for payment in sorted(overdue, key=lambda p: p.date):
        amount = _payment_amount(payment)
        balance = _balance()
        applied = min(amount, balance)
        excess = amount - applied
        ledger.append(
            LedgerRow(
                kind=KIND_PAYMENT,
                from_date=payment.date,
                to_date=payment.date,
                opening=balance,
                interest=Decimal("0.00"),
                payment=applied,
                closing=balance - applied,
                rate_pct=Decimal("0.00"),
                note="Paid before the appointed day, so it reduces principal only and "
                "no interest accrues on it.",
            )
        )
        principal_bal -= applied
        principal_timeline.append((payment.date, principal_bal))
        if excess > 0:
            _warn_overpayment(warnings, payment, excess, balance - applied)

    pending = sorted(
        (p for p in part_payments if appointed_day <= p.date <= calculation_date),
        key=lambda p: p.date,
    )

    anchor = appointed_day
    rest_origin = appointed_day
    rest_index = 1
    base = _balance()  # accrual base: fixed for the whole rest period
    pay_index = 0

    while anchor < calculation_date:
        next_rest = add_months(rest_origin, rest_index)
        candidates: list[tuple[str, date]] = []
        if next_rest <= calculation_date:
            candidates.append((KIND_REST, next_rest))
        if pay_index < len(pending):
            candidates.append((KIND_PAYMENT, pending[pay_index].date))
        candidates.append((KIND_STUB, calculation_date))
        # Ties resolve rest, then payment, then the calculation date, so a payment
        # falling on a rest date is capitalised before it is applied.
        precedence = {KIND_REST: 0, KIND_PAYMENT: 1, KIND_STUB: 2}
        kind, boundary = min(candidates, key=lambda kv: (kv[1], precedence[kv[0]]))

        if boundary > anchor:
            if kind == KIND_REST:
                _emit_accrual(
                    anchor,
                    boundary,
                    KIND_REST,
                    "Monthly rest: interest capitalised onto the balance.",
                )
            elif kind == KIND_PAYMENT:
                _emit_accrual(
                    anchor,
                    boundary,
                    KIND_STUB,
                    "Interest accrued to the payment date, then capitalised before the "
                    "payment is applied.",
                )
            else:
                _emit_accrual(
                    anchor,
                    boundary,
                    KIND_STUB,
                    "Interest accrued from the last rest to the calculation date; "
                    "not capitalised further.",
                )
            anchor = boundary

        if kind == KIND_REST:
            rest_index += 1
            base = _balance()
            continue

        if kind == KIND_PAYMENT:
            payment = pending[pay_index]
            pay_index += 1
            amount = _payment_amount(payment)
            balance = _balance()
            applied = min(amount, balance)
            excess = amount - applied
            ledger.append(
                LedgerRow(
                    kind=KIND_PAYMENT,
                    from_date=anchor,
                    to_date=anchor,
                    opening=balance,
                    interest=Decimal("0.00"),
                    payment=applied,
                    closing=balance - applied,
                    rate_pct=_rate_at(anchor),
                    note="Part-payment treated as a rest boundary (OQ-3).",
                )
            )
            principal_bal, interest_bal = _appropriate(
                principal_bal, interest_bal, applied, appropriation_mode
            )
            principal_timeline.append((anchor, principal_bal))
            if excess > 0:
                _warn_overpayment(warnings, payment, excess, _balance())
            # A new rest cycle starts from the payment date.
            rest_origin = anchor
            rest_index = 1
            base = _balance()
            continue

        anchor = boundary  # reached the calculation date

    total_claim = _balance()
    if calculation_date >= appointed_day and total_claim > 0:
        daily_accrual = rupees(
            total_claim * as_percent(_rate_at(calculation_date)) / day_count
        )
    else:
        daily_accrual = Decimal("0.00")

    interest_total = sum((row.interest for row in ledger), Decimal("0"))

    return InterestResult(
        rate_mode=rate_mode,
        appropriation_mode=appropriation_mode,
        payment_boundary_convention=convention,
        rate_segments=segments,
        ledger=ledger,
        interest_total=interest_total,
        principal_outstanding=principal_bal,
        interest_outstanding=interest_bal,
        total_claim=total_claim,
        daily_accrual=daily_accrual,
        citations=citations,
        warnings=warnings,
        assumptions=assumptions,
        principal_timeline=principal_timeline,
    )


def _payment_amount(payment: PaymentLike) -> Decimal:
    """Parse and sanity-check one part-payment amount."""
    amount = parse_money(payment.amount)
    if amount <= 0:
        raise InterestInputError(
            f"the part-payment on {payment.date.isoformat()} must be a positive amount, "
            f"not {amount}"
        )
    return amount


def _warn_overpayment(
    warnings: list[GateWarning], payment: PaymentLike, excess: Decimal, remaining: Decimal
) -> None:
    """Flag a payment larger than the balance (section 6.3, section 11)."""
    warnings.append(
        GateWarning(
            code=WARNING_OVERPAYMENT,
            severity="WARN",
            text=(
                f"The payment of {payment.amount} on {payment.date.isoformat()} was larger "
                f"than the balance owed. It cleared the claim and {excess} of it is not "
                f"applied to this debt; {remaining} remained before the payment. Check "
                "whether the payment belongs to a different invoice."
            ),
        )
    )
