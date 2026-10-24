"""Dev tests for backend/engine/buyer_cost.py (the engine author's smoke tests).

Covers: no checkpoint, one checkpoint, two checkpoints, a partial payment made
before 31 March (chained through interest.py), a gated feature off and on, and
the two hard constraints from section 6.4 — the three lines are never summed,
and 43B(h) timing never reaches the interest figure.

Every expected figure is hand-computed in a comment from round inputs. These are
NOT the spec tests in tests/spec/.
"""

from datetime import date
from decimal import Decimal

import pytest

from backend.engine.buyer_cost import (
    S22_DISCLOSURE_ID,
    WARNING_MISSING_STATUTE_CONSTANT,
    WARNING_UNVERIFIED_GATED_FEATURE,
    BuyerCostInputError,
    evaluate_buyer_cost,
)
from backend.engine.config import ConfigError
from backend.engine.interest import evaluate_interest
from backend.engine.money import MoneyError, Paisa
from backend.tests.dev.test_gate import make_config

D = Decimal

# Round inputs: tax 20%, cost of capital 10%, one deferred year, so every
# checkpoint figure lands on whole rupees unless the principal has paise.
TAX = D("20")
CAPITAL = D("10")
YEARS = D("1")

TIMELINE_OPEN = [(date.min, D("100000"))]


def buy(cfg=None, **kwargs):
    """A 100000 principal, due 2025-12-01, calculated 2026-04-15 (one 31 March)."""
    facts = dict(
        interest_total=D("5000"),
        statutory_rate_pct=D("16.50"),
        buyer_tax_rate_pct=TAX,
        due_date=date(2025, 12, 1),
        calculation_date=date(2026, 4, 15),
        cost_of_capital_pct=CAPITAL,
        years_deferred=YEARS,
        principal_timeline=TIMELINE_OPEN,
    )
    facts.update(kwargs)
    return evaluate_buyer_cost(cfg or make_config(), **facts)


def epochs(*pairs):
    """A config whose bank_rate_epochs are exactly `pairs` of (from, pct)."""
    cfg = make_config()
    cfg._entries["bank_rate_epochs"]["value"] = [
        {"from": start, "bank_rate_pct": pct} for start, pct in pairs
    ]
    cfg._bank_rate_epochs = cfg._load_bank_rate_epochs()
    return cfg


class _Pay:
    """Minimal part-payment satisfying interest.PaymentLike."""

    def __init__(self, when, amount):
        self.date = when
        self.amount = amount


def _pay(when, amount):
    return _Pay(when, amount)


# ------------------------------------------------------- deferral checkpoints ----


def test_no_checkpoint_means_deferral_does_not_apply():
    """due 2026-01-15 to calc 2026-02-20 contains no 31 March."""
    result = buy(due_date=date(2026, 1, 15), calculation_date=date(2026, 2, 20))
    assert result.deferral.applies is False
    assert result.deferral.checkpoints == []
    assert result.deferral.deferral_cost is None


def test_no_checkpoint_does_not_read_the_43bh_constant():
    """An untouched constant must not report itself as used (section 5)."""
    cfg = make_config()
    buy(cfg, due_date=date(2026, 1, 15), calculation_date=date(2026, 2, 20))
    assert "section_43bh_first_fy" not in cfg.used_keys


def test_one_checkpoint():
    """Window 2025-12-01..2026-04-15 holds 2026-03-31 alone.

    unpaid 100000.00
    tax_timing_effect = 100000 x 20% = 20000.00
    deferral_cost      = 20000.00 x 10% x 1 = 2000.00
    """
    result = buy()
    assert result.deferral.applies is True
    assert [c.fy_end for c in result.deferral.checkpoints] == [date(2026, 3, 31)]
    checkpoint = result.deferral.checkpoints[0]
    assert checkpoint.unpaid_principal == D("100000.00")
    assert checkpoint.tax_timing_effect == D("20000.00")
    assert result.deferral.deferral_cost == D("2000.00")


