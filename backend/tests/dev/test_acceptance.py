"""Dev tests for backend/engine/acceptance.py (the engine author's smoke tests).

Covers: delivery anchoring (not invoice), the objection-window boundary, an
unresolved objection leaving dates null, no agreement, Net 90 clamping, Net 30
not clamping, and leap-year dates. Every expectation is hand-computed in a
comment.

These are NOT the spec tests in tests/spec/; those come from the independent test
author and must pass without this module.
"""

from dataclasses import dataclass
from datetime import date

import pytest

from backend.engine.acceptance import (
    STATUS_DEEMED_ACCEPTANCE,
    STATUS_NO_DELIVERY_PROOF,
    STATUS_PENDING_RESOLUTION,
    STATUS_RESOLVED,
    WARNING_PENDING_RESOLUTION,
    evaluate_acceptance,
)
from backend.engine.config import ConfigError
from backend.tests.dev.test_gate import make_config


@dataclass
class Obj:
    """Minimal objection satisfying ObjectionLike."""

    raised_date: date
    is_written: bool = True
    description: str | None = None
    resolved_date: date | None = None


def run_acceptance(cfg=None, **kwargs):
    """Delivery 2026-01-12, Net 90, no objections, unless overridden."""
    cfg = cfg or make_config()
    facts = {
        "invoice_date": date(2026, 1, 5),
        "delivery_date": date(2026, 1, 12),
        "calculation_date": date(2026, 4, 15),
        "objections": (),
        "written_credit_days": 90,
    }
    facts.update(kwargs)
    return evaluate_acceptance(cfg, **facts)


# ------------------------------------------------------- delivery anchoring ----


def test_delivery_after_invoice_anchors_on_delivery():
    """Section 7: delivery, not invoice, anchors acceptance.

    Net 90 clamps to 45 days, so due = delivery + 45 = 2026-02-26 and the
    appointed day is 2026-02-27.
    """
    result = run_acceptance(
        invoice_date=date(2026, 1, 5), delivery_date=date(2026, 1, 12)
    )
    assert result.acceptance_date == date(2026, 1, 12)
    assert result.due_date == date(2026, 2, 26)
    assert result.appointed_day == date(2026, 2, 27)


def test_invoice_date_never_moves_the_clock():
    """Changing only the invoice date must leave every date identical."""
    early = run_acceptance(invoice_date=date(2025, 1, 1), delivery_date=date(2026, 1, 12))
    late = run_acceptance(invoice_date=date(2026, 3, 1), delivery_date=date(2026, 1, 12))
    assert early.acceptance_date == late.acceptance_date
    assert early.due_date == late.due_date
    assert early.appointed_day == late.appointed_day


def test_no_delivery_proof_leaves_every_date_empty():
    """First line of 6.2: no delivery date means no acceptance and no due date."""
    result = run_acceptance(delivery_date=None)
    assert result.status == STATUS_NO_DELIVERY_PROOF
    assert result.delivery_date is None
    assert result.objection_window_end is None
    assert result.acceptance_date is None
    assert result.due_date is None
    assert result.appointed_day is None
    assert result.days_overdue is None


def test_no_delivery_proof_still_reports_the_agreed_period():
    """The term length is known even when the anchor is not."""
    result = run_acceptance(delivery_date=None)
    assert result.agreed_days == 90
    assert result.applied_days == 45
    assert result.clamped is True


def test_no_delivery_proof_warns_that_objections_could_not_be_classified():
    result = run_acceptance(
        delivery_date=None,
        objections=[Obj(raised_date=date(2026, 1, 20))],
    )
    assert any(w.code == "UNCLASSIFIED_OBJECTIONS" for w in result.warnings)


# ------------------------------------------------------ objection window ----


