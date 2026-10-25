"""Finance maths for the v4 two-option model.

Pure functions over `Decimal`: no I/O, no clock, no network, no LLM. Separate from
the legal engine so the engine stays frozen (architecture_v4 section 2). Every
constant comes from config (`backend/finance/config.py`).
"""

from backend.finance.compare import bid_quote, compare_options
from backend.finance.config import FinanceConfig, finance_config
from backend.finance.discount import (
    as_decimal,
    discount,
    effective_annual_cost_pct,
    fee,
    net_receivable,
    round_money,
)
from backend.finance.financeability import CaseFacts, financeability

__all__ = [
    "CaseFacts",
    "FinanceConfig",
    "as_decimal",
    "bid_quote",
    "compare_options",
    "discount",
    "effective_annual_cost_pct",
    "fee",
    "finance_config",
    "financeability",
    "net_receivable",
    "round_money",
]
