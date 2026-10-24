"""Dev tests for backend/engine/interest.py (the engine author's smoke tests).

Covers: monthly rests with capitalisation, the two rate modes across a mid-delay
Bank Rate change, part-payments restarting the rest cycle, both appropriation
modes, overpayment, payments before the appointed day, and the invariant that
totals equal the sum of the rounded rows.

Every expected figure is hand-computed in a comment from round inputs. These are
NOT the spec tests in tests/spec/, which come from the independent test author.

Convention note (OQ-3): part-payments are rest boundaries. This is the documented
default, so it is asserted rather than questioned here.
"""

from datetime import date
from decimal import Decimal

import pytest

from backend.engine.config import ConfigError, StatuteConfig
from backend.engine.interest import (
    KIND_PAYMENT,
    KIND_REST,
    KIND_STUB,
    RATE_MODE_FLOATING,
    RATE_MODE_FROZEN,
    WARNING_OVERPAYMENT,
    InterestInputError,
    evaluate_interest,
)
from backend.engine.money import MoneyError, Paisa
from backend.tests.dev.test_gate import make_config

D = Decimal


# ------------------------------------------------------------- helpers ----


def epochs(*pairs):
    """A config whose bank_rate_epochs are exactly `pairs` of (from, pct)."""
    cfg = make_config()
    cfg._entries["bank_rate_epochs"]["value"] = [
        {"from": start, "bank_rate_pct": pct} for start, pct in pairs
    ]
    cfg._bank_rate_epochs = cfg._load_bank_rate_epochs()
    return cfg


def ledger(result):
    return [(r.kind, r.from_date, r.to_date, r.interest) for r in result.ledger]


def run(cfg=None, **kwargs):
    """A 365000 claim, appointed 2026-04-01, unless overridden.

    365000 x 16.50% / 365 = 165.00 per day exactly, so every expectation below
    lands on round numbers.
    """
    facts = dict(
        principal=D("365000"),
        appointed_day=date(2026, 4, 1),
        calculation_date=date(2026, 5, 11),
    )
    facts.update(kwargs)
    return evaluate_interest(cfg or make_config(), **facts)


class Pay:
    """Minimal part-payment satisfying PaymentLike."""

    def __init__(self, when, amount):
        self.date = when
        self.amount = amount


# ------------------------------------------------------ basic accrual ----


def test_full_rest_period_then_stub():
    """365000 at 16.50% is 165.00/day; 30 days then 10 days on the new balance.

    REST [04-01, 05-01): 365000 x 0.165 x 30 / 365 = 4950.00
    STUB [05-01, 05-11): 369950 x 0.165 x 10 / 365 = 1672.3767... -> 1672.38
    """
    result = run()
    assert [(r.kind, r.from_date, r.to_date) for r in result.ledger] == [
        (KIND_REST, date(2026, 4, 1), date(2026, 5, 1)),
        (KIND_STUB, date(2026, 5, 1), date(2026, 5, 11)),
    ]
    assert result.ledger[0].interest == D("4950.00")
    assert result.ledger[1].interest == D("1672.38")
    assert result.interest_total == D("6622.38")
    assert result.principal_outstanding == D("365000")
    assert result.interest_outstanding == D("6622.38")
    assert result.total_claim == D("371622.38")


def test_compounding_applies_to_principal_plus_interest():
    """The stub must accrue on the capitalised balance, not the bare principal.

    On 365000 alone the stub would be 1650.00; capitalising 4950.00 first makes
    it 1672.38, a difference of 22.38.
    """
    result = run()
    stub = result.ledger[1]
    assert stub.opening == D("369950.00")
    assert stub.interest == D("1672.38")
    assert stub.interest != D("1650.00")


def test_rows_are_continuous_and_close_on_the_claim():
    """Each row opens where the last closed, and the last row closes on total_claim."""
    result = run()
    previous = None
    for row in result.ledger:
        if previous is not None:
            assert row.opening == previous.closing
        assert row.opening + row.interest - row.payment == row.closing
        previous = row
    assert previous.closing == result.total_claim