def test_objection_on_the_last_window_day_qualifies():
    """Delivery 2026-01-01 + 15 days closes the window on 2026-01-16, inclusive."""
    result = run_acceptance(
        delivery_date=date(2026, 1, 1),
        objections=[Obj(raised_date=date(2026, 1, 16), resolved_date=date(2026, 2, 1))],
    )
    assert result.objection_window_end == date(2026, 1, 16)
    assert result.status == STATUS_RESOLVED
    # Acceptance moves to the resolution date, not the delivery date.
    assert result.acceptance_date == date(2026, 2, 1)
    assert result.late_complaints == []


def test_objection_the_day_after_the_window_is_recorded_and_ignored():
    """One day later falls outside, so the clock stays on the delivery date."""
    result = run_acceptance(
        delivery_date=date(2026, 1, 1),
        objections=[Obj(raised_date=date(2026, 1, 17), resolved_date=date(2026, 2, 1))],
    )
    assert result.objection_window_end == date(2026, 1, 16)
    assert result.status == STATUS_DEEMED_ACCEPTANCE
    assert result.acceptance_date == date(2026, 1, 1)
    assert len(result.late_complaints) == 1
    assert result.late_complaints[0].date == date(2026, 1, 17)
    assert "after the window" in result.late_complaints[0].reason


def test_unwritten_objection_inside_the_window_does_not_move_the_clock():
    result = run_acceptance(
        delivery_date=date(2026, 1, 1),
        objections=[Obj(raised_date=date(2026, 1, 5), is_written=False)],
    )
    assert result.status == STATUS_DEEMED_ACCEPTANCE
    assert result.acceptance_date == date(2026, 1, 1)
    assert len(result.late_complaints) == 1
    assert "not in writing" in result.late_complaints[0].reason


def test_unresolved_objection_leaves_dates_empty_with_a_warning():
    """Pending means unknown: no acceptance, no due date, no guess."""
    result = run_acceptance(
        delivery_date=date(2026, 1, 1),
        objections=[Obj(raised_date=date(2026, 1, 10), description="goods short-shipped")],
    )
    assert result.status == STATUS_PENDING_RESOLUTION
    assert result.acceptance_date is None
    assert result.due_date is None
    assert result.appointed_day is None
    assert result.days_overdue is None
    warning = next(w for w in result.warnings if w.code == WARNING_PENDING_RESOLUTION)
    assert "2026-01-10" in warning.text
    assert "left empty rather than estimated" in warning.text


def test_acceptance_uses_the_latest_of_several_resolved_objections():
    """The clock cannot resume until the last objection inside the window clears."""
    result = run_acceptance(
        delivery_date=date(2026, 1, 1),
        objections=[
            Obj(raised_date=date(2026, 1, 3), resolved_date=date(2026, 1, 20)),
            Obj(raised_date=date(2026, 1, 9), resolved_date=date(2026, 2, 5)),
        ],
    )
    assert result.status == STATUS_RESOLVED
    assert result.acceptance_date == date(2026, 2, 5)


def test_one_unresolved_among_resolved_keeps_the_date_unknown():
    result = run_acceptance(
        delivery_date=date(2026, 1, 1),
        objections=[
            Obj(raised_date=date(2026, 1, 3), resolved_date=date(2026, 1, 20)),
            Obj(raised_date=date(2026, 1, 9), resolved_date=None),
        ],
    )
    assert result.status == STATUS_PENDING_RESOLUTION
    assert result.acceptance_date is None


def test_window_length_comes_from_config_not_a_literal():
    """Section 6.2: the window length is whatever config says."""
    cfg = make_config()
    cfg._entries["objection_window_days"]["value"] = 7
    result = run_acceptance(cfg, delivery_date=date(2026, 1, 1))
    assert result.objection_window_end == date(2026, 1, 8)


# ------------------------------------------------------- applied period ----


