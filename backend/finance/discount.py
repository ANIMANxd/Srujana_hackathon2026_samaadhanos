"""Discount, fee and net receivable maths (architecture_v4 section 1.1).

Pure: no I/O, no clock, no network, no LLM. Decimal only — a `float` anywhere in
this module's inputs is a bug, not a convenience.

    discount          = amount × annual_rate_pct × tenor_days / (100 × day_count)
    fee               = amount × fee_pct / 100
    net_receivable    = amount − discount − fee

Every result is rounded half-up to 0.01 at the point it is produced, never at the
end of a longer chain (AGENTS.md section 5).
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Final

CENT: Final = Decimal("0.01")
HUNDRED: Final = Decimal(100)


def as_decimal(value: Decimal | int | str, *, field: str) -> Decimal:
    """Coerce a Decimal-compatible input, refusing float and bool.

    Money and rates arrive as Decimal, int or decimal string. A float is rejected
    because `0.1` is not `Decimal("0.1")` and the difference is a rupee on a large
    invoice.
    """
    if isinstance(value, bool) or isinstance(value, float):
        raise TypeError(
            f"{field} must be Decimal, int or a decimal string, never "
            f"{type(value).__name__} (use Decimal(str(...)) at the edge)"
        )
    if isinstance(value, Decimal):
        result = value
    else:
        result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError(f"{field} must be finite, got {result!r}")
    return result


def round_money(value: Decimal) -> Decimal:
    """Half-up to 0.01. The one rounding rule for finance money."""
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def discount(
    amount: Decimal | int | str,
    annual_rate_pct: Decimal | int | str,
    tenor_days: Decimal | int | str,
    day_count: int | Decimal | str,
) -> Decimal:
    """The financier's discount on the accepted amount, rounded half-up to 0.01.

    `tenor_days` accepts a fraction (e.g. 36.5) because a card may quote a part
    day; a real tenor is a whole number of days.
    """
    principal = as_decimal(amount, field="amount")
    rate = as_decimal(annual_rate_pct, field="annual_rate_pct")
    tenor = as_decimal(tenor_days, field="tenor_days")
    basis = as_decimal(day_count, field="day_count")

    if basis <= 0:
        raise ValueError(f"day_count must be positive, got {basis}")
    if tenor < 0:
        raise ValueError(f"tenor_days must not be negative, got {tenor}")
    if principal < 0:
        raise ValueError(f"amount must not be negative, got {principal}")

    return round_money(principal * rate * tenor / (HUNDRED * basis))


def fee(amount: Decimal | int | str, fee_pct: Decimal | int | str) -> Decimal:
    """The platform fee on the accepted amount, rounded half-up to 0.01."""
    principal = as_decimal(amount, field="amount")
    pct = as_decimal(fee_pct, field="fee_pct")
    if pct < 0:
        raise ValueError(f"fee_pct must not be negative, got {pct}")
    return round_money(principal * pct / HUNDRED)


def net_receivable(
    amount: Decimal | int | str,
    annual_rate_pct: Decimal | int | str,
    tenor_days: Decimal | int | str,
    day_count: int | Decimal | str,
    fee_pct: Decimal | int | str,
) -> Decimal:
    """What the supplier actually receives: amount less discount less fee."""
    principal = as_decimal(amount, field="amount")
    return (
        principal
        - discount(principal, annual_rate_pct, tenor_days, day_count)
        - fee(principal, fee_pct)
    )


def effective_annual_cost_pct(
    discount_amount: Decimal | int | str,
    net_amount: Decimal | int | str,
    tenor_days: Decimal | int | str,
    day_count: int | Decimal | str,
) -> Decimal:
    """The annualised cost of the discount, on the money actually received.

        cost = discount / net × (day_count / tenor_days) × 100

    The base is `net` rather than `amount` on purpose: you paid the discount to
    get the net early, so the net is the capital you really borrowed. Rounded
    half-up to 0.01.
    """
    cost = as_decimal(discount_amount, field="discount_amount")
    net = as_decimal(net_amount, field="net_amount")
    tenor = as_decimal(tenor_days, field="tenor_days")
    basis = as_decimal(day_count, field="day_count")

    if net <= 0:
        raise ValueError(f"net_amount must be positive, got {net}")
    if tenor <= 0:
        raise ValueError(f"tenor_days must be positive, got {tenor}")
    if basis <= 0:
        raise ValueError(f"day_count must be positive, got {basis}")

    return round_money(cost / net * basis / tenor * HUNDRED)
