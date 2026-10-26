"""Pure portfolio insights for the v5 Customer book.

`portfolio_insights` aggregates the per-customer statistics from
`backend.insights.stats` and adds four descriptive views:

- concentration: each customer's share of total outstanding, with a product
  threshold flag (not a risk score);
- before_march: open overdue invoices and their next 31 March, using the exact
  43B(h) wording the buyer-cost artifacts already use;
- terms_flags: customers whose observed average days-to-pay exceeds the
  engine's credit cap, with a config-sourced number in the sentence;
- cash-in estimate: a forecast behind a config flag, labelled and limited to
  customers with enough history.

No I/O, no clock, no network. Money and percentages are Decimal. Nothing here
scores, ranks or labels a buyer, and the only prediction is the labelled cash-in
estimate.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from backend.insights.stats import (
    ASSUMPTION_AVERAGES_EXCLUDE_UNDATED,
    NOT_ENOUGH_HISTORY,
    ONE_HUNDRED,
    STATUS_OVERDUE,
    STATUS_PAID,
    CustomerStatsResult,
    CaseSnapshot,
    InsightsConfig,
    PaymentRecord,
    _format_days,
    _mean,
    _median,
    customer_stats,
    q2,
)

BEFORE_MARCH_NOTE = "43B(h): their deduction for this amount depends on payment"
CASH_IN_LABEL = "estimate based on past payment timing"

CASH_IN_DISABLED = "DISABLED"
CASH_IN_NO_HISTORY = "NO_CUSTOMER_WITH_ENOUGH_HISTORY"
CASH_IN_NO_OPEN = "NO_ELIGIBLE_OPEN_INVOICES"

CONCENTRATION_NO_OUTSTANDING = "NO_OUTSTANDING"
CONCENTRATION_BELOW_THRESHOLD = "BELOW_THRESHOLD"
CONCENTRATION_TOP_AT_OR_ABOVE = "TOP_CUSTOMER_AT_OR_ABOVE_THRESHOLD"


@dataclass(frozen=True)
class ConcentrationShare:
    """One customer's share of the portfolio's outstanding.

    `flagged` is true only for the top customer when its share is at or above
    the product threshold. It is a concentration fact from the owner's book, not
    a risk rating.
    """

    customer_id: str
    customer_name: str
    outstanding: Decimal
    share_pct: Decimal
    flagged: bool
    based_on_n: int


@dataclass(frozen=True)
class ConcentrationResult:
    total_outstanding: Decimal
    threshold_pct: Decimal
    shares: tuple[ConcentrationShare, ...]
    top_customer_id: str | None
    top_share_pct: Decimal | None
    flagged: bool
    based_on_n: int
    reason: str


@dataclass(frozen=True)
class BeforeMarchItem:
    """An open overdue invoice and the next 31 March the buyer's tax timing meets."""

    customer_id: str
    customer_name: str
    case_id: str
    invoice_no: str
    outstanding: Decimal
    next_march: date
    note: str
    based_on_n: int


@dataclass(frozen=True)
class TermsFlag:
    """A customer whose observed payment timing exceeds the engine's credit cap.

    The sentence uses the cap from config; no new legal claim is introduced.
    """

    customer_id: str
    customer_name: str
    avg_days_to_pay: Decimal
    credit_cap_days: int
    text: str
    based_on_n: int


@dataclass(frozen=True)
class CashInWeek:
    """One ISO week of the labelled cash-in estimate (a forecast, not a promise)."""

    iso_week: str
    week_start: date
    amount: Decimal
    invoice_count: int
    based_on_n: int
    label: str


@dataclass(frozen=True)
class PortfolioInsightsResult:
    """Descriptive portfolio totals plus the four portfolio views."""

    as_of: date
    customer_count: int
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
    last_payment_on: date | None
    min_history: int
    concentration: ConcentrationResult
    before_march: tuple[BeforeMarchItem, ...]
    terms_flags: tuple[TermsFlag, ...]
    cash_in_estimate: tuple[CashInWeek, ...] | None
    cash_in_reason: str | None
    assumptions: tuple[str, ...]
    customers: tuple[CustomerStatsResult, ...]


def _next_march_31(as_of: date) -> date:
    """The next 31 March on or after `as_of` (a calendar date, not a rule)."""
    if (as_of.month, as_of.day) <= (3, 31):
        return date(as_of.year, 3, 31)
    return date(as_of.year + 1, 3, 31)


