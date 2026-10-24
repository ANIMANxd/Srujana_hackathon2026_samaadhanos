"""Dev tests for backend/engine/dates.py (the engine author's own smoke tests).

Covers end-of-month clamping in month stepping (including leap years and
backwards steps), the 31 March financial-year helpers, and the day counter.

These are NOT the spec tests in tests/spec/; those come from the independent test
author and must pass without this module.
"""

from datetime import date

import pytest

from backend.engine.dates import (
    DateError,
    add_months,
    days_ago,
    days_between,
    days_in_month,
    fy_end_after,
    fy_end_before,
    fy_ends_inclusive,
    iso,
    parse_iso,
    rest_dates,
)


# ------------------------------------------------- month-end clamping ----


def test_add_months_normal_case():
    assert add_months(date(2026, 1, 15), 1) == date(2026, 2, 15)
    assert add_months(date(2026, 1, 15), 12) == date(2027, 1, 15)
    assert add_months(date(2026, 6, 30), 3) == date(2026, 9, 30)


def test_add_months_clamps_to_end_of_month():
    # 31 Jan has no 31 Feb, so it clamps to the 28th in a common year.
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    # 31 Mar has no 31 Apr.
    assert add_months(date(2026, 3, 31), 1) == date(2026, 4, 30)
    # 30 Apr has no 31 May... 30 Apr + 1 = 30 May, which exists.
    assert add_months(date(2026, 4, 30), 1) == date(2026, 5, 30)


def test_add_months_leap_year_february():
    # Leap year: 31 Jan + 1 month clamps to the 29th.
    assert add_months(date(2024, 1, 31), 1) == date(2024, 2, 29)
    assert days_in_month(2024, 2) == 29
    assert days_in_month(2026, 2) == 28


def test_add_months_feb_29_anniversary():
    assert add_months(date(2024, 2, 29), 12) == date(2025, 2, 28)
    assert add_months(date(2024, 2, 29), 48) == date(2028, 2, 29)


def test_add_months_steps_across_year_end():
    assert add_months(date(2026, 11, 30), 3) == date(2027, 2, 28)
    assert add_months(date(2026, 12, 31), 1) == date(2027, 1, 31)


def test_add_months_backwards_clamps_too():
    assert add_months(date(2026, 3, 31), -1) == date(2026, 2, 28)
    assert add_months(date(2026, 1, 31), -1) == date(2025, 12, 31)
    assert add_months(date(2024, 3, 31), -1) == date(2024, 2, 29)


def test_add_months_zero_is_the_same_day():
    assert add_months(date(2026, 1, 31), 0) == date(2026, 1, 31)


def test_add_months_rejects_non_date():
    with pytest.raises(DateError, match="datetime.date"):
        add_months("2026-01-31", 1)


# ------------------------------------------------------- rest dates ----


def test_rest_dates_step_monthly_from_the_appointed_day():
    # Section 6.3: rest k is appointed_day + k months, end-of-month clamped.
    assert rest_dates(date(2026, 1, 31), 3) == [
        date(2026, 2, 28),
        date(2026, 3, 31),
        date(2026, 4, 30),
    ]
    assert rest_dates(date(2026, 1, 15), 2) == [date(2026, 2, 15), date(2026, 3, 15)]


def test_rest_dates_of_zero_is_empty():
    assert rest_dates(date(2026, 1, 15), 0) == []


def test_rest_dates_rejects_negative_count():
    with pytest.raises(DateError, match="negative"):
        rest_dates(date(2026, 1, 15), -1)


# ------------------------------------------------------- day counting ----


def test_days_between_is_start_exclusive_end_inclusive():
    assert days_between(date(2026, 1, 1), date(2026, 1, 31)) == 30
    assert days_between(date(2026, 1, 1), date(2026, 2, 1)) == 31
    assert days_between(date(2026, 1, 1), date(2026, 1, 1)) == 0


def test_days_between_counts_leap_february():
    assert days_between(date(2024, 2, 1), date(2024, 3, 1)) == 29
    assert days_between(date(2026, 2, 1), date(2026, 3, 1)) == 28


def test_days_between_is_negative_when_reversed():
    assert days_between(date(2026, 2, 1), date(2026, 1, 1)) == -31


def test_days_between_rejects_non_date():
    with pytest.raises(DateError, match="datetime.date"):
        days_between(date(2026, 1, 1), "2026-02-01")


def test_days_ago():
    assert days_ago(date(2026, 3, 1), 2) == date(2026, 2, 27)
    assert days_ago(date(2024, 3, 1), 1) == date(2024, 2, 29)


# ------------------------------------------------- financial year ends ----


def test_fy_end_before_and_after():
    # The FY runs 1 April to 31 March, so an FY end is always 31 March.
    assert fy_end_before(date(2026, 5, 10)) == date(2026, 3, 31)
    assert fy_end_before(date(2026, 3, 31)) == date(2026, 3, 31)
    assert fy_end_before(date(2026, 3, 30)) == date(2025, 3, 31)
    assert fy_end_after(date(2026, 5, 10)) == date(2027, 3, 31)
    assert fy_end_after(date(2026, 3, 31)) == date(2026, 3, 31)
    assert fy_end_after(date(2026, 3, 30)) == date(2026, 3, 31)


def test_fy_ends_inclusive_walks_31_march_checkpoints():
    # Section 6.4 walks each 31 March in [due_date, calculation_date].
    assert fy_ends_inclusive(date(2025, 4, 1), date(2027, 3, 31)) == [
        date(2026, 3, 31),
        date(2027, 3, 31),
    ]


def test_fy_ends_inclusive_single_checkpoint_at_both_ends():
    assert fy_ends_inclusive(date(2026, 3, 31), date(2026, 3, 31)) == [date(2026, 3, 31)]
    assert fy_ends_inclusive(date(2025, 4, 2), date(2026, 3, 31)) == [date(2026, 3, 31)]


def test_fy_ends_inclusive_empty_when_interval_spans_no_fy_end():
    # Any window inside one FY contains no 31 March.
    assert fy_ends_inclusive(date(2025, 4, 1), date(2026, 3, 30)) == []
    assert fy_ends_inclusive(date(2026, 4, 1), date(2027, 3, 30)) == []


def test_fy_ends_inclusive_rejects_inverted_range():
    with pytest.raises(DateError, match="on or before"):
        fy_ends_inclusive(date(2027, 3, 31), date(2025, 4, 1))


# ------------------------------------------------------------- boundary ----


def test_iso_and_parse_iso_round_trip():
    assert iso(date(2026, 1, 31)) == "2026-01-31"
    assert iso(None) is None
    assert parse_iso("2026-01-31") == date(2026, 1, 31)
    assert parse_iso(None) is None


def test_parse_iso_rejects_bad_forms():
    with pytest.raises(DateError, match="ISO date"):
        parse_iso("31-01-2026")
    with pytest.raises(DateError, match="ISO date"):
        parse_iso("2026-01-31T00:00:00Z")
    with pytest.raises(DateError, match="ISO date"):
        parse_iso("2026-02-30")
    with pytest.raises(DateError, match="ISO date"):
        parse_iso("2026-1-31")
    with pytest.raises(DateError, match="int"):
        parse_iso(20260131)
