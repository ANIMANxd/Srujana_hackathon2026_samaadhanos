"""money.py — Decimal helpers for the legal-math path (section 6).

Money and rates are decimal.Decimal here; JSON carries them as strings. Floats
never touch a rupee. Rounding happens per ledger row (quantize to 0.01, half-up)
so the ledger sums exactly; that convention is stated on screen.

Pure module: no I/O, no clock, no globals.
"""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

# The ledger row precision. Two decimal places, half-up, per section 6.
Paisa = Decimal("0.01")


class MoneyError(ValueError):
    """A value could not be interpreted as money or a percentage.

    Raised rather than coerced, because a float sneaking into the legal path
    would silently change an award. Plain English so a business owner can read it.
    """


def parse_money(raw: object) -> Decimal:
    """Parse a money value from a string, int or Decimal. Never a float.

    Also the entry point for rates and percentages: they are Decimals here too,
    kept in the units the document states them in (a Bank Rate of 5.50 stays 5.50;
    as_percent() converts to a multiplier only at the point of multiplication).

    Floats are rejected outright: binary floats cannot represent 0.10 exactly, so
    accepting one would plant a rounding error in a number meant for a demand note.
    """
    if isinstance(raw, bool):
        raise MoneyError("money cannot be a boolean; send a decimal string like \"1250000.00\"")
    if isinstance(raw, float):
        raise MoneyError(
            "money cannot be a float; send a decimal string like \"1250000.00\" "
            "so no rounding error is introduced"
        )
    if isinstance(raw, Decimal):
        value = raw
    elif isinstance(raw, int):
        value = Decimal(raw)
    elif isinstance(raw, str):
        text = raw.strip().replace(",", "")
        if not text:
            raise MoneyError("money cannot be an empty string")
        try:
            value = Decimal(text)
        except InvalidOperation as exc:
            raise MoneyError(f"{raw!r} is not a valid amount; use a decimal string like \"1250000.00\"") from exc
    else:
        raise MoneyError(
            f"money must be a decimal string, int or Decimal, not {type(raw).__name__}"
        )
    if not value.is_finite():
        raise MoneyError("money must be a finite amount")
    return value


def rupees(value: Decimal) -> Decimal:
    """Round to 0.01, half-up — the per-row rounding rule from section 6."""
    return value.quantize(Paisa, rounding=ROUND_HALF_UP)


def as_percent(rate_pct: Decimal) -> Decimal:
    """Turn a percentage like 5.50 into the multiplier 0.055.

    Kept explicit so no module guesses whether a rate is already a fraction.
    """
    return rate_pct / Decimal(100)


def apply_rate(amount: Decimal, rate_pct: Decimal, days: int, day_count_fraction_days: int) -> Decimal:
    """Simple interest on `amount` at `rate_pct` for `days`, over the year fraction.

    interest = amount x (rate_pct / 100) x days / day_count_fraction_days

    Returns the unrounded value; call rupees() at the row boundary so the ledger
    rounds once per row and sums exactly. day_count_fraction_days comes from the
    config (365 by convention), never a literal here.
    """
    if day_count_fraction_days <= 0:
        raise MoneyError("day_count_fraction_days must be positive")
    if days < 0:
        raise MoneyError("days cannot be negative")
    return amount * as_percent(rate_pct) * Decimal(days) / Decimal(day_count_fraction_days)


def sum_rows(rows: list[Decimal]) -> Decimal:
    """Sum already-rounded ledger rows.

    Rounding happens per row, so this is an exact sum of the printed ledger, not
    a re-rounding of an aggregate.
    """
    total = Decimal("0")
    for row in rows:
        total += row
    return total