def test_two_checkpoints_sum_within_the_line():
    """Window 2024-12-01..2026-04-15 holds 2025-03-31 and 2026-03-31.

    Each: 100000 x 20% = 20000.00 tax timing, x 10% x 1 = 2000.00 cost.
    The line total is their sum: 4000.00.
    """
    result = buy(due_date=date(2024, 12, 1), calculation_date=date(2026, 4, 15))
    assert [c.fy_end for c in result.deferral.checkpoints] == [
        date(2025, 3, 31),
        date(2026, 3, 31),
    ]
    assert all(c.unpaid_principal == D("100000.00") for c in result.deferral.checkpoints)
    assert all(c.tax_timing_effect == D("20000.00") for c in result.deferral.checkpoints)
    # The line total equals the sum of its rounded per-checkpoint costs.
    summed = sum((c.deferral_cost for c in result.deferral.checkpoints), D("0"))
    assert result.deferral.deferral_cost == summed == D("4000.00")
    assert result.deferral.applies is True


def test_checkpoint_on_the_window_edges_is_inclusive():
    """31 March exactly on due_date and exactly on calculation_date both count."""
    result = buy(due_date=date(2026, 3, 31), calculation_date=date(2026, 3, 31))
    assert [c.fy_end for c in result.deferral.checkpoints] == [date(2026, 3, 31)]


def test_checkpoints_before_the_43bh_floor_are_dropped():
    """With the floor at 2025-26, FY 2024-25 (ends 2025-03-31) is excluded."""
    cfg = make_config()
    cfg._entries["section_43bh_first_fy"]["value"] = "2025-26"
    result = buy(
        cfg, due_date=date(2024, 12, 1), calculation_date=date(2026, 4, 15)
    )
    assert [c.fy_end for c in result.deferral.checkpoints] == [date(2026, 3, 31)]


def test_cleared_principal_takes_a_checkpoint_out():
    """Principal already zero on 31 March means nothing is outstanding past the limit."""
    result = buy(
        principal_timeline=[(date.min, D("100000")), (date(2026, 3, 1), D("0.00"))]
    )
    assert result.deferral.checkpoints == []
    assert result.deferral.applies is False
    assert result.deferral.deferral_cost is None


def test_calculation_before_due_date_has_no_checkpoint():
    result = buy(due_date=date(2026, 4, 1), calculation_date=date(2026, 2, 1))
    assert result.deferral.applies is False
    assert result.deferral.checkpoints == []


def test_null_43bh_floor_degrades_with_a_warning():
    """Section 5: a null constant warns and the engine still runs."""
    cfg = make_config()
    cfg._entries["section_43bh_first_fy"]["value"] = None
    result = buy(cfg)
    assert result.deferral.applies is False
    assert result.deferral.deferral_cost is None
    assert any(w.code == WARNING_MISSING_STATUTE_CONSTANT for w in result.warnings)
    assert any("section_43bh_first_fy" in w.text for w in cfg.warnings())


def test_malformed_43bh_floor_fails_loudly():
    cfg = make_config()
    cfg._entries["section_43bh_first_fy"]["value"] = "not-a-year"
    with pytest.raises(ConfigError, match="section_43bh_first_fy"):
        buy(cfg)


def test_empty_timeline_is_refused_rather_than_guessed():
    with pytest.raises(BuyerCostInputError, match="principal_timeline"):
        buy(principal_timeline=[])


# ------------------------------------------- partial payment before 31 March ----


def test_partial_payment_before_31_march_reduces_unpaid_principal():
    """Chained through interest.py so the timeline is the real one.

    Appointed 2026-01-01, 40000 paid on 2026-03-01, calculated 2026-04-15,
    Bank Rate 5.50% -> statutory 16.50%, INTEREST_FIRST appropriation:

      REST [01-01,02-01) 31d on 100000: 1401.37, balance 101401.37
      REST [02-01,03-01) 28d on 101401.37: 1283.49, balance 102684.86
      PAYMENT 40000 absorbs the 2684.86 interest, so principal falls by
        37315.14 -> 62684.86 from 2026-03-01

    The 2026-03-31 checkpoint then sees 62684.86, not the original 100000:
      tax_timing_effect = 62684.86 x 20% = 12536.972   -> 12536.97
      deferral_cost      = 12536.97 x 10% x 1 = 1253.697 -> 1253.70
    """
    cfg = epochs(("2025-01-01", "5.50"))
    interest = evaluate_interest(
        cfg,
        principal=D("100000"),
        appointed_day=date(2026, 1, 1),
        calculation_date=date(2026, 4, 15),
        part_payments=[_pay(date(2026, 3, 1), D("40000"))],
    )
    assert interest.principal_outstanding == D("62684.86")

    result = buy(
        cfg,
        interest_total=interest.interest_total,
        due_date=date(2025, 12, 1),
        calculation_date=date(2026, 4, 15),
        principal_timeline=interest.principal_timeline,
    )
    checkpoint = result.deferral.checkpoints[0]
    assert checkpoint.fy_end == date(2026, 3, 31)
    # The payment made before 31 March is what lowers this figure.
    assert checkpoint.unpaid_principal == D("62684.86")
    assert checkpoint.unpaid_principal < D("100000.00")
    assert checkpoint.tax_timing_effect == D("12536.97")
    assert result.deferral.deferral_cost == D("1253.70")


