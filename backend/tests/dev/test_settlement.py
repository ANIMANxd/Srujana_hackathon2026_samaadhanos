"""Dev tests for backend/engine/settlement.py (the engine author's smoke tests).

Covers the split offer: waiver on interest only, upfront taken after the waiver,
payments that add back to the payable exactly, and the supplier's net recovery.

Settlement has no response schema in section 8.3 yet, so there is no frozen model
to validate against here; the shape itself is logged as an open contract question.

These are NOT the spec tests in tests/spec/.
"""

from decimal import Decimal

import pytest

from backend.engine.money import MoneyError, Paisa
from backend.engine.settlement import (
    PAYMENT_SECOND,
    PAYMENT_UPFRONT,
    SettlementInputError,
    evaluate_settlement,
)

D = Decimal


def settle(**kwargs):
    """A 100000 principal with 5000 interest, 50% up front, 20% waived, 30 days."""
    facts = dict(
        principal_outstanding=D("100000"),
        interest_outstanding=D("5000"),
        upfront_pct=D("50"),
        waiver_pct=D("20"),
        days_to_second_payment=30,
    )
    facts.update(kwargs)
    return evaluate_settlement(**facts)


def sum_payments(result):
    return sum((p.amount for p in result.payments), Decimal("0"))


# ------------------------------------------------------------- the split ----


def test_basic_split_of_the_offer():
    """total_claim 105000, waiver 20% of the 5000 interest -> 1000 waived.
    Payable 104000, 50% up front -> 52000 now and 52000 in 30 days."""
    result = settle()
    assert result.total_claim == D("105000.00")
    assert result.interest_waived == D("1000.00")
    assert result.interest_paid == D("4000.00")
    assert result.principal_paid == D("100000.00")
    assert result.total_payable == D("104000.00")
    assert result.net_recovery == D("104000.00")


def test_payments_carry_their_slots_and_timings():
    result = settle()
    assert [p.kind for p in result.payments] == [PAYMENT_UPFRONT, PAYMENT_SECOND]
    assert [p.days_from_now for p in result.payments] == [0, 30]
    assert [p.amount for p in result.payments] == [D("52000.00"), D("52000.00")]


def test_net_recovery_is_the_claim_minus_the_waiver():
    result = settle()
    assert result.net_recovery == result.total_claim - result.interest_waived
    # Nothing is invented: it is exactly principal plus interest not waived.
    assert result.net_recovery == result.principal_paid + result.interest_paid


def test_payments_add_back_to_the_payable_exactly():
    assert sum_payments(settle()) == settle().total_payable


def test_waiver_never_touches_principal():
    """Principal is owed for goods delivered; the lever is interest only."""
    for waiver in (D("0"), D("20"), D("50"), D("100")):
        result = settle(waiver_pct=waiver)
        assert result.principal_paid == D("100000.00")
        assert result.principal_paid + result.interest_paid == result.total_payable


def test_zero_waiver_keeps_all_interest():
    result = settle(waiver_pct=D("0"))
    assert result.interest_waived == D("0.00")
    assert result.interest_paid == D("5000.00")
    assert result.total_payable == D("105000.00")
    assert result.net_recovery == D("105000.00")


def test_full_waiver_leaves_only_principal():
    result = settle(waiver_pct=D("100"))
    assert result.interest_waived == D("5000.00")
    assert result.interest_paid == D("0.00")
    assert result.total_payable == D("100000.00")
    assert result.net_recovery == D("100000.00")


def test_full_upfront_leaves_nothing_for_the_second_payment():
    result = settle(upfront_pct=D("100"))
    assert [p.amount for p in result.payments] == [D("104000.00"), D("0.00")]


def test_zero_upfront_pushes_everything_to_the_second_payment():
    result = settle(upfront_pct=D("0"))
    assert [p.amount for p in result.payments] == [D("0.00"), D("104000.00")]
    assert sum_payments(result) == result.total_payable


def test_no_interest_owed_still_splits_the_principal():
    result = settle(interest_outstanding=D("0"))
    assert result.total_claim == D("100000.00")
    assert result.interest_waived == D("0.00")
    assert sum_payments(result) == D("100000.00")