def test_no_written_agreement_uses_no_agreement_days():
    """written_credit_days of None means the statutory no-agreement period (15)."""
    result = run_acceptance(written_credit_days=None)
    assert result.agreed_days is None
    assert result.applied_days == 15
    assert result.clamped is False
    assert result.due_date == date(2026, 1, 27)  # 2026-01-12 + 15
    assert any("no written credit period" in c.rule for c in result.citations)


def test_net_90_is_clamped_to_the_cap():
    """Agreed 90, cap 45 from config: applied 45 and clamped True."""
    result = run_acceptance(written_credit_days=90)
    assert result.agreed_days == 90
    assert result.applied_days == 45
    assert result.clamped is True


def test_net_30_is_not_clamped():
    """Agreed 30 sits under the 45-day cap, so nothing clamps."""
    result = run_acceptance(written_credit_days=30)
    assert result.agreed_days == 30
    assert result.applied_days == 30
    assert result.clamped is False
    assert result.due_date == date(2026, 2, 11)  # 2026-01-12 + 30


def test_cap_is_read_from_config_not_hardcoded():
    cfg = make_config()
    cfg._entries["credit_cap_days"]["value"] = 30
    result = run_acceptance(cfg, written_credit_days=90)
    assert result.applied_days == 30
    assert result.clamped is True


def test_no_regime_logic_applies_the_cap_on_every_supply_date():
    """Trap 2: there are no regimes, so the cap bites regardless of the date."""
    early = run_acceptance(delivery_date=date(2019, 6, 1), written_credit_days=90)
    late = run_acceptance(delivery_date=date(2026, 6, 1), written_credit_days=90)
    assert early.applied_days == late.applied_days == 45
    assert early.clamped is late.clamped is True


def test_missing_statute_constant_fails_loudly():
    """A null window length would make the dates undecidable, so no default is used."""
    cfg = make_config()
    cfg._entries["objection_window_days"]["value"] = None
    with pytest.raises(ConfigError, match="objection_window_days"):
        run_acceptance(cfg)


# --------------------------------------------------------- leap-year dates ----


def test_leap_year_window_end_lands_on_29_february():
    """Delivery 2024-02-14 + 15 days = 2024-02-29, which exists only in a leap year."""
    result = run_acceptance(
        delivery_date=date(2024, 2, 14),
        objections=[Obj(raised_date=date(2024, 2, 29), resolved_date=date(2024, 3, 15))],
    )
    assert result.objection_window_end == date(2024, 2, 29)
    assert result.status == STATUS_RESOLVED
    assert result.acceptance_date == date(2024, 3, 15)


def test_leap_year_due_date_steps_over_29_february():
    """Net 90 clamps to 45: 2024-02-14 + 45 = 2024-03-30 (29-day February)."""
    result = run_acceptance(
        delivery_date=date(2024, 2, 14), written_credit_days=90
    )
    assert result.due_date == date(2024, 3, 30)
    assert result.appointed_day == date(2024, 3, 31)


def test_non_leap_year_window_end_lands_on_28_february():
    """Delivery 2026-02-13 + 15 days closes on 2026-02-28, the last day of a
    common-year February."""
    result = run_acceptance(
        delivery_date=date(2026, 2, 13),
        objections=[Obj(raised_date=date(2026, 2, 28), resolved_date=date(2026, 3, 14))],
    )
    assert result.objection_window_end == date(2026, 2, 28)
    assert result.status == STATUS_RESOLVED


def test_same_delivery_in_a_common_year_ends_the_window_on_1_march():
    """2026-02-14 + 15 days runs past February, unlike the leap-year pair above."""
    result = run_acceptance(delivery_date=date(2026, 2, 14))
    assert result.objection_window_end == date(2026, 3, 1)
    # The objection that would have qualified a day earlier is now outside.
    with_late = run_acceptance(
        delivery_date=date(2026, 2, 14),
        objections=[Obj(raised_date=date(2026, 3, 2))],
    )
    assert [c.date for c in with_late.late_complaints] == [date(2026, 3, 2)]


