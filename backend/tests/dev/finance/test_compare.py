"""The two-option comparison: both options, real engine interest, no recommendation."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from backend.app.config_loader import load_config
from backend.app.schemas import CaseEvaluationRequest
from backend.engine.config import StatuteConfig
from backend.engine.evaluate import evaluate_case
from backend.finance.compare import compare_options
from backend.finance.financeability import CaseFacts

AS_OF = date(2026, 10, 25)
EXPECTED = date(2026, 11, 24)
DUE = date(2026, 10, 29)

# 12,50,000 at 10.25% for 30 days, 0.10% fee -> the v4 section 9 working example.
CASE_ID = "01JAV4E7K3M9Q2R5T8V0W1XCZD"


def _engine(status: str = "ELIGIBLE", outstanding: str = "1250000.00") -> SimpleNamespace:
    return SimpleNamespace(
        jurisdiction=SimpleNamespace(status=status, alternative_remedy=None),
        financials=SimpleNamespace(principal_outstanding=Decimal(outstanding)),
    )


def _facts(**overrides) -> CaseFacts:
    base = {
        "case_id": CASE_ID,
        "accepted_amount": Decimal("1250000.00"),
        "due_date": DUE,
        "recovery_state": "STAGE_1_PREPARED",
    }
    base.update(overrides)
    return CaseFacts(**base)


def test_recommendation_is_always_none(config):
    """Golden rule 20: the field exists so nobody adds one later."""
    body = compare_options(
        _engine(), _facts(), EXPECTED, lambda _d: Decimal("14768.84"), config, as_of=AS_OF
    )
    assert body["recommendation"] is None
    assert "recommendation" in body


def test_none_is_the_only_value_shipped(config):
    """Nothing in the module can produce a recommendation."""
    for status in ("ELIGIBLE", "EXCLUDED_MEDIUM", "BARRED_SILPI"):
        body = compare_options(
            _engine(status), _facts(), EXPECTED, lambda _d: Decimal("0.00"), config, as_of=AS_OF
        )
        assert body["recommendation"] is None


def test_the_interest_callable_is_used_and_gets_the_expected_date(config):
    """s.16 interest must come from the engine, not from this module."""
    calls: list[date] = []

    def interest_to_date(day: date) -> Decimal:
        calls.append(day)
        return Decimal("14768.84")

    body = compare_options(_engine(), _facts(), EXPECTED, interest_to_date, config, as_of=AS_OF)
    assert calls == [EXPECTED], "the callable must be called once, with the expected date"
    assert body["recover_with_law"]["interest_to_expected_date"] == "14768.84"


def test_option_two_totals_are_principal_plus_interest(config):
    """12,50,000.00 + 14,768.84 = 12,64,768.84."""
    body = compare_options(
        _engine(), _facts(), EXPECTED, lambda _d: Decimal("14768.84"), config, as_of=AS_OF
    )
    option_two = body["recover_with_law"]
    assert option_two["principal"] == "1250000.00"
    assert option_two["total_if_paid"] == "1264768.84"
    assert option_two["expected_payment_date"] == "2026-11-24"


def test_the_engine_principal_wins_over_the_accepted_amount(config):
    """Part-payments belong to the engine; finance must not re-add them."""
    body = compare_options(
        _engine(outstanding="1000000.00"),
        _facts(),
        EXPECTED,
        lambda _d: Decimal("1000.00"),
        config,
        as_of=AS_OF,
    )
    assert body["recover_with_law"]["principal"] == "1000000.00"
    assert body["recover_with_law"]["total_if_paid"] == "1001000.00"


def test_option_one_is_available_before_the_due_date(config):
    body = compare_options(
        _engine(), _facts(), EXPECTED, lambda _d: Decimal("0.00"), config, as_of=AS_OF
    )
    option_one = body["get_paid_early"]
    assert option_one["available"] is True
    assert option_one["unavailable_reasons"] == []
    assert option_one["indicative"] is not None


def test_option_one_numbers_match_the_hand_computation(config):
    """The tenor is days from as_of to the due date: 2026-10-29 - 2026-10-25 = 4.

    discount(12%) = 1250000 × 12% × 4/365 =  600000/365 = 1643.8356... -> 1643.84
    discount( 8%) = 1250000 ×  8% × 4/365 =  400000/365 = 1095.8904... -> 1095.89
    fee           = 1250000 × 0.10%                = 1250.00
    net range     = 1247106.16 .. 1247654.11

    At a 4-day tenor the flat fee is larger than the discount — a real property of
    short tenors, and the reason this number must not be hard-coded anywhere.
    """
    body = compare_options(
        _engine(), _facts(), EXPECTED, lambda _d: Decimal("0.00"), config, as_of=AS_OF
    )
    indicative = body["get_paid_early"]["indicative"]
    assert indicative["tenor_days"] == 4
    assert indicative["accepted_amount"] == "1250000.00"
    assert indicative["net_receivable_range"] == {"low": "1247106.16", "high": "1247654.11"}
    assert indicative["platform_fee_pct"] == "0.10"
    assert indicative["rate_band_pct"]["label"] == config.rate_band_label


def test_option_one_is_unavailable_when_overdue(config):
    """Past the due date, Option 1 is blocked and Option 2 stays available."""
    body = compare_options(
        _engine(), _facts(), EXPECTED, lambda _d: Decimal("0.00"), config, as_of=date(2026, 11, 2)
    )
    option_one = body["get_paid_early"]
    assert option_one["available"] is False
    assert option_one["indicative"] is None
    assert option_one["unavailable_reasons"], "a disabled option must say why"
    assert body["recover_with_law"]["available"] is True


def test_a_blocked_option_never_silently_computes_numbers(config):
    """No indicative numbers when the option is unavailable: they would be a lie."""
    body = compare_options(
        _engine("EXCLUDED_MEDIUM"), _facts(), EXPECTED, lambda _d: Decimal("0"), config, as_of=AS_OF
    )
    assert body["get_paid_early"]["available"] is False
    assert body["get_paid_early"]["indicative"] is None


def test_both_options_are_reported_even_when_one_is_blocked(config):
    """The card shows two columns; neither may vanish."""
    body = compare_options(
        _engine("EXCLUDED_MEDIUM"), _facts(), EXPECTED, lambda _d: Decimal("0"), config, as_of=AS_OF
    )
    assert set(body) >= {"get_paid_early", "recover_with_law"}
    assert body["recover_with_law"]["available"] is True


def test_the_settlement_line_is_config_driven(config):
    body = compare_options(
        _engine(), _facts(), EXPECTED, lambda _d: Decimal("0"), config, as_of=AS_OF
    )
    assert "T+2" in body["get_paid_early"]["indicative"]["settlement"]
    assert "treds.settlement_days" in body["get_paid_early"]["indicative"]["settlement"]


def test_the_body_matches_the_contract_shape(config):
    """The body is what `OptionsResponse` validates; unknown keys would be a drift."""
    from backend.app.schemas_v4 import OptionsResponse

    body = compare_options(
        _engine(), _facts(), EXPECTED, lambda _d: Decimal("14768.84"), config, as_of=AS_OF
    )
    model = OptionsResponse.model_validate(body)
    assert model.recommendation is None
    assert model.get_paid_early.available is True
    assert model.recover_with_law.total_if_paid == Decimal("1264768.84")


# ---------------------------------------------------- real engine wiring ----


def _request(calculation_date: date) -> CaseEvaluationRequest:
    return CaseEvaluationRequest.model_validate(
        {
            "contract_version": "1.0",
            "case_id": CASE_ID,
            "supplier": {
                "name": "Sample Supplies Pvt Ltd (synthetic)",
                "udyam_number": "UDYAM-SYN-000000000",
                "enterprise_class": "SMALL",
                "activity": "MANUFACTURING",
                "nic_codes": ["25990"],
                "udyam_registration_date": "2023-06-01",
                "investment_cr": "1.20",
                "turnover_cr": "8.00",
            },
            "buyer": {
                "name": "Sample Buyer Corp (synthetic)",
                "gstin": "29SYN000000000Z1",
                "tax_rate_pct": "31.20",
                "cost_of_capital_pct": "12.00",
            },
            "transaction": {
                "contract_date": "2026-08-01",
                "supply_date": "2026-09-14",
                "invoice_date": "2026-09-16",
                "delivery_date": "2026-09-14",
                "principal": "1250000.00",
                "written_credit_days": 45,
                "calculation_date": calculation_date.isoformat(),
                "years_deferred": None,
            },
            "objections": [],
            "part_payments": [],
            "acknowledgments": [],
            "evidence": {
                "items": [
                    {"kind": "INVOICE", "present": True, "ref": "INV-0042"},
                    {"kind": "PO", "present": True, "ref": "PO-7781"},
                    {"kind": "DELIVERY_PROOF", "present": True, "ref": None},
                ]
            },
            "config_overrides": None,
        }
    )


def test_the_engine_supplies_the_interest_across_the_real_boundary(config):
    """End to end: the callable is the frozen engine, and the total is its claim.

    The engine says interest 14,768.84 and total claim 12,64,768.84 as of
    2026-11-24 for this case; finance must reproduce that total and not its own.
    """
    statute = StatuteConfig.from_dict(load_config())

    def interest_to_date(day: date) -> Decimal:
        result = evaluate_case(statute, _request(day))
        assert result.financials is not None
        return result.financials.interest_total

    engine_at_as_of = evaluate_case(statute, _request(AS_OF))
    body = compare_options(
        engine_at_as_of, _facts(), EXPECTED, interest_to_date, config, as_of=AS_OF
    )

    expected_claim = evaluate_case(statute, _request(EXPECTED)).financials
    assert expected_claim is not None
    assert body["recover_with_law"]["total_if_paid"] == format(expected_claim.total_claim, "f")
    assert body["recover_with_law"]["interest_to_expected_date"] == format(
        expected_claim.interest_total, "f"
    )
