"""Discount, fee, net and effective cost, with the arithmetic written out.

Every expectation below is hand-computed and shown in a comment (AGENTS.md
section 3: round numbers, the working in the test). Money is Decimal and rounded
half-up to 0.01 at the point of production.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from backend.finance.discount import (
    discount,
    effective_annual_cost_pct,
    fee,
    net_receivable,
    round_money,
)


def test_ten_lakh_at_ten_percent_for_36_5_days():
    """10,00,000 Ã— 10% Ã— 36.5 / 365

    = 100000 Ã— 36.5 / 365
    = 3650000 / 365
    = 10000.00 exactly
    """
    assert discount("1000000", "10", "36.5", 365) == Decimal("10000.00")


def test_tenor_one_day():
    """10,00,000 Ã— 10% Ã— 1 / 365 = 100000 / 365 = 273.9726... -> 273.97 (half-up)."""
    assert discount("1000000", "10", 1, 365) == Decimal("273.97")


def test_tenor_one_year_is_the_rate():
    """10,00,000 Ã— 10% Ã— 365 / 365 = 100000.00 exactly."""
    assert discount("1000000", "10", 365, 365) == Decimal("100000.00")


@pytest.mark.parametrize(
    ("amount", "rate", "expected", "working"),
    [
        ("182.50", "1", Decimal("0.01"), "182.50 / 36500 = 0.005 exactly -> half-up 0.01"),
        ("146.00", "1", Decimal("0.00"), "146.00 / 36500 = 0.004 exactly -> 0.00"),
        ("219.00", "1", Decimal("0.01"), "219.00 / 36500 = 0.006 exactly -> 0.01"),
    ],
)
def test_rounding_is_half_up_on_exact_ties(amount, rate, expected, working):
    """Decimal keeps 0.005 exact; a float would land on 0.00499... and round down."""
    assert discount(amount, rate, 1, 365) == expected, working


def test_decimal_avoids_the_classic_float_rounding_trap():
    """2.675 is stored as 2.67499..., so Python's round() gives 2.67.

    Decimal("2.675") is exact, so half-up gives 2.68. This is the whole reason
    money never touches a float, and it is why the tie tests above are exact
    base-10 values rather than floats.
    """
    assert round(2.675, 2) == 2.67, "the float trap we must not inherit"
    assert round_money(Decimal("2.675")) == Decimal("2.68")


def test_a_zero_fee_is_zero_not_a_missing_value():
    """fee(10,00,000, 0%) = 0.00, and the net is the amount less the discount only."""
    assert fee("1000000.00", "0") == Decimal("0.00")
    assert fee("1000000.00", Decimal("0")) == Decimal("0.00")
    # 1000000 - 10000.00 - 0.00
    assert net_receivable("1000000", "10", "36.5", 365, "0") == Decimal("990000.00")


def test_the_platform_fee_uses_the_config_rate(config):
    """12,50,000 Ã— 0.10% = 1250.000 -> 1250.00."""
    assert fee("1250000.00", config.platform_fee_pct) == Decimal("1250.00")


def test_net_receivable_matches_the_architecture_example(config):
    """The v4 section 9 example: 12,50,000 at 10.25%, 30 days, 0.10% fee.

    discount = 1250000 Ã— 10.25% Ã— 30 / 365 = 3843750 / 365 = 10530.8219... -> 10530.82
    fee      = 1250.00
    net      = 1250000 - 10530.82 - 1250.00 = 1238219.18
    """
    assert net_receivable("1250000.00", "10.25", 30, 365, config.platform_fee_pct) == Decimal(
        "1238219.18"
    )


def test_net_receivable_bounds_are_ordered(config):
    """A higher rate can only reduce the net, so low(8%) >= high(12%)."""
    best = net_receivable("1250000.00", config.rate_band_low, 30, 365, config.platform_fee_pct)
    worst = net_receivable("1250000.00", config.rate_band_high, 30, 365, config.platform_fee_pct)
    assert best > worst
    assert (best, worst) == (Decimal("1240530.82"), Decimal("1236421.23"))


def test_effective_annual_cost_is_annualised_on_the_net():
    """10000 / 990000 Ã— 365 / 36.5 Ã— 100 = 10.1010...% -> 10.10.

    The base is the net received, not the invoice amount, because the net is the
    capital actually advanced.
    """
    assert effective_annual_cost_pct("10000", "990000", "36.5", 365) == Decimal("10.10")


def test_a_float_input_is_refused():
    """0.1 is not Decimal("0.1"); a rupee must never enter through a float."""
    with pytest.raises(TypeError, match="never float"):
        discount(1000000.0, "10", 30, 365)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="never float"):
        fee("1000000", 0.1)  # type: ignore[arg-type]


def test_a_zero_day_count_is_refused():
    with pytest.raises(ValueError, match="day_count must be positive"):
        discount("1000000", "10", 30, 0)


def test_a_negative_tenor_is_refused():
    with pytest.raises(ValueError, match="tenor_days must not be negative"):
        discount("1000000", "10", -1, 365)


def test_a_non_positive_net_is_refused_for_the_effective_cost():
    with pytest.raises(ValueError, match="net_amount must be positive"):
        effective_annual_cost_pct("10000", "0", 30, 365)
