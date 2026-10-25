"""A typed, read-only view over the config entries finance is allowed to use.

Config over constants (golden rule 4): every rate, day count, threshold and
settlement day in `backend/finance/` comes from here, and nothing in the maths
carries a number of its own.

The v4 sections (`treds`, `financing`, `mock_financing`) are *not* part of the
engine's `REQUIRED_KEYS`, so `StatuteConfig` ignores them. Finance therefore reads
the raw config mapping (`backend.app.config_loader.load_config()`), which keeps the
existing `{value, source_ref, verified, note}` envelope intact for citations.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from backend.finance.discount import as_decimal


@dataclass(frozen=True)
class FinanceConfig:
    """Every config value the finance maths may use, plus its provenance."""

    day_count: Decimal
    min_amount: Decimal | None
    max_overdue_days: int
    advance_pct: Decimal

    platform_fee_pct: Decimal
    rate_band_low: Decimal
    rate_band_high: Decimal
    rate_band_label: str

    settlement_days: int
    buyer_acceptance_required: bool
    without_recourse: bool

    financing_source: str
    treds_source: str
    mock_financing_source: str
    interest_source: str


def _section(raw: Mapping[str, Any], name: str) -> dict[str, Any]:
    entry = raw.get(name)
    if not isinstance(entry, Mapping):
        raise ValueError(f"config is missing the {name!r} section")
    value = entry.get("value")
    if not isinstance(value, Mapping):
        raise ValueError(f"config section {name!r} has no object 'value'")
    return dict(value)


def _source(raw: Mapping[str, Any], name: str) -> str:
    entry = raw.get(name)
    if isinstance(entry, Mapping):
        return str(entry.get("source_ref", ""))
    return ""


def finance_config(raw: Mapping[str, Any]) -> FinanceConfig:
    """Read and validate the config sections finance depends on.

    Raises with the section name rather than guessing a default, so a missing
    constant is a startup error and not a quietly wrong discount.
    """
    financing = _section(raw, "financing")
    mock = _section(raw, "mock_financing")
    treds = _section(raw, "treds")

    rate_band = mock.get("rate_band")
    if not isinstance(rate_band, Mapping):
        raise ValueError("config mock_financing.rate_band must be an object with low/high")

    min_amount_raw = financing.get("min_amount")
    return FinanceConfig(
        day_count=as_decimal(financing["day_count"], field="financing.day_count"),
        min_amount=(
            None if min_amount_raw is None else as_decimal(min_amount_raw, field="financing.min_amount")
        ),
        max_overdue_days=int(financing["max_overdue_days"]),
        advance_pct=as_decimal(financing["advance_pct"], field="financing.advance_pct"),
        platform_fee_pct=as_decimal(mock["platform_fee_pct"], field="mock_financing.platform_fee_pct"),
        rate_band_low=as_decimal(rate_band["low"], field="mock_financing.rate_band.low"),
        rate_band_high=as_decimal(rate_band["high"], field="mock_financing.rate_band.high"),
        rate_band_label=str(rate_band.get("label", "")),
        settlement_days=int(treds["settlement_days"]),
        buyer_acceptance_required=bool(treds["buyer_acceptance_required"]),
        without_recourse=bool(treds["without_recourse"]),
        financing_source=_source(raw, "financing"),
        treds_source=_source(raw, "treds"),
        mock_financing_source=_source(raw, "mock_financing"),
        interest_source=_source(raw, "interest_multiplier"),
    )
