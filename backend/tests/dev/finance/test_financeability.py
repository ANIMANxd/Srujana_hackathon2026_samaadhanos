"""Each section 5.4 reason, one at a time and all together.

`engine_result` is stubbed with SimpleNamespace: finance only reads
`jurisdiction.status`, so a stub proves the coupling is that narrow and keeps the
test fast.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from backend.finance.financeability import CaseFacts, financeability

AS_OF = date(2026, 10, 25)


def _engine(status: str = "ELIGIBLE", remedy: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        jurisdiction=SimpleNamespace(status=status, alternative_remedy=remedy),
    )


def _facts(**overrides) -> CaseFacts:
    base = {
        "case_id": "01JAV4E7K3M9Q2R5T8V0W1XCZD",
        "accepted_amount": Decimal("1250000.00"),
        "due_date": date(2026, 10, 29),
    }
    base.update(overrides)
    return CaseFacts(**base)


def _codes(result) -> list[str]:
    return [reason["code"] for reason in result["reasons"]]


def test_a_clean_case_is_financeable(config):
    result = financeability(_engine(), _facts(), None, AS_OF, config)
    assert result["financeable"] is True
    assert result["reasons"] == []


@pytest.mark.parametrize("status", ["BARRED_SILPI", "EXCLUDED_TRADER", "EXCLUDED_MEDIUM"])
def test_gate_blocked(status, config):
    result = financeability(_engine(status), _facts(), None, AS_OF, config)
    assert result["financeable"] is False
    assert "GATE_BLOCKED" in _codes(result)


def test_gate_blocked_mentions_the_alternative_remedy(config):
    result = financeability(
        _engine("EXCLUDED_MEDIUM", remedy="MSME ODR portal"), _facts(), None, AS_OF, config
    )
    message = next(r["message"] for r in result["reasons"] if r["code"] == "GATE_BLOCKED")
    assert "alternative remedy" in message


def test_written_objection(config):
    result = financeability(
        _engine(), _facts(has_written_objection=True), None, AS_OF, config
    )
    assert result["financeable"] is False
    assert _codes(result) == ["WRITTEN_OBJECTION"]


@pytest.mark.parametrize("stage", [3, 4])
def test_recovery_stage_locked(stage, config):
    result = financeability(_engine(), _facts(), stage, AS_OF, config)
    assert result["financeable"] is False
    assert _codes(result) == ["RECOVERY_STAGE_LOCKED"]


@pytest.mark.parametrize("stage", [None, 1, 2])
def test_recovery_before_stage_three_is_allowed(stage, config):
    result = financeability(_engine(), _facts(), stage, AS_OF, config)
    assert result["financeable"] is True


def test_amount_below_the_configured_minimum(config_with_minimum):
    result = financeability(
        _engine(), _facts(accepted_amount=Decimal("500000.00")), None, AS_OF, config_with_minimum
    )
    assert result["financeable"] is False
    assert _codes(result) == ["AMOUNT_BELOW_MINIMUM"]


def test_amount_exactly_at_the_minimum_is_allowed(config_with_minimum):
    result = financeability(
        _engine(), _facts(accepted_amount=Decimal("1000000.00")), None, AS_OF, config_with_minimum
    )
    assert result["financeable"] is True


def test_an_unconfigured_minimum_is_an_assumption_not_a_block(config):
    """The shipped config has `financing.min_amount: null`.

    Blocking on it would hide the whole demo behind one uncaptured constant
    (the mistake the repo already recorded as CQ-33), so it becomes an assumption.
    """
    assert config.min_amount is None
    result = financeability(_engine(), _facts(accepted_amount=Decimal("1.00")), None, AS_OF, config)
    assert result["financeable"] is True
    assert result["assumptions"], "a missing minimum must be surfaced, not silent"


def test_buyer_not_on_treds_and_the_owner_will_not_invite(config):
    result = financeability(
        _engine(),
        _facts(buyer_on_treds=False, user_declines_invite=True),
        None,
        AS_OF,
        config,
    )
    assert result["financeable"] is False
    assert _codes(result) == ["BUYER_NOT_ON_TREDS"]


def test_buyer_not_on_treds_but_willing_to_invite(config):
    result = financeability(
        _engine(),
        _facts(buyer_on_treds=False, user_declines_invite=False),
        None,
        AS_OF,
        config,
    )
    assert result["financeable"] is True


def test_overdue_by_more_than_the_allowance(config):
    """Default `max_overdue_days` is 0, so one day past the due date blocks."""
    result = financeability(_engine(), _facts(), None, date(2026, 10, 30), config)
    assert result["financeable"] is False
    assert _codes(result) == ["OVERDUE"]


def test_on_the_due_date_itself_is_not_overdue(config):
    """(as_of - due_date).days == 0, which is not > 0."""
    result = financeability(_engine(), _facts(), None, date(2026, 10, 29), config)
    assert result["financeable"] is True


def test_one_day_before_the_due_date_is_not_overdue(config):
    result = financeability(_engine(), _facts(), None, date(2026, 10, 28), config)
    assert result["financeable"] is True


def test_every_reason_is_reported_at_once(config_with_minimum):
    """The owner should see everything wrong, not fix one thing to find the next."""
    result = financeability(
        _engine("EXCLUDED_MEDIUM"),
        _facts(
            accepted_amount=Decimal("1000.00"),
            has_written_objection=True,
            buyer_on_treds=False,
            user_declines_invite=True,
        ),
        3,
        date(2026, 12, 1),
        config_with_minimum,
    )
    assert result["financeable"] is False
    assert set(_codes(result)) == {
        "GATE_BLOCKED",
        "WRITTEN_OBJECTION",
        "RECOVERY_STAGE_LOCKED",
        "AMOUNT_BELOW_MINIMUM",
        "BUYER_NOT_ON_TREDS",
        "OVERDUE",
    }
    assert all(reason["message"] for reason in result["reasons"]), "every reason needs copy"


def test_the_result_has_the_documented_shape(config):
    result = financeability(_engine(), _facts(), None, AS_OF, config)
    assert set(result) == {"financeable", "reasons", "assumptions"}
    assert isinstance(result["financeable"], bool)
    assert isinstance(result["reasons"], list)
