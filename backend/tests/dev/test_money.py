"""Dev tests for backend/engine/money.py (the engine author's own smoke tests).

Covers Decimal parsing, the rejection of floats, half-up rounding at 0.01, and
the rate helpers. Round numbers so every expectation is hand-checkable.

These are NOT the spec tests in tests/spec/; those come from the independent test
author and must pass without this module.
"""

from decimal import Decimal

import pytest

from backend.engine.money import (
    MoneyError,
    apply_rate,
    parse_money,
    rupees,
    sum_rows,
)


# -------------------------------------------------------------- parsing ----


def test_parse_money_from_string_keeps_every_paisa():
    assert parse_money("1250000.00") == Decimal("1250000.00")
    assert parse_money("0.01") == Decimal("0.01")
    assert parse_money("-4500.50") == Decimal("-4500.50")


def test_parse_money_strips_grouping_and_whitespace():
    assert parse_money(" 12,50,000.00 ") == Decimal("1250000.00")


def test_parse_money_accepts_int_and_decimal():
    assert parse_money(1250000) == Decimal("1250000")
    assert parse_money(Decimal("99.99")) == Decimal("99.99")


def test_parse_money_rejects_float():
    """A float cannot represent 0.10 exactly, so it is refused outright."""
    with pytest.raises(MoneyError, match="float"):
        parse_money(12.50)


def test_parse_money_rejects_bool():
    with pytest.raises(MoneyError, match="boolean"):
        parse_money(True)


def test_parse_money_rejects_empty_and_junk():
    with pytest.raises(MoneyError, match="empty"):
        parse_money("")
    with pytest.raises(MoneyError, match="not a valid amount"):
        parse_money("twelve hundred")
    with pytest.raises(MoneyError, match="not a valid amount"):
        parse_money("12.5.6")


def test_parse_money_rejects_infinity_and_nan():
    with pytest.raises(MoneyError, match="finite"):
        parse_money("Infinity")
    with pytest.raises(MoneyError, match="finite"):
        parse_money("NaN")


def test_parse_money_rejects_unsupported_type():
    with pytest.raises(MoneyError, match="decimal string"):
        parse_money(None)


def test_rates_parse_through_the_same_helper():
    """Rates are Decimals too, in the units the document states them in."""
    assert parse_money("5.50") == Decimal("5.50")
    with pytest.raises(MoneyError, match="float"):
        parse_money(5.50)


# ------------------------------------------------------------ rounding ----


def test_rupees_rounds_half_up():
    assert rupees(Decimal("10.005")) == Decimal("10.01")
    assert rupees(Decimal("10.004")) == Decimal("10.00")
    assert rupees(Decimal("-10.005")) == Decimal("-10.01")


def test_rupees_always_lands_on_two_places():
    assert rupees(Decimal("7")) == Decimal("7.00")
    assert rupees(Decimal("7.5")) == Decimal("7.50")


def test_rupees_is_idempotent():
    once = rupees(Decimal("3.335"))
    assert rupees(once) == once


def test_rupees_keeps_large_values_exact():
    # 1250000.005 rounds to 1250000.01 with no float drift.
    assert rupees(Decimal("1250000.005")) == Decimal("1250000.01")


# ---------------------------------------------------------- rate helpers ----


def test_as_percent_converts_percentage_to_multiplier():
    from backend.engine.money import as_percent

    assert as_percent(Decimal("5.50")) == Decimal("0.055")
    assert as_percent(Decimal("100")) == Decimal("1")


def test_apply_rate_simple_interest():
    # 100000 at 16.50% for 30 days over 365 = 1356.164383...
    got = apply_rate(Decimal("100000"), Decimal("16.50"), 30, 365)
    assert rupees(got) == Decimal("1356.16")


def test_apply_rate_zero_days_is_zero():
    assert apply_rate(Decimal("100000"), Decimal("16.50"), 0, 365) == Decimal("0")


def test_apply_rate_rejects_bad_day_counts():
    with pytest.raises(MoneyError, match="positive"):
        apply_rate(Decimal("1"), Decimal("1"), 1, 0)
    with pytest.raises(MoneyError, match="negative"):
        apply_rate(Decimal("1"), Decimal("1"), -1, 365)


def test_sum_rows_is_an_exact_sum_of_rounded_rows():
    rows = [rupees(Decimal("1356.164")), rupees(Decimal("1356.164")), rupees(Decimal("0.005"))]
    assert sum_rows(rows) == Decimal("2712.33")
    # Rounding each row first, then summing, is not the same as summing first:
    # 2712.329 rounds to 2712.33, one paisa short of the per-row sum.
    assert rupees(sum(Decimal("1356.164") for _ in range(2)) + Decimal("0.005")) == Decimal("2712.33")


def test_sum_rows_of_empty_is_zero():
    assert sum_rows([]) == Decimal("0")
