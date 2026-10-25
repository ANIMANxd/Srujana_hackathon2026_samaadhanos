"""Fixtures for the finance tests.

The config is the **real** `statute_config.json`, loaded through the same loader the
API uses, so a test cannot pass against a value the product does not ship.
"""

from __future__ import annotations

import copy
import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from backend.app.config_loader import load_config
from backend.finance.config import FinanceConfig, finance_config
from backend.finance.financeability import CaseFacts

CONFIG_PATH = Path(__file__).resolve().parents[3] / "config" / "statute_config.json"


@pytest.fixture()
def raw_config() -> dict[str, Any]:
    return load_config(CONFIG_PATH)


@pytest.fixture()
def config(raw_config: dict[str, Any]) -> FinanceConfig:
    return finance_config(raw_config)


@pytest.fixture()
def config_with_minimum(raw_config: dict[str, Any]) -> dict[str, Any]:
    """The shipped config with `financing.min_amount` set, for the threshold test."""
    patched = copy.deepcopy(raw_config)
    patched["financing"]["value"]["min_amount"] = "1000000.00"
    return patched


@pytest.fixture()
def facts() -> CaseFacts:
    return CaseFacts(
        case_id="01JAV4E7K3M9Q2R5T8V0W1XCZD",
        accepted_amount=Decimal("1250000.00"),
        due_date=date(2026, 10, 29),
    )
