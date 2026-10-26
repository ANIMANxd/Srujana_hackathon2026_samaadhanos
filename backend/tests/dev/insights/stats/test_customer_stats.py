"""Per-customer stats: acceptance-anchored averages, partial payments, series."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from backend.app.config_loader import insights_config, load_config
from backend.insights.stats import (
    ASSUMPTION_INTEREST_EXCLUDES_UNKNOWN,
    ASSUMPTION_NO_DUE_DATE,
    ASSUMPTION_NO_ENGINE_EVALUATION,
    NOT_ENOUGH_HISTORY,
    STATUS_NO_DUE_DATE,
    STATUS_NOT_DUE,
    STATUS_OVERDUE,
    STATUS_PAID,
    CaseSnapshot,
    InsightsConfig,
    PaymentRecord,
    TrackSummary,
    customer_stats,
)
from backend.tests.dev.insights.stats.helpers import (
    AS_OF,
    INVOICE_DATE,
    evaluation,
    make_case,
    make_payment,
    open_case,
    paid_pair,
)


def _stats(cases, payments, *, min_history: int = 3, credit_cap_days: int | None = 45):
    return customer_stats(
        customer_id="cu1",
        customer_name="Acme Industries (synthetic)",
        cases=cases,
        payments=payments,
        as_of=AS_OF,
        config=InsightsConfig(
            min_history=min_history, credit_cap_days=credit_cap_days
        ),
    )


def test_average_days_uses_acceptance_not_invoice_date():
    first, p1 = paid_pair(
        case_id="c1",
        invoice_no="INV-1",
        acceptance="2026-01-10",
        due="2026-02-09",
        paid_on=date(2026, 2, 9),
        invoice_date=date(2025, 12, 1),
    )
    second, p2 = paid_pair(
        case_id="c2",
        invoice_no="INV-2",
        acceptance="2026-01-10",
        due="2026-02-09",
        paid_on=date(2026, 2, 19),
        invoice_date=date(2025, 12, 1),
    )
    third, p3 = paid_pair(
        case_id="c3",
        invoice_no="INV-3",
        acceptance="2026-01-10",
        due="2026-02-19",
        paid_on=date(2026, 3, 1),
        invoice_date=date(2025, 12, 1),
    )

    result = _stats([first, second, third], [p1, p2, p3], min_history=3)

    # 30, 40 and 50 days from acceptance; from the invoice date they would be
    # 70, 80 and 90, so this pins the anchor.
    assert result.avg_days_to_pay == Decimal("40.00")
    assert result.median_days_to_pay == Decimal("40.00")
    assert result.worst_days_to_pay == Decimal("50.00")
    assert result.paid_count == 3
    assert result.based_on_n == 3
    assert result.history_sufficient is True
    assert result.history_reason is None
    assert result.on_time_count == 1
    assert result.on_time_pct == Decimal("33.33")
    assert result.total_billed == Decimal("3000.00")
    assert result.interest_accrued_now == Decimal("300.00")
    assert result.outstanding == Decimal("0.00")

    points = {point.invoice_no: point for point in result.series}
    assert points["INV-1"].days_to_pay == 30
    assert points["INV-2"].days_to_pay == 40
    assert points["INV-3"].days_to_pay == 50
    assert points["INV-1"].legal_due_days == 30
    assert points["INV-3"].legal_due_days == 40
    assert points["INV-1"].on_time is True
    assert points["INV-2"].on_time is False


def test_two_paid_invoices_is_not_enough_history():
    first, p1 = paid_pair(case_id="c1", invoice_no="INV-1")
    second, p2 = paid_pair(case_id="c2", invoice_no="INV-2")

    result = _stats([first, second], [p1, p2], min_history=3)

    assert result.paid_count == 2
    assert result.based_on_n == 2
    assert result.history_sufficient is False
    assert result.avg_days_to_pay is None
    assert result.median_days_to_pay is None
    assert result.worst_days_to_pay is None
    assert result.on_time_pct is None
    assert result.history_reason == NOT_ENOUGH_HISTORY
    # The count itself is still useful; only the derived average is withheld.
    assert result.on_time_count == 2


def test_partial_payment_stays_open_with_a_fallback_and_an_assumption():
    case = make_case(
        case_id="c1",
        invoice_no="INV-1",
        accepted="1000.00",
        evaluation_data={
            "timeline": {
                "acceptance_date": "2026-01-10",
                "due_date": "2026-02-09",
                "days_overdue": 259,
            }
        },
    )
    payment = make_payment(
        payment_id="p1", case_id="c1", amount="400.00", paid_on=date(2026, 2, 1)
    )

    result = _stats([case], [payment], min_history=1)

    assert result.paid_count == 0
    assert result.outstanding == Decimal("600.00")
    assert result.overdue_amount == Decimal("600.00")
    assert result.based_on_n == 0
    point = result.series[0]
    assert point.status == STATUS_OVERDUE
    assert point.days_to_pay is None
    assert point.days_open_so_far == (AS_OF - date(2026, 1, 10)).days
    assert any("no appropriation" in assumption for assumption in result.assumptions)
    assert ASSUMPTION_INTEREST_EXCLUDES_UNKNOWN in result.assumptions


def test_partial_payment_uses_the_engine_total_claim_when_present():
    case = make_case(
        case_id="c1",
        invoice_no="INV-1",
        accepted="1000.00",
        evaluation_data=evaluation(
            total_claim="900.00", ledger_payments=("400.00",)
        ),
    )
    payment = make_payment(
        payment_id="p1", case_id="c1", amount="400.00", paid_on=date(2026, 2, 1)
    )

    result = _stats([case], [payment], min_history=1)

    assert result.paid_count == 0
    assert result.outstanding == Decimal("900.00")
    assert not any("no appropriation" in assumption for assumption in result.assumptions)
    assert not any(
        "payment rows do not match" in assumption for assumption in result.assumptions
    )


def test_interest_accrued_sums_engine_figures_and_outstanding_uses_engine_claim():
    unpaid = open_case(
        case_id="c1",
        invoice_no="INV-OPEN",
        total_claim="1100.00",
        interest="50.00",
    )
    paid, payment = paid_pair(case_id="c2", invoice_no="INV-PAID", interest="100.00")

    result = _stats([unpaid, paid], [payment], min_history=3)

    assert result.interest_accrued_now == Decimal("150.00")
    assert result.outstanding == Decimal("1100.00")
    assert result.paid_count == 1
    assert result.total_billed == Decimal("2000.00")


def test_voided_payment_is_ignored():
    case = make_case(case_id="c1", invoice_no="INV-1", evaluation_data=None)
    active = make_payment(
        payment_id="active",
        case_id="c1",
        amount="400.00",
        paid_on=date(2026, 2, 1),
    )
    voided = make_payment(
        payment_id="voided",
        case_id="c1",
        amount="600.00",
        paid_on=date(2026, 9, 1),
        voided_at=datetime(2026, 9, 2, tzinfo=UTC),
    )

    result = _stats([case], [active, voided], min_history=1)

    assert result.paid_count == 0
    assert result.outstanding == Decimal("600.00")
    assert result.last_payment_on == date(2026, 2, 1)
    assert ASSUMPTION_NO_ENGINE_EVALUATION.format(invoice="INV-1") in result.assumptions


def test_series_statuses_and_days_open_or_to_pay():
    paid, payment = paid_pair(
        case_id="c1", invoice_no="INV-PAID", acceptance="2026-01-10", due="2026-02-09"
    )
    overdue = open_case(
        case_id="c2", invoice_no="INV-OVERDUE", acceptance="2026-01-10", due="2026-09-30"
    )
    not_due = open_case(
        case_id="c3", invoice_no="INV-NOT-DUE", acceptance="2026-10-01", due="2026-12-31"
    )
    no_due = open_case(
        case_id="c4", invoice_no="INV-NO-DUE", acceptance="2026-01-10", due=None
    )

    result = _stats([paid, overdue, not_due, no_due], [payment], min_history=3)
    points = {point.invoice_no: point for point in result.series}

    assert points["INV-PAID"].status == STATUS_PAID
    assert points["INV-PAID"].days_to_pay == 30
    assert points["INV-PAID"].days_open_so_far is None
    assert points["INV-PAID"].on_time is True

    assert points["INV-OVERDUE"].status == STATUS_OVERDUE
    assert points["INV-OVERDUE"].days_overdue == (AS_OF - date(2026, 9, 30)).days
    assert points["INV-OVERDUE"].days_open_so_far == (AS_OF - date(2026, 1, 10)).days

    assert points["INV-NOT-DUE"].status == STATUS_NOT_DUE
    assert points["INV-NOT-DUE"].days_overdue == 0
    assert points["INV-NOT-DUE"].days_open_so_far == (AS_OF - date(2026, 10, 1)).days

    assert points["INV-NO-DUE"].status == STATUS_NO_DUE_DATE
    assert points["INV-NO-DUE"].legal_due_days is None
    assert points["INV-NO-DUE"].days_overdue is None
    assert points["INV-NO-DUE"].days_open_so_far == (AS_OF - date(2026, 1, 10)).days
    assert ASSUMPTION_NO_DUE_DATE in result.assumptions


def test_float_money_is_refused_everywhere():
    with pytest.raises(TypeError, match="never float"):
        CaseSnapshot(
            case_id="c1",
            customer_id="cu1",
            customer_name="Acme",
            invoice_no="INV-1",
            invoice_date=INVOICE_DATE,
            accepted_amount=1000.0,  # type: ignore[arg-type]
        )
    with pytest.raises(TypeError, match="never float"):
        PaymentRecord(
            payment_id="p1",
            case_id="c1",
            amount=400.0,  # type: ignore[arg-type]
            paid_on=date(2026, 2, 1),
        )
    with pytest.raises(TypeError, match="concentration_flag_pct"):
        InsightsConfig(concentration_flag_pct=40.0)  # type: ignore[arg-type]

    case = make_case(
        case_id="c1",
        invoice_no="INV-1",
        evaluation_data={
            "timeline": {"acceptance_date": "2026-01-10", "due_date": "2026-02-09"},
            "financials": {"interest_total": 100.0, "total_claim": "1100.00"},
        },
    )
    with pytest.raises(TypeError, match="never float"):
        _stats([case], [], min_history=1)


def test_config_helper_reads_product_settings():
    raw = load_config()
    config = insights_config(raw)

    assert config.min_history == 3
    assert config.concentration_flag_pct == Decimal("40")
    assert config.credit_cap_days == 45
    assert config.cash_in_estimate_enabled is False
    assert raw["insights"]["verified"] is False
    assert raw["insights"]["source_ref"] == "product setting, not law"


def test_active_track_summary_uses_the_most_recent_track():
    first = open_case(
        case_id="c1",
        invoice_no="INV-1",
        track=TrackSummary(
            kind="RECOVERY",
            state="STAGE_1_PREPARED",
            created_at=datetime(2026, 10, 1, tzinfo=UTC),
        ),
    )
    second = open_case(
        case_id="c2",
        invoice_no="INV-2",
        track=TrackSummary(
            kind="FINANCING",
            state="BIDS_AVAILABLE",
            created_at=datetime(2026, 10, 2, tzinfo=UTC),
        ),
    )

    result = _stats([first, second], [], min_history=1)

    assert result.active_track is not None
    assert result.active_track.kind == "FINANCING"
    assert result.active_track.state == "BIDS_AVAILABLE"