def test_delivery_on_29_february_itself():
    """A delivery date that only exists in a leap year still anchors normally."""
    result = run_acceptance(delivery_date=date(2024, 2, 29), written_credit_days=30)
    assert result.acceptance_date == date(2024, 2, 29)
    # 2024-02-29 + 30 = 2024-03-30
    assert result.due_date == date(2024, 3, 30)


# ------------------------------------------------------------ days overdue ----


def test_days_overdue_is_null_before_the_appointed_day():
    """Net 30 from a 2026-01-12 delivery: due 2026-02-11, appointed 2026-02-12."""
    on_due = run_acceptance(
        written_credit_days=30, calculation_date=date(2026, 2, 11)
    )
    assert on_due.days_overdue is None  # not yet appointed


def test_days_overdue_counts_from_the_due_date_once_appointed():
    on_appointed = run_acceptance(
        written_credit_days=30, calculation_date=date(2026, 2, 12)
    )
    assert on_appointed.days_overdue == 1
    a_week_later = run_acceptance(
        written_credit_days=30, calculation_date=date(2026, 2, 20)
    )
    assert a_week_later.days_overdue == 9


def test_days_overdue_is_null_when_acceptance_is_unknown():
    result = run_acceptance(
        delivery_date=date(2026, 1, 1),
        objections=[Obj(raised_date=date(2026, 1, 10))],
        calculation_date=date(2026, 6, 1),
    )
    assert result.days_overdue is None


# ------------------------------------------------ citations and assumptions ----


def test_every_constant_read_is_cited_with_its_source():
    result = run_acceptance(written_credit_days=90)
    keys = {c.config_key for c in result.citations}
    assert keys == {"objection_window_days", "credit_cap_days"}
    for citation in result.citations:
        assert citation.statute_ref  # V2:s.2(b), V2:s.15 proviso
        assert citation.id.startswith("acceptance.")
        assert citation.verified is False  # statute sheet not captured yet


def test_no_agreement_path_cites_the_no_agreement_constant():
    result = run_acceptance(written_credit_days=None)
    assert {c.config_key for c in result.citations} == {
        "objection_window_days",
        "no_agreement_days",
    }


def test_read_constants_are_reported_as_unverified_by_the_config():
    """Usage tracking: the constants this rule relied on surface as warnings."""
    cfg = make_config()
    run_acceptance(cfg, written_credit_days=90)
    joined = " ".join(w.text for w in cfg.warnings())
    for key in ("objection_window_days", "credit_cap_days"):
        assert key in joined


def test_oq5_assumption_is_always_recorded():
    """Section 6.2 constraint: say what counts as a written agreement (OQ-5)."""
    with_agreement = run_acceptance(written_credit_days=90)
    without = run_acceptance(written_credit_days=None)
    assert any("OQ-5" in a for a in with_agreement.assumptions)
    assert any("OQ-5" in a for a in without.assumptions)
    assert any("purchase order" in a for a in with_agreement.assumptions)


def test_days_overdue_convention_is_stated_as_an_assumption():
    result = run_acceptance(written_credit_days=30)
    assert any("days_overdue" in a for a in result.assumptions)


# --------------------------------------------------------- contract shape ----


def test_result_validates_against_the_frozen_timeline_model():
    from backend.app.schemas import Timeline

    for kwargs in (
        {},
        {"written_credit_days": 30},
        {"delivery_date": None},
        {"objections": [Obj(raised_date=date(2026, 1, 10))]},
        {"objections": [Obj(raised_date=date(2026, 1, 17), resolved_date=date(2026, 2, 1))]},
        {"delivery_date": date(2024, 2, 29)},
    ):
        result = run_acceptance(**kwargs)
        timeline = Timeline(**result.to_dict())
        assert timeline.objection_status.value == result.status
        if result.due_date is None:
            assert timeline.due_date is None
        else:
            assert timeline.due_date == result.due_date
