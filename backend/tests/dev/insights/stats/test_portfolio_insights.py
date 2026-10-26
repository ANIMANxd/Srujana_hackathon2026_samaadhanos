"""Portfolio insights: concentration, 43B(h), terms flags and cash-in."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import date, timedelta
from decimal import Decimal

from backend.insights.insights import (
    BEFORE_MARCH_NOTE,
    CASH_IN_DISABLED,
    CASH_IN_LABEL,
    CASH_IN_NO_HISTORY,
    CONCENTRATION_BELOW_THRESHOLD,
    BeforeMarchItem,
    CashInWeek,
    ConcentrationResult,
    ConcentrationShare,
    PortfolioInsightsResult,
    TermsFlag,
    portfolio_insights,
)
from backend.insights.stats import (
    NOT_ENOUGH_HISTORY,
    CustomerStatsResult,
    InsightsConfig,
    InvoiceSeriesPoint,
)
from backend.tests.dev.insights.stats.helpers import (
    AS_OF,
    open_case,
    paid_pair,
)


def _config(**overrides) -> InsightsConfig:
    values = {
        "min_history": 3,
        "concentration_flag_pct": Decimal("40"),
        "credit_cap_days": 45,
        "cash_in_estimate_enabled": False,
    }
    values.update(overrides)
    return InsightsConfig(**values)


def _open_customer(customer_id: str, amount: str, *, due: str = "2026-12-31"):
    return open_case(
        case_id=f"c-{customer_id}",
        invoice_no=f"INV-{customer_id}",
        customer_id=customer_id,
        customer_name=f"Customer {customer_id}",
        acceptance="2026-01-10",
        due=due,
        accepted=amount,
        total_claim=amount,
    )


def test_concentration_flag_at_the_threshold():
    cases = [
        _open_customer("a", "400.00"),
        _open_customer("b", "300.00"),
        _open_customer("c", "300.00"),
    ]

    result = portfolio_insights(
        cases=cases, payments=[], as_of=AS_OF, config=_config()
    )

    assert result.customer_count == 3
    assert result.concentration.total_outstanding == Decimal("1000.00")
    assert result.concentration.top_customer_id == "a"
    assert result.concentration.top_share_pct == Decimal("40.00")
    assert result.concentration.flagged is True
    assert result.concentration.reason.startswith("TOP_CUSTOMER")
    assert result.concentration.shares[0].flagged is True
    assert all(not share.flagged for share in result.concentration.shares[1:])
    assert result.concentration.based_on_n == 3
    assert all(share.based_on_n == 1 for share in result.concentration.shares)


def test_concentration_just_below_the_threshold_is_not_flagged():
    cases = [
        _open_customer("a", "390.00"),
        _open_customer("b", "305.00"),
        _open_customer("c", "305.00"),
    ]

    result = portfolio_insights(
        cases=cases, payments=[], as_of=AS_OF, config=_config()
    )

    assert result.concentration.top_customer_id == "a"
    assert result.concentration.top_share_pct == Decimal("39.00")
    assert result.concentration.flagged is False
    assert result.concentration.reason == CONCENTRATION_BELOW_THRESHOLD


def test_before_march_lists_only_overdue_open_invoices():
    paid, payment = paid_pair(
        case_id="c-paid",
        invoice_no="INV-PAID",
        acceptance="2026-01-10",
        due="2026-09-30",
        paid_on=date(2026, 10, 15),
    )
    overdue = open_case(
        case_id="c-overdue",
        invoice_no="INV-OVERDUE",
        acceptance="2026-01-10",
        due="2026-09-30",
    )
    not_due = open_case(
        case_id="c-not-due",
        invoice_no="INV-NOT-DUE",
        acceptance="2026-10-01",
        due="2026-12-31",
    )

    result = portfolio_insights(
        cases=[paid, overdue, not_due],
        payments=[payment],
        as_of=AS_OF,
        config=_config(),
    )

    assert len(result.before_march) == 1
    item = result.before_march[0]
    assert item.invoice_no == "INV-OVERDUE"
    assert item.outstanding == Decimal("1000.00")
    assert item.next_march == date(2027, 3, 31)
    assert item.note == BEFORE_MARCH_NOTE
    assert item.based_on_n == 1

    later = portfolio_insights(
        cases=[paid, overdue, not_due],
        payments=[payment],
        as_of=date(2027, 4, 1),
        config=_config(),
    )
    assert later.before_march[0].next_march == date(2028, 3, 31)


def test_terms_flags_use_the_configured_credit_cap():
    slow = []
    for index in range(3):
        slow.append(
            paid_pair(
                case_id=f"slow-{index}",
                invoice_no=f"SLOW-{index}",
                customer_id="slow",
                customer_name="Slow Co",
                due="2026-02-19",
                paid_on=date(2026, 3, 1),
            )
        )
    fast = []
    for index in range(3):
        fast.append(
            paid_pair(
                case_id=f"fast-{index}",
                invoice_no=f"FAST-{index}",
                customer_id="fast",
                customer_name="Fast Co",
                due="2026-02-09",
                paid_on=date(2026, 2, 9),
            )
        )
    thin = []
    for index in range(2):
        thin.append(
            paid_pair(
                case_id=f"thin-{index}",
                invoice_no=f"THIN-{index}",
                customer_id="thin",
                customer_name="Thin Co",
                due="2026-02-09",
                paid_on=date(2026, 3, 21),
            )
        )

    cases = [pair[0] for pair in slow + fast + thin]
    payments = [pair[1] for pair in slow + fast + thin]
    result = portfolio_insights(
        cases=cases, payments=payments, as_of=AS_OF, config=_config()
    )

    assert len(result.terms_flags) == 1
    flag = result.terms_flags[0]
    assert flag.customer_id == "slow"
    assert flag.avg_days_to_pay == Decimal("50.00")
    assert flag.credit_cap_days == 45
    assert flag.text == "This customer averages 50 days; the law caps credit at 45 days."
    assert flag.based_on_n == 3

    no_cap = portfolio_insights(
        cases=cases,
        payments=payments,
        as_of=AS_OF,
        config=_config(credit_cap_days=None),
    )
    assert no_cap.terms_flags == ()
    assert "CREDIT_CAP_NOT_CONFIGURED" in no_cap.assumptions


def test_cash_in_estimate_is_behind_the_flag_and_needs_history():
    steady = []
    for index in range(3):
        steady.append(
            paid_pair(
                case_id=f"steady-{index}",
                invoice_no=f"STEADY-{index}",
                customer_id="steady",
                customer_name="Steady Co",
                due="2026-02-09",
                paid_on=date(2026, 2, 9),
            )
        )
    steady_open = open_case(
        case_id="steady-open",
        invoice_no="STEADY-OPEN",
        customer_id="steady",
        customer_name="Steady Co",
        acceptance="2026-01-10",
        due="2026-02-09",
        accepted="500.00",
        total_claim="500.00",
    )
    thin = []
    for index in range(2):
        thin.append(
            paid_pair(
                case_id=f"thin-{index}",
                invoice_no=f"THIN-{index}",
                customer_id="thin",
                customer_name="Thin Co",
                due="2026-02-09",
                paid_on=date(2026, 3, 21),
            )
        )
    thin_open = open_case(
        case_id="thin-open",
        invoice_no="THIN-OPEN",
        customer_id="thin",
        customer_name="Thin Co",
        acceptance="2026-01-10",
        due="2026-02-09",
        accepted="300.00",
        total_claim="300.00",
    )

    cases = [pair[0] for pair in steady + thin] + [steady_open, thin_open]
    payments = [pair[1] for pair in steady + thin]

    disabled = portfolio_insights(
        cases=cases,
        payments=payments,
        as_of=AS_OF,
        config=_config(cash_in_estimate_enabled=False),
    )
    assert disabled.cash_in_estimate is None
    assert disabled.cash_in_reason == CASH_IN_DISABLED

    enabled = portfolio_insights(
        cases=cases,
        payments=payments,
        as_of=AS_OF,
        config=_config(cash_in_estimate_enabled=True),
    )
    assert enabled.cash_in_estimate is not None
    assert len(enabled.cash_in_estimate) == 1
    week = enabled.cash_in_estimate[0]
    expected_day = date(2026, 1, 10) + timedelta(days=30)
    iso = expected_day.isocalendar()
    assert week.iso_week == f"{iso.year}-W{iso.week:02d}"
    assert week.week_start == expected_day - timedelta(days=expected_day.weekday())
    assert week.amount == Decimal("500.00")
    assert week.invoice_count == 1
    assert week.based_on_n == 1
    assert week.label == CASH_IN_LABEL
    assert enabled.cash_in_reason is None
    assert "CASH_IN_EXCLUDES_CUSTOMERS_WITHOUT_ENOUGH_HISTORY" in enabled.assumptions

    no_history = portfolio_insights(
        cases=[pair[0] for pair in thin] + [thin_open],
        payments=[pair[1] for pair in thin],
        as_of=AS_OF,
        config=_config(cash_in_estimate_enabled=True),
    )
    assert no_history.cash_in_estimate == ()
    assert no_history.cash_in_reason == CASH_IN_NO_HISTORY


def test_every_output_carries_based_on_n():
    output_types = (
        CustomerStatsResult,
        InvoiceSeriesPoint,
        PortfolioInsightsResult,
        ConcentrationResult,
        ConcentrationShare,
        BeforeMarchItem,
        TermsFlag,
        CashInWeek,
    )
    for output_type in output_types:
        assert is_dataclass(output_type)
        names = {field.name for field in fields(output_type)}
        assert "based_on_n" in names, f"{output_type.__name__} has no based_on_n"


def test_outputs_use_no_score_rating_or_risk_labels():
    forbidden = ("score", "rating", "risk", "rank", "defaulter", "blacklist", "predict")
    output_types = (
        CustomerStatsResult,
        InvoiceSeriesPoint,
        PortfolioInsightsResult,
        ConcentrationResult,
        ConcentrationShare,
        BeforeMarchItem,
        TermsFlag,
        CashInWeek,
    )
    for output_type in output_types:
        for field in fields(output_type):
            lowered = field.name.lower()
            assert not any(word in lowered for word in forbidden), (
                f"{output_type.__name__}.{field.name} uses a forbidden buyer label"
            )


def test_a_portfolio_with_no_cases_is_empty_and_explicit():
    result = portfolio_insights(
        cases=[], payments=[], as_of=AS_OF, config=_config()
    )
    assert result.customer_count == 0
    assert result.invoices_count == 0
    assert result.based_on_n == 0
    assert result.history_sufficient is False
    assert result.history_reason == NOT_ENOUGH_HISTORY
    assert result.concentration.reason == "NO_OUTSTANDING"
    assert result.before_march == ()
