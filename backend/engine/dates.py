"""dates.py — date helpers for the legal-math path (section 6).

Month stepping uses calendar months with end-of-month clamping, which is what
dateutil.relativedelta does. relativedelta is the preferred implementation
(conventions in AGENTS.md); add_months() below keeps the same clamping semantics
and no extra dependency, and both are pinned by the same tests.

The financial year runs 1 April to 31 March, so an FY end is always 31 March.
Section 6.4 walks the 31 March checkpoints in [due_date, calculation_date].

Pure module: no I/O, no clock. Nothing here calls date.today().
"""

from calendar import monthrange
from datetime import date, timedelta

# An Indian financial year ends on 31 March (section 6.4).
FY_END_MONTH = 3
FY_END_DAY = 31


class DateError(ValueError):
    """A date value is missing or out of range in a way the engine will not guess past."""


def days_in_month(year: int, month: int) -> int:
    """Days in a calendar month, handling leap years (February 29)."""
    return monthrange(year, month)[1]


def add_months(start: date, months: int) -> date:
    """Add calendar months, clamping to the end of the target month.

    This is the rest-date rule from section 6.3: rest dates are
    appointed_day + k calendar months, end-of-month clamped. So
    31 Jan + 1 month is 28 Feb in a common year and 29 Feb in a leap year,
    and 31 Mar + 1 month is 30 Apr.

    Negative `months` steps backwards with the same clamping.
    """
    if not isinstance(start, date):
        raise DateError(f"add_months needs a datetime.date, not {type(start).__name__}")
    total = (start.year * 12 + (start.month - 1)) + months
    year, zero_based_month = divmod(total, 12)
    month = zero_based_month + 1
    if year < 1 or year > 9999:
        raise DateError(f"month stepping reached year {year}, outside the representable range")
    return date(year, month, min(start.day, days_in_month(year, month)))


def rest_dates(appointed_day: date, count: int) -> list[date]:
    """The first `count` monthly rest dates after the appointed day (section 6.3).

    Rest k is appointed_day + k months, end-of-month clamped. Returns them in
    ascending order. Zero or negative count yields an empty list.
    """
    if count < 0:
        raise DateError("rest date count cannot be negative")
    return [add_months(appointed_day, k) for k in range(1, count + 1)]


def days_between(start: date, end: date) -> int:
    """Whole days from `start` to `end`; negative when `end` is earlier.

    Day-counting for interest is exclusive of the start day and inclusive of the
    end day, which is exactly (end - start).days. The caller decides whether a
    zero or negative span is an error; this helper only measures.
    """
    if not isinstance(start, date) or not isinstance(end, date):
        raise DateError("days_between needs two datetime.date values")
    return (end - start).days


def fy_end_before(day: date) -> date:
    """The most recent financial-year end (31 March) on or before `day`."""
    candidate = date(day.year, FY_END_MONTH, FY_END_DAY)
    if candidate > day:
        candidate = date(day.year - 1, FY_END_MONTH, FY_END_DAY)
    return candidate


def fy_end_after(day: date) -> date:
    """The earliest financial-year end (31 March) on or after `day`."""
    candidate = date(day.year, FY_END_MONTH, FY_END_DAY)
    if candidate < day:
        candidate = date(day.year + 1, FY_END_MONTH, FY_END_DAY)
    return candidate


def fy_ends_inclusive(start: date, end: date) -> list[date]:
    """Every 31 March checkpoint in the closed interval [start, end] (section 6.4).

    Walks the FY ends from the first one on or after `start` through the last one
    on or before `end`, ascending. An empty list is normal when the interval
    contains no 31 March, which happens whenever start and end fall in the same
    FY. `start` after `end` is an error, because the caller has an inverted range
    and should not silently get no checkpoints.
    """
    if start > end:
        raise DateError(
            f"fy_ends_inclusive needs start on or before end, got {start.isoformat()} then {end.isoformat()}"
        )
    out: list[date] = []
    cursor = fy_end_after(start)
    while cursor <= end:
        out.append(cursor)
        cursor = add_months(cursor, 12)
    return out


def iso(day: date | None) -> str | None:
    """The Z-less ISO form that crosses the API boundary (section 6)."""
    return None if day is None else day.isoformat()


def parse_iso(raw: str | None) -> date | None:
    """Parse a Z-less ISO date string, or pass through None."""
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise DateError(f"expected an ISO date string, not {type(raw).__name__}")
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise DateError(f"{raw!r} is not an ISO date in YYYY-MM-DD form") from exc


def days_ago(reference: date, days: int) -> date:
    """`reference` shifted back by `days` calendar days."""
    if not isinstance(reference, date):
        raise DateError(f"days_ago needs a datetime.date, not {type(reference).__name__}")
    return reference - timedelta(days=days)