def test_daily_accrual_is_on_the_calculation_date_balance():
    """371622.38 x 0.165 / 365 = 167.9936... -> 167.99"""
    assert run().daily_accrual == D("167.99")


def test_rate_segments_cover_the_whole_delay():
    result = run()
    assert [(s.from_date, s.to_date) for s in result.rate_segments] == [
        (date(2026, 4, 1), date(2026, 5, 11))
    ]
    assert result.rate_segments[0].statutory_rate_pct == D("16.50")
    assert result.rate_segments[0].bank_rate_pct == D("5.50")


# ------------------------------------------------ totals equal row sums ----


def test_totals_equal_the_sum_of_the_rows():
    scenarios = [
        {},
        {"part_payments": [Pay(date(2026, 4, 21), D("100000"))]},
        {"part_payments": [Pay(date(2026, 4, 21), D("100000")), Pay(date(2026, 5, 2), D("50000"))]},
        {"appropriation_mode": "PRINCIPAL_FIRST",
         "part_payments": [Pay(date(2026, 4, 21), D("100000"))]},
        {"principal": D("12345.67"), "calculation_date": date(2026, 6, 3)},
    ]
    for kwargs in scenarios:
        result = run(**kwargs)
        row_sum = sum((row.interest for row in result.ledger), D("0"))
        assert result.interest_total == row_sum, kwargs
        assert result.total_claim == result.principal_outstanding + result.interest_outstanding


def test_every_ledger_value_is_rounded_to_paisa():
    result = run(part_payments=[Pay(date(2026, 4, 21), D("7777.77"))])
    for row in result.ledger:
        for value in (row.opening, row.interest, row.payment, row.closing, row.rate_pct):
            assert value == value.quantize(Paisa), row


# ------------------------------------------------------- rate modes ----


def two_rate_config():
    """Bank Rate 5.50% from 2026-04-01, 6.00% from 2026-04-15 (mid-delay)."""
    return epochs(("2026-04-01", "5.50"), ("2026-04-15", "6.00"))


def test_floating_splits_the_first_period_at_the_rate_change():
    """Rates: 16.50% to 04-15, 18.00% after. Multiplier 3 from config.

    REST [04-01, 05-01): 365000 x (0.165 x 14 + 0.18 x 16) / 365
                        = 365000 x 5.19 / 365 = 5190.00
    STUB [05-01, 05-11): 370190 x 0.18 x 10 / 365 = 1825.5945... -> 1825.59
    """
    result = run(two_rate_config(), rate_mode=RATE_MODE_FLOATING)
    assert result.ledger[0].interest == D("5190.00")
    assert result.ledger[1].interest == D("1825.59")
    assert result.interest_total == D("7015.59")
    assert [(s.from_date, s.to_date, s.statutory_rate_pct) for s in result.rate_segments] == [
        (date(2026, 4, 1), date(2026, 4, 15), D("16.50")),
        (date(2026, 4, 15), date(2026, 5, 11), D("18.00")),
    ]


def test_frozen_uses_the_appointed_day_rate_for_the_whole_period():
    """The appointed day is 2026-04-01, so 5.50% / 16.50% never changes.

    REST 365000 x 0.165 x 30 / 365 = 4950.00
    STUB 369950 x 0.165 x 10 / 365 = 1672.3767... -> 1672.38
    """
    result = run(two_rate_config(), rate_mode=RATE_MODE_FROZEN)
    assert result.ledger[0].interest == D("4950.00")
    assert result.ledger[1].interest == D("1672.38")
    assert result.interest_total == D("6622.38")
    assert len(result.rate_segments) == 1
    segment = result.rate_segments[0]
    assert segment.bank_rate_pct == D("5.50")
    assert segment.statutory_rate_pct == D("16.50")
    assert (segment.from_date, segment.to_date) == (date(2026, 4, 1), date(2026, 5, 11))