def _concentration(
    customers: Sequence[CustomerStatsResult], config: InsightsConfig
) -> ConcentrationResult:
    total = q2(sum((customer.outstanding for customer in customers), Decimal("0.00")))
    shares: list[ConcentrationShare] = []
    for customer in customers:
        share = (
            q2(customer.outstanding / total * ONE_HUNDRED)
            if total > 0
            else Decimal("0.00")
        )
        open_invoices = sum(
            1 for point in customer.series if point.outstanding > 0
        )
        shares.append(
            ConcentrationShare(
                customer_id=customer.customer_id,
                customer_name=customer.customer_name,
                outstanding=customer.outstanding,
                share_pct=share,
                flagged=False,
                based_on_n=open_invoices,
            )
        )

    shares.sort(key=lambda share: (-share.outstanding, share.customer_id))
    top = shares[0] if shares else None
    flagged = (
        top is not None
        and total > 0
        and top.share_pct >= config.concentration_flag_pct
    )
    top_id = top.customer_id if top is not None and total > 0 else None
    top_share = top.share_pct if top is not None and total > 0 else None
    final_shares = tuple(
        replace(share, flagged=bool(flagged and share.customer_id == top_id))
        for share in shares
    )
    if total == 0:
        reason = CONCENTRATION_NO_OUTSTANDING
    elif flagged:
        reason = CONCENTRATION_TOP_AT_OR_ABOVE
    else:
        reason = CONCENTRATION_BELOW_THRESHOLD

    return ConcentrationResult(
        total_outstanding=total,
        threshold_pct=config.concentration_flag_pct,
        shares=final_shares,
        top_customer_id=top_id,
        top_share_pct=top_share,
        flagged=flagged,
        based_on_n=sum(1 for customer in customers if customer.outstanding > 0),
        reason=reason,
    )


def _before_march(
    customers: Sequence[CustomerStatsResult], as_of: date
) -> tuple[BeforeMarchItem, ...]:
    next_march = _next_march_31(as_of)
    items: list[BeforeMarchItem] = []
    for customer in customers:
        for point in customer.series:
            if point.status != STATUS_OVERDUE or point.outstanding <= 0:
                continue
            items.append(
                BeforeMarchItem(
                    customer_id=customer.customer_id,
                    customer_name=customer.customer_name,
                    case_id=point.case_id,
                    invoice_no=point.invoice_no,
                    outstanding=point.outstanding,
                    next_march=next_march,
                    note=BEFORE_MARCH_NOTE,
                    based_on_n=1,
                )
            )
    items.sort(key=lambda item: (item.next_march, item.customer_name, item.invoice_no))
    return tuple(items)


def _terms_flags(
    customers: Sequence[CustomerStatsResult],
    config: InsightsConfig,
    assumptions: set[str],
) -> tuple[TermsFlag, ...]:
    if config.credit_cap_days is None:
        assumptions.add("CREDIT_CAP_NOT_CONFIGURED")
        return ()
    cap = config.credit_cap_days
    flags: list[TermsFlag] = []
    for customer in customers:
        if not customer.history_sufficient or customer.avg_days_to_pay is None:
            continue
        if customer.avg_days_to_pay <= Decimal(cap):
            continue
        flags.append(
            TermsFlag(
                customer_id=customer.customer_id,
                customer_name=customer.customer_name,
                avg_days_to_pay=customer.avg_days_to_pay,
                credit_cap_days=cap,
                text=(
                    f"This customer averages {_format_days(customer.avg_days_to_pay)} "
                    f"days; the law caps credit at {cap} days."
                ),
                based_on_n=customer.based_on_n,
            )
        )
    flags.sort(key=lambda flag: (-flag.avg_days_to_pay, flag.customer_id))
    return tuple(flags)


def _cash_in(
    customers: Sequence[CustomerStatsResult],
    config: InsightsConfig,
    assumptions: set[str],
) -> tuple[tuple[CashInWeek, ...] | None, str | None]:
    if not config.cash_in_estimate_enabled:
        return None, CASH_IN_DISABLED

    eligible = [
        customer
        for customer in customers
        if customer.history_sufficient and customer.avg_days_to_pay is not None
    ]
    if not eligible:
        return (), CASH_IN_NO_HISTORY

    buckets: dict[str, tuple[date, Decimal, int]] = {}
    excluded_without_acceptance = 0
    for customer in eligible:
        assert customer.avg_days_to_pay is not None
        offset = int(
            customer.avg_days_to_pay.to_integral_value(rounding=ROUND_HALF_UP)
        )
        for point in customer.series:
            if point.status == STATUS_PAID or point.outstanding <= 0:
                continue
            if point.accepted_on is None:
                excluded_without_acceptance += 1
                continue
            expected = point.accepted_on + timedelta(days=offset)
            iso = expected.isocalendar()
            label = f"{iso.year}-W{iso.week:02d}"
            week_start = expected - timedelta(days=expected.weekday())
            previous = buckets.get(label)
            if previous is None:
                buckets[label] = (week_start, point.outstanding, 1)
            else:
                buckets[label] = (
                    previous[0],
                    q2(previous[1] + point.outstanding),
                    previous[2] + 1,
                )

    assumptions.add("CASH_IN_ESTIMATE_ROUNDS_AVG_DAYS_TO_WHOLE_DAYS")
    if excluded_without_acceptance:
        assumptions.add("CASH_IN_EXCLUDES_INVOICES_WITHOUT_ACCEPTANCE_DATE")
    if len(eligible) < len(customers):
        assumptions.add("CASH_IN_EXCLUDES_CUSTOMERS_WITHOUT_ENOUGH_HISTORY")

    if not buckets:
        return (), CASH_IN_NO_OPEN

    weeks = tuple(
        CashInWeek(
            iso_week=label,
            week_start=buckets[label][0],
            amount=buckets[label][1],
            invoice_count=buckets[label][2],
            based_on_n=buckets[label][2],
            label=CASH_IN_LABEL,
        )
        for label in sorted(buckets, key=lambda key: buckets[key][0])
    )
    return weeks, None


