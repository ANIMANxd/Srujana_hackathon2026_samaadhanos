"""Pure per-customer payment statistics for the v5 Customer book.

Inputs are explicit: cases with their latest engine evaluation, the payments the
owner recorded, the read date (`as_of`) and the product config. There is no I/O,
no clock and no network, and every rupee is a `Decimal`.

The rule that matters most: **the engine computes the legal figures**. This
module reads `timeline.acceptance_date`, `timeline.due_date`,
`financials.interest_total` and `financials.total_claim` from the stored
evaluation. It never recomputes interest or a due date. It only does descriptive
arithmetic over those figures and over payment dates.

Partial payments stay open. An invoice is paid only when the non-voided payments
sum to at least the invoice amount. When the latest evaluation has no
appropriation, outstanding falls back to `amount - payments` and an explicit
assumption says so.

Outputs are descriptive only: no score, rating, rank, risk label or prediction.
The only estimate in the customer book is the portfolio cash-in estimate, which
lives in `backend.insights.insights` behind a config flag and is labelled.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

TWO_PLACES = Decimal("0.01")
ONE_HUNDRED = Decimal("100")

# Series statuses. These describe the invoice, not the buyer.
STATUS_PAID = "PAID"
STATUS_OVERDUE = "OVERDUE"
STATUS_NOT_DUE = "NOT_DUE"
STATUS_NO_DUE_DATE = "NO_DUE_DATE"

NOT_ENOUGH_HISTORY = "NOT_ENOUGH_HISTORY"

# Assumption codes/texts. They are plain English for the assumptions drawer.
ASSUMPTION_NO_ENGINE_EVALUATION = (
    "No engine evaluation is stored for {invoice}; its outstanding uses the "
    "invoice amount less recorded payments."
)
ASSUMPTION_NO_ENGINE_APPROPRIATION = (
    "The latest engine evaluation for {invoice} has no appropriation, so its "
    "outstanding uses the invoice amount less recorded payments."
)
ASSUMPTION_INTEREST_EXCLUDES_UNKNOWN = (
    "Interest accrued excludes invoices whose latest engine evaluation has no "
    "interest figure."
)
ASSUMPTION_AVERAGES_EXCLUDE_UNDATED = (
    "Averages use only fully paid invoices that have both an engine acceptance "
    "date and a payment date."
)
ASSUMPTION_PAYMENTS_EXCEED_AMOUNT = (
    "Recorded payments for {invoice} exceed the invoice amount; the invoice is "
    "treated as paid and outstanding is zero."
)
ASSUMPTION_NO_DUE_DATE = (
    "At least one invoice has no engine due date; its series status is "
    "NO_DUE_DATE and it is not counted as overdue."
)
ASSUMPTION_ENGINE_PAYMENTS_DIFFER = (
    "The latest engine evaluation's payment rows do not match the owner-recorded "
    "payments for {invoice}; the engine's outstanding figure is used."
)
ASSUMPTION_ON_TIME_EXCLUDES_UNDATED = (
    "The on-time percentage counts only fully paid invoices that have an engine "
    "due date and a final payment date."
)


def _as_decimal(value: Any, *, label: str) -> Decimal:
    """Decimal in, Decimal out; floats are refused rather than coerced."""
    if isinstance(value, bool) or isinstance(value, float):
        raise TypeError(
            f"{label} must be Decimal or a decimal string, never float "
            f"(got {type(value).__name__})"
        )
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except Exception as exc:  # noqa: BLE001 - all conversions fail the same way
        raise ValueError(f"{label} must be a decimal, got {value!r}") from exc
    if not result.is_finite():
        raise ValueError(f"{label} must be finite, got {result!r}")
    return result


def _optional_decimal(value: Any, *, label: str) -> Decimal | None:
    return None if value is None else _as_decimal(value, label=label)


def q2(value: Decimal) -> Decimal:
    """Round to paise, half-up, at the output boundary only."""
    return value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def _optional_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value)
    raise TypeError(f"date value must be an ISO string or date, got {type(value).__name__}")


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _days_between(later: date, earlier: date) -> int:
    return (later - earlier).days


@dataclass(frozen=True)
class InsightsConfig:
    """The product settings for this module.

    `min_history` and `concentration_flag_pct` are product settings, not law
    (AGENTS.md rule 27). The app reads them from `insights` in the statute
    config, where both ship with `verified=false` and the note
    "product setting, not law". `credit_cap_days` is the engine's s.15 cap from
    the same config; it is used only to phrase the terms flag, never to compute
    interest.
    """

    min_history: int = 3
    concentration_flag_pct: Decimal = Decimal("40")
    credit_cap_days: int | None = None
    cash_in_estimate_enabled: bool = False

    def __post_init__(self) -> None:
        if isinstance(self.min_history, bool) or not isinstance(self.min_history, int):
            raise TypeError("min_history must be an integer")
        if self.min_history < 1:
            raise ValueError("min_history must be at least 1")
        concentration = self.concentration_flag_pct
        if isinstance(concentration, bool) or isinstance(concentration, float):
            raise TypeError("concentration_flag_pct must be Decimal or a decimal string")
        concentration = (
            concentration
            if isinstance(concentration, Decimal)
            else Decimal(str(concentration))
        )
        if not concentration.is_finite() or not 0 <= concentration <= ONE_HUNDRED:
            raise ValueError("concentration_flag_pct must be between 0 and 100")
        cap = self.credit_cap_days
        if cap is not None and (isinstance(cap, bool) or not isinstance(cap, int) or cap < 0):
            raise ValueError("credit_cap_days must be a non-negative integer or None")
        if not isinstance(self.cash_in_estimate_enabled, bool):
            raise TypeError("cash_in_estimate_enabled must be a boolean")
        object.__setattr__(self, "concentration_flag_pct", concentration)


@dataclass(frozen=True)
class PaymentRecord:
    """One owner-recorded payment. Voided payments are ignored, not deleted."""

    payment_id: str
    case_id: str
    amount: Decimal
    paid_on: date
    voided_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "amount", _as_decimal(self.amount, label="payment amount")
        )
        if isinstance(self.paid_on, datetime) or not isinstance(self.paid_on, date):
            raise TypeError("paid_on must be a date")


@dataclass(frozen=True)
class TrackSummary:
    """The v4 track facts the customer page may show. No legal conclusion."""

    kind: str
    state: str
    version: int = 1
    created_at: datetime | None = None


@dataclass(frozen=True)
class CaseSnapshot:
    """One stored case plus its latest engine evaluation.

    `evaluation` is the engine response as stored (a mapping). `invoice_date` is
    kept for traceability only: days-to-pay are measured from the engine's
    `timeline.acceptance_date`, never from the invoice date.
    """

    case_id: str
    customer_id: str
    customer_name: str
    invoice_no: str
    invoice_date: date
    accepted_amount: Decimal
    evaluation: Mapping[str, Any] | None = None
    active_track: TrackSummary | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "accepted_amount",
            _as_decimal(self.accepted_amount, label="accepted_amount"),
        )
        if self.evaluation is not None and not isinstance(self.evaluation, Mapping):
            raise TypeError("evaluation must be a mapping or None")
        if isinstance(self.invoice_date, datetime) or not isinstance(self.invoice_date, date):
            raise TypeError("invoice_date must be a date")


@dataclass(frozen=True)
class InvoiceSeriesPoint:
    """One point of the customer's invoice chart.

    `days_to_pay` is set only for a fully paid invoice; an open invoice carries
    `days_open_so_far`. `legal_due_days` is `due_date - acceptance_date` from the
    engine, never a recomputed statutory period.
    """

    case_id: str
    invoice_no: str
    accepted_on: date | None
    due_date: date | None
    legal_due_days: int | None
    days_to_pay: int | None
    days_open_so_far: int | None
    days_overdue: int | None
    status: str
    outstanding: Decimal
    on_time: bool | None
    based_on_n: int


@dataclass(frozen=True)
class _InvoiceFacts:
    case: CaseSnapshot
    fully_paid: bool
    paid_sum: Decimal
    final_payment_on: date | None
    accepted_on: date | None
    due_date: date | None
    legal_due_days: int | None
    days_to_pay: int | None
    days_open_so_far: int | None
    days_overdue: int | None
    status: str
    outstanding: Decimal
    interest_total: Decimal | None
    on_time: bool | None
    assumptions: tuple[str, ...]


@dataclass(frozen=True)
class CustomerStatsResult:
    """Descriptive payment history for one customer.

    `based_on_n` is the number of fully paid invoices with usable engine and
    payment dates, i.e. the sample behind the averages. `paid_count` is the
    number of fully paid invoices; `history_sufficient` is
    `paid_count >= min_history`, as the task defines it.
    """

    customer_id: str
    customer_name: str
    as_of: date
    invoices_count: int
    total_billed: Decimal
    outstanding: Decimal
    overdue_amount: Decimal
    interest_accrued_now: Decimal
    paid_count: int
    based_on_n: int
    history_sufficient: bool
    avg_days_to_pay: Decimal | None
    median_days_to_pay: Decimal | None
    worst_days_to_pay: Decimal | None
    on_time_count: int
    on_time_pct: Decimal | None
    history_reason: str | None
    series: tuple[InvoiceSeriesPoint, ...]
    last_payment_on: date | None
    active_track: TrackSummary | None
    assumptions: tuple[str, ...]
    min_history: int


def _mean(values: Sequence[int]) -> Decimal:
    return Decimal(sum(values)) / Decimal(len(values))


def _median(values: Sequence[int]) -> Decimal:
    ordered = sorted(values)
    count = len(ordered)
    middle = count // 2
    if count % 2:
        return Decimal(ordered[middle])
    return (Decimal(ordered[middle - 1]) + Decimal(ordered[middle])) / Decimal(2)


def _format_days(value: Decimal) -> str:
    text = format(q2(value), "f").rstrip("0").rstrip(".")
    return text or "0"


def _invoice_facts(
    case: CaseSnapshot,
    payments: Sequence[PaymentRecord],
    as_of: date,
) -> _InvoiceFacts:
    active_payments = [payment for payment in payments if payment.voided_at is None]
    paid_sum = sum((payment.amount for payment in active_payments), Decimal("0.00"))
    accepted = case.accepted_amount
    fully_paid = paid_sum >= accepted
    final_payment_on = (
        max(payment.paid_on for payment in active_payments)
        if active_payments
        else None
    )

    evaluation = case.evaluation or {}
    timeline = _mapping(evaluation.get("timeline"))
    financials = _mapping(evaluation.get("financials"))
    accepted_on = _optional_date(timeline.get("acceptance_date"))
    due_date = _optional_date(timeline.get("due_date"))
    interest_total = _optional_decimal(
        financials.get("interest_total"), label="engine interest_total"
    )
    total_claim = _optional_decimal(
        financials.get("total_claim"), label="engine total_claim"
    )

    assumptions: list[str] = []
    if fully_paid:
        outstanding = Decimal("0.00")
        if paid_sum > accepted:
            assumptions.append(
                ASSUMPTION_PAYMENTS_EXCEED_AMOUNT.format(invoice=case.invoice_no)
            )
    elif total_claim is not None:
        outstanding = max(total_claim, Decimal("0.00"))
    else:
        outstanding = max(accepted - paid_sum, Decimal("0.00"))
        assumptions.append(
            (
                ASSUMPTION_NO_ENGINE_EVALUATION
                if case.evaluation is None
                else ASSUMPTION_NO_ENGINE_APPROPRIATION
            ).format(invoice=case.invoice_no)
        )

    if financials:
        engine_payments = Decimal("0.00")
        ledger = financials.get("ledger")
        if isinstance(ledger, list):
            for row in ledger:
                if not isinstance(row, Mapping) or row.get("kind") != "PAYMENT":
                    continue
                raw_payment = row.get("payment")
                if raw_payment is not None:
                    engine_payments += _as_decimal(
                        raw_payment, label="engine ledger payment"
                    )
        if engine_payments != paid_sum:
            assumptions.append(
                ASSUMPTION_ENGINE_PAYMENTS_DIFFER.format(invoice=case.invoice_no)
            )

    if due_date is None:
        status = STATUS_NO_DUE_DATE if not fully_paid else STATUS_PAID
    elif fully_paid:
        status = STATUS_PAID
    elif due_date < as_of:
        status = STATUS_OVERDUE
    else:
        status = STATUS_NOT_DUE

    days_overdue: int | None
    if fully_paid:
        days_overdue = 0
    elif due_date is None:
        days_overdue = None
    else:
        days_overdue = max(_days_between(as_of, due_date), 0)

    legal_due_days = (
        _days_between(due_date, accepted_on)
        if due_date is not None and accepted_on is not None
        else None
    )
    days_to_pay = (
        _days_between(final_payment_on, accepted_on)
        if fully_paid and final_payment_on is not None and accepted_on is not None
        else None
    )
    days_open_so_far = (
        max(_days_between(as_of, accepted_on), 0)
        if not fully_paid and accepted_on is not None
        else None
    )
    on_time = (
        final_payment_on <= due_date
        if fully_paid and final_payment_on is not None and due_date is not None
        else None
    )

    return _InvoiceFacts(
        case=case,
        fully_paid=fully_paid,
        paid_sum=paid_sum,
        final_payment_on=final_payment_on,
        accepted_on=accepted_on,
        due_date=due_date,
        legal_due_days=legal_due_days,
        days_to_pay=days_to_pay,
        days_open_so_far=days_open_so_far,
        days_overdue=days_overdue,
        status=status,
        outstanding=q2(outstanding),
        interest_total=interest_total,
        on_time=on_time,
        assumptions=tuple(assumptions),
    )


def customer_stats(
    *,
    customer_id: str,
    customer_name: str,
    cases: Sequence[CaseSnapshot],
    payments: Sequence[PaymentRecord],
    as_of: date,
    config: InsightsConfig,
) -> CustomerStatsResult:
    """Descriptive stats for one customer over the supplied cases and payments.

    `cases` may contain other customers; only `customer_id` is used. Payments are
    matched by `case_id`; voided rows are ignored. The caller owns persistence
    and supplies the engine's latest evaluation for each case.
    """
    customer_cases = [case for case in cases if case.customer_id == customer_id]
    case_ids = {case.case_id for case in customer_cases}
    customer_payments = [payment for payment in payments if payment.case_id in case_ids]
    payments_by_case: dict[str, list[PaymentRecord]] = {}
    for payment in customer_payments:
        payments_by_case.setdefault(payment.case_id, []).append(payment)

    facts = [
        _invoice_facts(case, payments_by_case.get(case.case_id, []), as_of)
        for case in customer_cases
    ]
    facts.sort(
        key=lambda fact: (
            fact.accepted_on is None,
            fact.accepted_on or date.min,
            fact.case.invoice_no,
            fact.case.case_id,
        )
    )

    total_billed = q2(sum((fact.case.accepted_amount for fact in facts), Decimal("0.00")))
    outstanding = q2(
        sum(
            (fact.outstanding for fact in facts if not fact.fully_paid),
            Decimal("0.00"),
        )
    )
    overdue_amount = q2(
        sum(
            (fact.outstanding for fact in facts if fact.status == STATUS_OVERDUE),
            Decimal("0.00"),
        )
    )
    interest_values = [
        fact.interest_total for fact in facts if fact.interest_total is not None
    ]
    interest_accrued = q2(sum(interest_values, Decimal("0.00")))

    paid_facts = [fact for fact in facts if fact.fully_paid]
    paid_count = len(paid_facts)
    timed_paid = [fact for fact in paid_facts if fact.days_to_pay is not None]
    timed_days = [fact.days_to_pay for fact in timed_paid if fact.days_to_pay is not None]
    based_on_n = len(timed_days)
    history_sufficient = paid_count >= config.min_history

    avg_days = median_days = worst_days = None
    if history_sufficient and timed_days:
        avg_days = q2(_mean(timed_days))
        median_days = q2(_median(timed_days))
        worst_days = q2(Decimal(max(timed_days)))

    on_time_count = sum(1 for fact in paid_facts if fact.on_time is True)
    on_time_pct = None
    if history_sufficient and paid_count:
        on_time_pct = q2(
            Decimal(on_time_count) / Decimal(paid_count) * ONE_HUNDRED
        )

    assumptions: set[str] = set()
    for fact in facts:
        assumptions.update(fact.assumptions)
    if len(interest_values) < len(facts):
        assumptions.add(ASSUMPTION_INTEREST_EXCLUDES_UNKNOWN)
    if len(timed_paid) < paid_count:
        assumptions.add(ASSUMPTION_AVERAGES_EXCLUDE_UNDATED)
    if any(fact.fully_paid and fact.on_time is None for fact in facts):
        assumptions.add(ASSUMPTION_ON_TIME_EXCLUDES_UNDATED)
    if any(fact.due_date is None and not fact.fully_paid for fact in facts):
        assumptions.add(ASSUMPTION_NO_DUE_DATE)

    tracks = [case.active_track for case in customer_cases if case.active_track is not None]
    active_track = (
        max(
            tracks,
            key=lambda track: (
                track.created_at is not None,
                track.created_at or datetime.min,
            ),
        )
        if tracks
        else None
    )

    series = tuple(
        InvoiceSeriesPoint(
            case_id=fact.case.case_id,
            invoice_no=fact.case.invoice_no,
            accepted_on=fact.accepted_on,
            due_date=fact.due_date,
            legal_due_days=fact.legal_due_days,
            days_to_pay=fact.days_to_pay,
            days_open_so_far=fact.days_open_so_far,
            days_overdue=fact.days_overdue,
            status=fact.status,
            outstanding=fact.outstanding,
            on_time=fact.on_time,
            based_on_n=1,
        )
        for fact in facts
    )

    return CustomerStatsResult(
        customer_id=customer_id,
        customer_name=customer_name or (customer_cases[0].customer_name if customer_cases else ""),
        as_of=as_of,
        invoices_count=len(facts),
        total_billed=total_billed,
        outstanding=outstanding,
        overdue_amount=overdue_amount,
        interest_accrued_now=interest_accrued,
        paid_count=paid_count,
        based_on_n=based_on_n,
        history_sufficient=history_sufficient,
        avg_days_to_pay=avg_days,
        median_days_to_pay=median_days,
        worst_days_to_pay=worst_days,
        on_time_count=on_time_count,
        on_time_pct=on_time_pct,
        history_reason=None if history_sufficient else NOT_ENOUGH_HISTORY,
        series=series,
        last_payment_on=(
            max(
                payment.paid_on
                for payment in customer_payments
                if payment.voided_at is None
            )
            if any(payment.voided_at is None for payment in customer_payments)
            else None
        ),
        active_track=active_track,
        assumptions=tuple(sorted(assumptions)),
        min_history=config.min_history,
    )