def test_a_mid_delay_rate_change_makes_the_two_modes_differ():
    """The required section 11 case: same claim, two rate modes, two answers."""
    floating = run(two_rate_config(), rate_mode=RATE_MODE_FLOATING)
    frozen = run(two_rate_config(), rate_mode=RATE_MODE_FROZEN)
    assert floating.interest_total == D("7015.59")
    assert frozen.interest_total == D("6622.38")
    assert floating.interest_total > frozen.interest_total
    assert floating.total_claim != frozen.total_claim


def test_a_row_spanning_a_rate_change_is_flagged():
    result = run(two_rate_config(), rate_mode=RATE_MODE_FLOATING)
    first = result.ledger[0]
    assert "Rate changed during this row" in first.note
    assert first.rate_pct == D("16.50")  # the rate at the row's start


def test_frozen_mode_ignores_a_change_after_the_appointed_day():
    """Appointed 2026-05-01 (6.00% epoch): the earlier 5.50% is not used."""
    cfg = epochs(("2026-04-01", "5.50"), ("2026-05-01", "6.00"))
    result = run(
        cfg,
        appointed_day=date(2026, 5, 1),
        calculation_date=date(2026, 6, 11),
        rate_mode=RATE_MODE_FROZEN,
    )
    # Rates: 5.50% epoch before 05-01, 6.00% (18.00%) from 05-01.
    # REST [05-01, 06-01): 31 days, 365000 x 0.18 x 31 / 365 = 5580.00
    assert result.rate_segments[0].bank_rate_pct == D("6.00")
    assert result.ledger[0].interest == D("5580.00")


# ------------------------------------------------------- part-payments ----


def test_payment_restarts_the_rest_cycle():
    """Payment 100000 on 2026-04-21, so rests move to 04-21 + k months.

    Had the cycle not restarted, a REST row would fall on 2026-05-01; instead the
    cycle runs 04-21 -> 05-21, past the calculation date, so the ledger is
    STUB, PAYMENT, STUB.

    STUB [04-01, 04-21): 365000 x 0.165 x 20 / 365 = 3300.00, capitalised
    PAYMENT: balance 368300 - 100000 = 268300 (interest bucket drained first)
    STUB [04-21, 05-11): 268300 x 0.165 x 20 / 365 = 2425.7260... -> 2425.73
    """
    result = run(part_payments=[Pay(date(2026, 4, 21), D("100000"))])
    assert [r.kind for r in result.ledger] == [KIND_STUB, KIND_PAYMENT, KIND_STUB]
    assert result.ledger[0].interest == D("3300.00")
    assert result.ledger[1].payment == D("100000.00")
    assert result.ledger[1].closing == D("268300.00")
    assert result.ledger[2].interest == D("2425.73")
    assert result.interest_total == D("5725.73")
    assert result.principal_outstanding == D("268300")
    assert result.interest_outstanding == D("2425.73")
    assert result.total_claim == D("270725.73")


def test_payment_on_a_rest_date_is_capitalised_before_it_is_applied():
    """Payment lands exactly on the 2026-05-01 rest: rest first, then payment.

    REST [04-01, 05-01): 4950.00, balance 369950
    PAYMENT: 369950 - 100000 = 269950 (4950 of interest absorbed first)
    STUB [05-01, 05-11): 269950 x 0.165 x 10 / 365 = 1220.3219... -> 1220.32
    """
    result = run(part_payments=[Pay(date(2026, 5, 1), D("100000"))])
    assert [r.kind for r in result.ledger] == [KIND_REST, KIND_PAYMENT, KIND_STUB]
    assert result.ledger[0].interest == D("4950.00")
    assert result.ledger[1].opening == D("369950.00")
    assert result.ledger[2].interest == D("1220.32")
    assert result.interest_total == D("6170.32")
    assert result.total_claim == D("271170.32")