def test_a_payment_later_than_the_checkpoint_leaves_it_unreduced():
    """Paid 2026-04-10, after the 2026-03-31 checkpoint, so that checkpoint
    still sees the full principal."""
    cfg = epochs(("2025-01-01", "5.50"))
    interest = evaluate_interest(
        cfg,
        principal=D("100000"),
        appointed_day=date(2026, 1, 1),
        calculation_date=date(2026, 4, 15),
        part_payments=[_pay(date(2026, 4, 10), D("40000"))],
    )
    result = buy(
        cfg,
        interest_total=interest.interest_total,
        due_date=date(2025, 12, 1),
        calculation_date=date(2026, 4, 15),
        principal_timeline=interest.principal_timeline,
    )
    assert result.deferral.checkpoints[0].unpaid_principal == D("100000.00")


# ------------------------------------------------------------- line 1 ----


def test_pretax_equivalent_divides_by_one_minus_tax_rate():
    """16.50 / (1 - 0.312) = 23.982558... -> 23.98"""
    result = buy(buyer_tax_rate_pct=D("31.2"))
    assert result.permanent_loss.pretax_equivalent_rate_pct == D("23.98")


def test_pretax_equivalent_at_a_lower_tax_rate_is_lower():
    """16.50 / (1 - 0.20) = 20.625 -> 20.63 (half-up)."""
    result = buy()
    assert result.permanent_loss.pretax_equivalent_rate_pct == D("20.63")


def test_permanent_loss_is_interest_only_never_plus_43bh_timing():
    """Trap 3: the 43B(h) timing effect must never reach the interest figure."""
    result = buy()
    assert result.permanent_loss.interest_non_deductible == D("5000")
    # The tax timing sits on the deferral line, and only there.
    assert result.deferral.checkpoints[0].tax_timing_effect == D("20000.00")
    assert result.permanent_loss.interest_non_deductible != (
        D("5000") + D("20000.00")
    )


def test_permanent_loss_stays_interest_only_when_deferral_does_not_apply():
    result = buy(due_date=date(2026, 1, 15), calculation_date=date(2026, 2, 20))
    assert result.permanent_loss.interest_non_deductible == D("5000")
    assert result.deferral.applies is False


def test_zero_interest_is_allowed():
    result = buy(interest_total=D("0"))
    assert result.permanent_loss.interest_non_deductible == D("0")


def test_negative_interest_is_refused():
    with pytest.raises(BuyerCostInputError, match="interest_total"):
        buy(interest_total=D("-1"))


def test_tax_rate_of_100_percent_is_refused():
    """1 - tax rate would be zero, so the pretax figure has no finite value."""
    with pytest.raises(BuyerCostInputError, match="tax rate"):
        buy(buyer_tax_rate_pct=D("100"))


def test_negative_cost_of_capital_is_refused():
    with pytest.raises(BuyerCostInputError, match="cost_of_capital_pct"):
        buy(cost_of_capital_pct=D("-1"))


def test_float_inputs_are_refused():
    with pytest.raises(MoneyError, match="float"):
        buy(interest_total=5000.00)


# ------------------------------------------------------------- line 3 ----


def test_s22_disclosure_is_always_present():
    result = buy()
    assert [f.id for f in result.disclosure_flags] == [S22_DISCLOSURE_ID]
    assert "audited accounts" in result.disclosure_flags[0].text
    assert result.disclosure_flags[0].verified is False


def test_gated_feature_off_emits_no_pressure_points():
    """Default config has all three gated flags false (OQ-8)."""
    cfg = make_config()
    assert all(v is False for v in cfg.gated_features().values())
    result = buy(cfg)
    assert result.pressure_points == []
    assert not any(w.code == WARNING_UNVERIFIED_GATED_FEATURE for w in result.warnings)