def test_rounding_never_leaks_a_paisa():
    """Upfront is rounded, the second payment takes the exact remainder."""
    odd = settle(
        principal_outstanding=D("100000.01"),
        interest_outstanding=D("5000.00"),
        upfront_pct=D("33.33"),
        waiver_pct=D("33.33"),
    )
    assert sum_payments(odd) == odd.total_payable
    for payment in odd.payments:
        assert payment.amount == payment.amount.quantize(Paisa)


def test_every_amount_is_rounded_to_paisa():
    result = settle(upfront_pct=D("33.33"), waiver_pct=D("33.33"))
    for value in (
        result.total_claim,
        result.interest_waived,
        result.interest_paid,
        result.principal_paid,
        result.total_payable,
        result.net_recovery,
    ):
        assert value == value.quantize(Paisa)


# ------------------------------------------------------------ assumptions ----


def test_the_four_documented_assumptions_are_listed():
    """Section 8.1 asks for plain arithmetic with the assumptions stated."""
    joined = " ".join(settle().assumptions)
    assert "outstanding interest only" in joined
    assert "after the waiver" in joined
    assert "No time value of money" in joined
    assert "half-up" in joined


def test_assumptions_repeat_the_inputs_that_drove_the_split():
    joined = " ".join(settle().assumptions)
    assert "50" in joined and "20" in joined


def test_assumptions_note_the_buyer_cost_lines_are_excluded():
    joined = " ".join(settle().assumptions)
    assert "excludes every buyer-cost line" in joined


def test_zero_waiver_still_explains_itself():
    """A degenerate offer must not silently drop the assumptions."""
    assert len(settle(waiver_pct=D("0")).assumptions) >= 5


# ------------------------------------------------------------ guards ----


def test_out_of_range_percentages_are_refused_not_clamped():
    with pytest.raises(SettlementInputError, match="upfront_pct"):
        settle(upfront_pct=D("101"))
    with pytest.raises(SettlementInputError, match="upfront_pct"):
        settle(upfront_pct=D("-1"))
    with pytest.raises(SettlementInputError, match="waiver_pct"):
        settle(waiver_pct=D("-0.01"))


def test_negative_days_are_refused():
    with pytest.raises(SettlementInputError, match="days_to_second_payment"):
        settle(days_to_second_payment=-1)


def test_fractional_days_are_refused():
    """A day count is whole days; silently flooring it would misstate the offer."""
    with pytest.raises(SettlementInputError, match="days_to_second_payment"):
        settle(days_to_second_payment=30.5)


def test_negative_amounts_are_refused():
    with pytest.raises(SettlementInputError, match="principal_outstanding"):
        settle(principal_outstanding=D("-1"))
    with pytest.raises(SettlementInputError, match="interest_outstanding"):
        settle(interest_outstanding=D("-1"))


def test_float_amounts_are_refused():
    """Floats never reach an offer figure (golden rule 3)."""
    with pytest.raises(MoneyError, match="float"):
        settle(principal_outstanding=100000.00)


def test_percentages_at_the_boundaries_are_allowed():
    assert settle(upfront_pct=D("0"), waiver_pct=D("0")).total_payable == D("105000.00")
    assert settle(upfront_pct=D("100"), waiver_pct=D("100")).total_payable == D(
        "100000.00"
    )


# ------------------------------------------------------ no combined figure ----


def test_result_offers_no_buyer_cost_total():
    """Golden rule 8: a settlement splits principal and interest, it never adds
    the three buyer-cost lines to anything."""
    result = settle()
    assert {"permanent_loss", "deferral", "disclosure_flags"}.isdisjoint(vars(result))
    assert {"total", "combined", "grand_total"}.isdisjoint(vars(result))


def test_to_dict_carries_the_engine_local_shape():
    payload = settle().to_dict()
    assert set(payload) == {
        "total_claim",
        "interest_waived",
        "interest_paid",
        "principal_paid",
        "total_payable",
        "payments",
        "net_recovery",
        "upfront_pct",
        "waiver_pct",
        "days_to_second_payment",
        "assumptions",
    }
    assert set(payload["payments"][0]) == {"kind", "days_from_now", "amount"}


def test_inputs_are_echoed_without_rescaling():
    result = settle(upfront_pct=D("25"), waiver_pct=D("12.5"), days_to_second_payment=45)
    assert result.upfront_pct == D("25")
    assert result.waiver_pct == D("12.5")
    assert result.days_to_second_payment == 45