def test_payment_before_the_appointed_day_reduces_principal_only():
    """No interest has accrued yet, so the payment moves principal and nothing else.

    365000 - 50000 = 315000, then STUB [04-01, 04-11):
    315000 x 0.165 x 10 / 365 = 1423.9726... -> 1423.97
    """
    result = run(
        principal=D("365000"),
        calculation_date=date(2026, 4, 11),
        part_payments=[Pay(date(2026, 3, 25), D("50000"))],
    )
    first = result.ledger[0]
    assert first.kind == KIND_PAYMENT
    assert first.from_date == date(2026, 3, 25)
    assert first.interest == D("0.00")
    assert first.rate_pct == D("0.00")
    assert result.ledger[1].from_date == date(2026, 4, 1)  # interest starts at appointed
    assert result.ledger[1].interest == D("1423.97")
    assert result.principal_outstanding == D("315000")
    assert result.interest_outstanding == D("1423.97")


def test_overpayment_clears_the_claim_and_warns():
    """Section 6.3: a payment larger than the balance clears it, with a warning."""
    result = run(part_payments=[Pay(date(2026, 4, 21), D("999999"))])
    assert result.ledger[1].payment == D("368300.00")  # only the balance, not 999999
    assert result.ledger[1].closing == D("0.00")
    assert result.principal_outstanding == D("0")
    assert result.interest_outstanding == D("0")
    assert result.total_claim == D("0")
    assert result.interest_total == D("3300.00")
    warning = next(w for w in result.warnings if w.code == WARNING_OVERPAYMENT)
    assert "999999" in warning.text
    assert "631699" in warning.text  # 999999 - 368300


def test_two_payments_are_applied_in_date_order():
    result = run(
        part_payments=[
            Pay(date(2026, 5, 2), D("50000")),
            Pay(date(2026, 4, 21), D("100000")),
        ]
    )
    payments = [r for r in result.ledger if r.kind == KIND_PAYMENT]
    assert [p.from_date for p in payments] == [date(2026, 4, 21), date(2026, 5, 2)]
    # STUB 3300.00 capitalised; payment 100000 absorbs it, principal 268300.
    # STUB [04-21, 05-02) 11d: 268300 x 0.165 x 11 / 365 = 1334.149... -> 1334.15
    # Payment 50000 absorbs that 1334.15, leaving 48665.85 of principal:
    #   268300 - 48665.85 = 219634.15
    # STUB [05-02, 05-11) 9d: 219634.15 x 0.165 x 9 / 365 = 893.5800... -> 893.58
    assert result.principal_outstanding == D("219634.15")
    assert result.interest_outstanding == D("893.58")
    assert result.total_claim == D("220527.73")
    assert result.interest_total == D("5527.73")  # 3300.00 + 1334.15 + 893.58


def test_a_non_positive_payment_is_refused():
    with pytest.raises(InterestInputError, match="positive"):
        run(part_payments=[Pay(date(2026, 4, 21), D("0"))])


# ------------------------------------------------------ appropriation ----


def test_appropriation_modes_split_differently_but_total_the_same():
    """Section 6.3: identical total balance, different principal/interest split.

    INTEREST_FIRST: the 100000 absorbs the 3300.00 interest, leaving 96700
                    against principal -> principal 268300.
    PRINCIPAL_FIRST: 100000 comes off principal -> principal 265000, and the
                     3300.00 interest survives, so interest_outstanding is
                     3300.00 + 2425.73 = 5725.73.
    """
    interest_first = run(
        part_payments=[Pay(date(2026, 4, 21), D("100000"))],
        appropriation_mode="INTEREST_FIRST",
    )
    principal_first = run(
        part_payments=[Pay(date(2026, 4, 21), D("100000"))],
        appropriation_mode="PRINCIPAL_FIRST",
    )

    assert interest_first.total_claim == principal_first.total_claim == D("270725.73")
    assert interest_first.interest_total == principal_first.interest_total == D("5725.73")

    assert interest_first.principal_outstanding == D("268300")
    assert interest_first.interest_outstanding == D("2425.73")

    assert principal_first.principal_outstanding == D("265000")
    assert principal_first.interest_outstanding == D("5725.73")

    # principal_outstanding comes from the split, not from a subtraction shortcut.
    for result in (interest_first, principal_first):
        assert result.principal_outstanding + result.interest_outstanding == result.total_claim