def test_gated_feature_on_emits_exactly_that_pressure_point():
    cfg = make_config()
    cfg._entries["gated_features"]["value"]["gst_itc_180d"] = True
    result = buy(cfg)
    assert [p.id for p in result.pressure_points] == ["gst_itc_180d"]
    assert "180 days" in result.pressure_points[0].text
    warning = next(w for w in result.warnings if w.code == WARNING_UNVERIFIED_GATED_FEATURE)
    assert "gst_itc_180d" in warning.text
    assert "OQ-8" in warning.text


def test_two_gated_features_on_emit_two_rows_in_order():
    cfg = make_config()
    cfg._entries["gated_features"]["value"]["gst_itc_180d"] = True
    cfg._entries["gated_features"]["value"]["s19_deposit"] = True
    result = buy(cfg)
    assert [p.id for p in result.pressure_points] == ["gst_itc_180d", "s19_deposit"]


def test_gated_flags_are_read_even_when_all_false():
    """The gate decision itself reads the constant, so it is cited and reported."""
    cfg = make_config()
    result = buy(cfg)
    assert any(c.config_key == "gated_features" for c in result.citations)
    assert "gated_features" in cfg.used_keys


# --------------------------------------------------------- constraints ----


def test_to_dict_emits_exactly_the_four_contract_keys():
    """Golden rule 8: no combined total can appear, because none is emitted."""
    result = buy(due_date=date(2024, 12, 1), calculation_date=date(2026, 4, 15))
    payload = result.to_dict()
    assert set(payload) == {
        "permanent_loss",
        "deferral",
        "disclosure_flags",
        "other_pressure_points",
    }


def test_no_attribute_offers_a_combined_total():
    result = buy()
    forbidden = {"total", "combined", "sum", "grand_total", "overall", "buyer_loss"}
    assert forbidden.isdisjoint(vars(result))


def test_checkpoint_dict_matches_the_contract_shape():
    """Section 8.3: fy_end, unpaid_principal, tax_timing_effect - nothing more."""
    result = buy()
    checkpoint = result.deferral.checkpoints[0].to_dict()
    assert set(checkpoint) == {"fy_end", "unpaid_principal", "tax_timing_effect"}
    assert "deferral_cost" not in checkpoint  # the contract keeps the total only


# --------------------------------------------------------- citations and shape ----


def test_read_constants_are_cited_with_their_source():
    result = buy(due_date=date(2024, 12, 1), calculation_date=date(2026, 4, 15))
    keys = {c.config_key for c in result.citations}
    assert {"section_43bh_first_fy", "gated_features"} <= keys
    for citation in result.citations:
        assert citation.statute_ref
        assert citation.id.startswith("buyer_cost.")
        assert citation.verified is False


def test_assumptions_state_the_never_summed_rule_and_the_43bh_exclusion():
    joined = " ".join(result_text for result_text in buy().assumptions)
    assert "never added into one number" in joined
    assert "never added to interest" in joined


def test_rounding_is_half_up_at_the_checkpoint():
    """tax timing 62684.86 x 20% = 12536.972 rounds down, cost rounds up."""
    result = buy(principal_timeline=[(date.min, D("62684.86"))])
    checkpoint = result.deferral.checkpoints[0]
    for value in (checkpoint.unpaid_principal, checkpoint.tax_timing_effect):
        assert value == value.quantize(Paisa)


def test_result_validates_against_the_frozen_buyer_cost_model():
    from backend.app.schemas import BuyerCost

    for kwargs in (
        {},
        {"due_date": date(2024, 12, 1), "calculation_date": date(2026, 4, 15)},
        {"due_date": date(2026, 1, 15), "calculation_date": date(2026, 2, 20)},
        {"interest_total": D("0"), "buyer_tax_rate_pct": D("25.168")},
        {"statutory_rate_pct": D("17.25"), "buyer_tax_rate_pct": D("31.2")},
    ):
        payload = buy(**kwargs).to_dict()
        model = BuyerCost(**payload)
        assert model.permanent_loss.pretax_equivalent_rate_pct >= 0
        assert model.deferral.applies == (len(model.deferral.checkpoints) > 0)