def portfolio_insights(
    *,
    cases: Sequence[CaseSnapshot],
    payments: Sequence[PaymentRecord],
    as_of: date,
    config: InsightsConfig,
) -> PortfolioInsightsResult:
    """Descriptive portfolio totals plus concentration, 43B(h), terms and cash-in.

    Cases are grouped by `customer_id`; each customer is computed with
    `stats.customer_stats`, so the portfolio and the customer page cannot
    disagree. The cash-in forecast is returned only when
    `config.cash_in_estimate_enabled` is true, and only for customers with
    sufficient history.
    """
    grouped: dict[str, list[CaseSnapshot]] = {}
    for case in cases:
        grouped.setdefault(case.customer_id, []).append(case)

    customer_results: list[CustomerStatsResult] = []
    for customer_id in sorted(grouped):
        customer_cases = grouped[customer_id]
        customer_results.append(
            customer_stats(
                customer_id=customer_id,
                customer_name=customer_cases[0].customer_name,
                cases=customer_cases,
                payments=payments,
                as_of=as_of,
                config=config,
            )
        )

    customers = tuple(customer_results)
    paid_count = sum(customer.paid_count for customer in customers)
    timed_days = [
        point.days_to_pay
        for customer in customers
        for point in customer.series
        if point.status == STATUS_PAID and point.days_to_pay is not None
    ]
    based_on_n = len(timed_days)
    history_sufficient = paid_count >= config.min_history

    avg_days = median_days = worst_days = None
    if history_sufficient and timed_days:
        avg_days = q2(_mean(timed_days))
        median_days = q2(_median(timed_days))
        worst_days = q2(Decimal(max(timed_days)))

    on_time_count = sum(customer.on_time_count for customer in customers)
    on_time_pct = None
    if history_sufficient and paid_count:
        on_time_pct = q2(
            Decimal(on_time_count) / Decimal(paid_count) * ONE_HUNDRED
        )

    assumptions: set[str] = set()
    for customer in customers:
        assumptions.update(customer.assumptions)
    if len(timed_days) < paid_count:
        assumptions.add(ASSUMPTION_AVERAGES_EXCLUDE_UNDATED)

    concentration = _concentration(customers, config)
    before_march = _before_march(customers, as_of)
    terms_flags = _terms_flags(customers, config, assumptions)
    cash_in, cash_in_reason = _cash_in(customers, config, assumptions)

    last_payments = [
        customer.last_payment_on
        for customer in customers
        if customer.last_payment_on is not None
    ]

    return PortfolioInsightsResult(
        as_of=as_of,
        customer_count=len(customers),
        invoices_count=sum(customer.invoices_count for customer in customers),
        total_billed=q2(
            sum((customer.total_billed for customer in customers), Decimal("0.00"))
        ),
        outstanding=q2(
            sum((customer.outstanding for customer in customers), Decimal("0.00"))
        ),
        overdue_amount=q2(
            sum((customer.overdue_amount for customer in customers), Decimal("0.00"))
        ),
        interest_accrued_now=q2(
            sum(
                (customer.interest_accrued_now for customer in customers),
                Decimal("0.00"),
            )
        ),
        paid_count=paid_count,
        based_on_n=based_on_n,
        history_sufficient=history_sufficient,
        avg_days_to_pay=avg_days,
        median_days_to_pay=median_days,
        worst_days_to_pay=worst_days,
        on_time_count=on_time_count,
        on_time_pct=on_time_pct,
        history_reason=None if history_sufficient else NOT_ENOUGH_HISTORY,
        last_payment_on=max(last_payments) if last_payments else None,
        min_history=config.min_history,
        concentration=concentration,
        before_march=before_march,
        terms_flags=terms_flags,
        cash_in_estimate=cash_in,
        cash_in_reason=cash_in_reason,
        assumptions=tuple(sorted(assumptions)),
        customers=customers,
    )