def test_appropriation_does_not_change_the_ledger_interest():
    """The rows are identical; only the post-payment bucket split differs."""
    interest_first = run(
        part_payments=[Pay(date(2026, 4, 21), D("100000"))],
        appropriation_mode="INTEREST_FIRST",
    )
    principal_first = run(
        part_payments=[Pay(date(2026, 4, 21), D("100000"))],
        appropriation_mode="PRINCIPAL_FIRST",
    )
    assert ledger(interest_first) == ledger(principal_first)


# ------------------------------------------------------- boundary dates ----


def test_no_interest_before_the_appointed_day():
    result = run(
        principal=D("365000"),
        appointed_day=date(2026, 4, 1),
        calculation_date=date(2026, 3, 15),
    )
    assert result.ledger == []
    assert result.rate_segments == []
    assert result.interest_total == D("0")
    assert result.total_claim == D("365000")
    assert result.daily_accrual == D("0.00")


def test_rests_step_over_leap_day_and_clamp():
    """Appointed 2024-01-31: rest 1 clamps to 02-29, rest 2 lands on 03-31.

    REST [01-31, 02-29): 365000 x 0.165 x 29 / 365 = 4785.00
    REST [02-29, 03-31): 369785 x 0.165 x 31 / 365 = 5182.0555... -> 5182.06
    """
    cfg = epochs(("2024-01-01", "5.50"))
    result = run(
        cfg,
        appointed_day=date(2024, 1, 31),
        calculation_date=date(2024, 3, 31),
    )
    assert [(r.kind, r.from_date, r.to_date) for r in result.ledger] == [
        (KIND_REST, date(2024, 1, 31), date(2024, 2, 29)),
        (KIND_REST, date(2024, 2, 29), date(2024, 3, 31)),
    ]
    assert result.ledger[0].interest == D("4785.00")
    assert result.ledger[1].interest == D("5182.06")
    assert result.interest_total == D("9967.06")


def test_common_year_rest_lands_on_28_february():
    cfg = epochs(("2026-01-01", "5.50"))
    result = run(
        cfg,
        appointed_day=date(2026, 1, 31),
        calculation_date=date(2026, 2, 28),
    )
    assert [(r.kind, r.from_date, r.to_date) for r in result.ledger] == [
        (KIND_REST, date(2026, 1, 31), date(2026, 2, 28)),
    ]


def test_calculation_on_the_rest_date_capitalises_and_stops():
    result = run(calculation_date=date(2026, 5, 1))
    assert [r.kind for r in result.ledger] == [KIND_REST]
    assert result.ledger[0].interest == D("4950.00")
    assert result.interest_outstanding == D("4950.00")


# ------------------------------------------------ citations and modes ----


def test_every_constant_read_is_cited_with_its_source():
    result = run()
    keys = {c.config_key for c in result.citations}
    assert {"interest_multiplier", "bank_rate_epochs", "day_count_fraction_days",
            "payment_boundary_convention"} <= keys
    for citation in result.citations:
        assert citation.statute_ref
        assert citation.id.startswith("interest.")
        assert citation.verified is False  # statute sheet not captured yet


def test_mode_defaults_from_config_are_cited():
    result = run()
    keys = {c.config_key for c in result.citations}
    assert {"rate_mode_default", "appropriation_mode_default"} <= keys
    assert result.rate_mode == "FLOATING"
    assert result.appropriation_mode == "INTEREST_FIRST"


def test_explicit_modes_replace_the_config_default_without_citing_it():
    result = run(rate_mode=RATE_MODE_FROZEN, appropriation_mode="PRINCIPAL_FIRST")
    keys = {c.config_key for c in result.citations}
    assert "rate_mode_default" not in keys
    assert "appropriation_mode_default" not in keys
    assert result.rate_mode == RATE_MODE_FROZEN
    assert result.appropriation_mode == "PRINCIPAL_FIRST"


def test_the_payment_convention_is_stated_in_assumptions():
    """Section 6.3 constraint: state the convention on screen (OQ-3)."""
    result = run()
    joined = " ".join(result.assumptions)
    assert "PAYMENT_DATE_IS_REST_BOUNDARY" in joined
    assert "OQ-3" in joined
    assert "lawyer review" in joined


def test_assumptions_state_both_rate_modes_and_appropriation():
    floating = run(rate_mode=RATE_MODE_FLOATING)
    frozen = run(rate_mode=RATE_MODE_FROZEN)
    assert "Bank Rate epoch boundary" in " ".join(floating.assumptions)
    assert "appoint" in " ".join(frozen.assumptions)
    assert "total balance is the same" in " ".join(floating.assumptions)


def test_read_constants_surface_as_unverified_warnings():
    cfg = make_config()
    run(cfg)
    joined = " ".join(w.text for w in cfg.warnings())
    assert "interest_multiplier" in joined
    assert "bank_rate_epochs" in joined


# ----------------------------------------------------------- guards ----


def test_unknown_rate_mode_is_refused():
    with pytest.raises(ConfigError, match="rate mode"):
        run(rate_mode="SOMETHING_ELSE")


def test_unknown_appropriation_mode_is_refused():
    with pytest.raises(ConfigError, match="appropriation mode"):
        run(appropriation_mode="SPLIT_EVENLY")


def test_float_principal_is_refused():
    """Floats never touch a rupee (section 6, golden rule 3)."""
    with pytest.raises(MoneyError, match="float"):
        run(principal=365000.00)


def test_negative_principal_is_refused():
    with pytest.raises(InterestInputError, match="negative"):
        run(principal=D("-1"))


def test_null_statute_constant_fails_loudly():
    cfg = make_config()
    cfg._entries["interest_multiplier"]["value"] = None
    with pytest.raises(ConfigError, match="interest_multiplier"):
        run(cfg)


def test_null_day_count_fails_loudly():
    cfg = make_config()
    cfg._entries["day_count_fraction_days"]["value"] = None
    with pytest.raises(ConfigError, match="day_count_fraction_days"):
        run(cfg)


def test_no_bank_rate_epoch_for_the_appointed_day_fails_loudly():
    """Guessing a rate would be inventing law (golden rule 1)."""
    from backend.engine.config import NoEpochFound

    cfg = epochs(("2026-04-01", "5.50"))
    with pytest.raises(NoEpochFound, match="bank_rate_epochs"):
        run(cfg, appointed_day=date(2026, 1, 15), calculation_date=date(2026, 5, 11))


# --------------------------------------------------------- contract shape ----


def test_result_validates_against_the_frozen_financials_model():
    from backend.app.schemas import Financials

    scenarios = [
        {},
        {"part_payments": [Pay(date(2026, 4, 21), D("100000"))]},
        {"rate_mode": RATE_MODE_FROZEN, "part_payments": [Pay(date(2026, 5, 1), D("50000"))]},
        {"appropriation_mode": "PRINCIPAL_FIRST"},
        {"principal": D("12345.67"), "calculation_date": date(2026, 6, 3)},
        {"calculation_date": date(2026, 3, 15)},
    ]
    for kwargs in scenarios:
        result = run(two_rate_config(), **kwargs)
        financials = Financials(**result.to_dict())
        assert financials.rate_mode.value == result.rate_mode
        assert financials.interest_total == result.interest_total
        assert len(financials.ledger) == len(result.ledger)
