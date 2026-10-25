"""Architecture 6.3: the interest ledger, its rests, its rows and its rates.

Section 11 cases covered here: leap-year February dates and month-end rests,
payment before the appointed day, payment larger than the balance, payment on
a rest date, two payments, a bank-rate change mid-delay under **both** rate
modes, and epoch boundary dates.

Each test opens with the hand calculation the assertion checks - principal,
rate (multiplier x Bank Rate, both read from the config), rest dates, day
counts and the expected closing balances - so a reader can redo the sums with
a calculator and no source code.
"""

from decimal import Decimal

from backend.tests.spec.helpers import (
    APPROPRIATION_MODE_DEFAULT,
    DAY_COUNT,
    RATE_MODE_DEFAULT,
    assert_ledger_consistent,
    assumptions_blob,
    bank_rate_on,
    base_request,
    days_between,
    evaluate_ok,
    month_end_step,
    rupees,
    simple_interest,
    statutory_rate_on,
    warning_codes,
)

PRINCIPAL = "365000.00"  # divides by the 365-day day count exactly: 1000/day
# The configured epochs: 5.50 from 2026-04-01, 5.75 from 2026-10-07 (V1).
RATE_EARLY = statutory_rate_on("2026-06-01")  # 3 x 5.50 = 16.50
RATE_LATE = statutory_rate_on("2026-11-01")  # 3 x 5.75 = 17.25
BOUNDARY = "2026-10-07"  # the second configured epoch's first day


def test_leap_year_february_rest_and_month_end_clamp(client):
    """Section 11: leap-year February and month-end rests.

    Hand calculation (architecture 6.3):
      principal 365000.00, statutory rate = 3 x 5.75 = 17.25%, day count 365
      delivery 2028-01-15, no written agreement -> due 2028-01-30,
        appointed day 2028-01-31
      rest 1 = 2028-01-31 + 1 month = 2028-02-29  (leap February, clamped)
      period 1: 2028-01-31 -> 2028-02-29 = 29 days
        365000 x 17.25% x 29/365 = 5002.50
      balance after the rest = 365000.00 + 5002.50 = 370002.50
      period 2 (stub): 2028-02-29 -> 2028-03-01 = 1 day
        370002.50 x 17.25% x 1/365 = 174.864... -> 174.86 (half-up)
      interest total = 5002.50 + 174.86 = 5177.36
      total claim    = 365000.00 + 5177.36 = 370177.36
    """
    assert RATE_LATE == Decimal("17.25"), "config: 3 x 5.75 from 2026-10-07"
    appointed = "2028-01-31"
    rest = month_end_step(appointed, 1)
    assert rest == "2028-02-29", "2028-01-31 + 1 month clamps to leap-day February"

    body = evaluate_ok(
        client,
        base_request(
            transaction={
                "supply_date": "2028-01-15",
                "delivery_date": "2028-01-15",
                "written_credit_days": None,
                "calculation_date": "2028-03-01",
            }
        ),
    )
    financials = body["financials"]
    assert body["timeline"]["appointed_day"] == appointed

    period_1 = simple_interest(PRINCIPAL, RATE_LATE, days_between(appointed, rest))
    assert period_1 == Decimal("5002.50")
    balance_after_rest = Decimal(PRINCIPAL) + period_1
    period_2 = simple_interest(
        balance_after_rest, RATE_LATE, days_between(rest, "2028-03-01")
    )
    assert period_2 == Decimal("174.86")
    expected_total = period_1 + period_2
    assert expected_total == Decimal("5177.36")

    assert_amount(financials["interest_total"], expected_total, "interest total")
    assert_amount(
        financials["total_claim"],
        Decimal(PRINCIPAL) + expected_total,
        "total claim",
    )
    assert (
        financials["ledger"][0]["from"] == appointed
    ), "the ledger starts at the appointed day"
    assert financials["ledger"][0]["to"] == rest, "first row ends on the leap-day rest"
    assert (
        financials["ledger"][-1]["to"] == "2028-03-01"
    ), "last row ends on the calculation date"
    assert_ledger_consistent(financials, first_from=appointed)


def test_payment_on_the_rest_day_that_is_also_the_calculation_date(client):
    """Section 11, the sharpest corner: payment on a rest date, evaluated that day.

    Hand calculation (architecture 6.3, OQ-3):
      principal 365000.00, rate = 3 x 5.50 = 16.50%
      delivery 2026-05-11, no agreement -> due 2026-05-26, appointed 2026-05-27
      rest 1 = 2026-06-27, payment of 100000 on that same day, calc same day
      period: 2026-05-27 -> 2026-06-27 = 31 days
        365000 x 16.50% x 31/365 = 5115.00   (accrued once, not twice)
      appropriation INTEREST_FIRST: the payment clears 5115.00 of interest,
        then 94885.00 of principal
      principal outstanding = 365000.00 - 94885.00 = 270115.00
      interest outstanding  = 0.00
      total claim           = 270115.00
      (6.3: accrue to the payment date, capitalise, apply, restart from there.)
      Outcome recorded in docs/test-oracles.md.
    """
    appointed = "2026-05-27"
    rest = month_end_step(appointed, 1)
    assert rest == "2026-06-27"
    expected_interest = simple_interest(
        PRINCIPAL, RATE_EARLY, days_between(appointed, rest)
    )
    assert expected_interest == Decimal("5115.00")
    principal_part = Decimal("100000.00") - expected_interest
    expected_principal = Decimal(PRINCIPAL) - principal_part
    assert expected_principal == Decimal("270115.00")

    body = evaluate_ok(
        client,
        base_request(
            transaction={
                "supply_date": "2026-05-11",
                "delivery_date": "2026-05-11",
                "calculation_date": rest,
            },
            part_payments=[
                {"date": rest, "amount": "100000.00", "reference": "spec-pay"}
            ],
            config_overrides={"appropriation_mode": "INTEREST_FIRST"},
        ),
    )
    financials = body["financials"]
    assert financials["appropriation_mode"] == "INTEREST_FIRST"
    assert_amount(
        financials["interest_total"], expected_interest, "interest to the rest day"
    )
    assert_amount(
        financials["principal_outstanding"],
        expected_principal,
        "principal after payment",
    )
    assert_amount(
        financials["interest_outstanding"], Decimal("0.00"), "interest fully absorbed"
    )
    assert_amount(
        financials["total_claim"], expected_principal, "total claim after payment"
    )
    assert_ledger_consistent(financials, first_from=appointed)
    assert any(
        rest in row["from"] or rest in row["to"] for row in financials["ledger"]
    ), "the payment/rest day must appear in the ledger"
    assert "PAYMENT_DATE_IS_REST_BOUNDARY" in assumptions_blob(
        body
    ), "the mid-period convention is an open rule (OQ-3) and must be stated"


def test_payment_on_a_rest_date_with_a_later_calculation_date(client):
    """Section 11 again: the same rest-day payment, evaluated a week later.

    Hand calculation (architecture 6.3, OQ-3):
      period to the rest: 2026-05-27 -> 2026-06-27 = 31 days = 5115.00
      payment 100000 on the rest day, INTEREST_FIRST:
        5115.00 to interest, 94885.00 to principal
        principal outstanding = 365000.00 - 94885.00 = 270115.00
      the cycle restarts from the rest day; stub 2026-06-27 -> 2026-07-05
      = 8 days: 270115.00 x 16.50% x 8/365 = 976.85 (half-up)
      interest outstanding = 976.85, total claim = 271091.85
    """
    appointed = "2026-05-27"
    rest = month_end_step(appointed, 1)
    expected_interest = simple_interest(
        PRINCIPAL, RATE_EARLY, days_between(appointed, rest)
    )
    assert expected_interest == Decimal("5115.00")
    expected_principal = Decimal(PRINCIPAL) - (Decimal("100000.00") - expected_interest)
    assert expected_principal == Decimal("270115.00")
    stub = simple_interest(
        expected_principal, RATE_EARLY, days_between(rest, "2026-07-05")
    )
    assert stub == Decimal("976.85")
    assert expected_principal + stub == Decimal("271091.85")

    body = evaluate_ok(
        client,
        base_request(
            transaction={
                "supply_date": "2026-05-11",
                "delivery_date": "2026-05-11",
                "calculation_date": "2026-07-05",
            },
            part_payments=[
                {"date": rest, "amount": "100000.00", "reference": "spec-pay"}
            ],
            config_overrides={"appropriation_mode": "INTEREST_FIRST"},
        ),
    )
    financials = body["financials"]
    assert_amount(
        financials["interest_total"], expected_interest + stub, "interest total"
    )
    assert_amount(
        financials["principal_outstanding"],
        expected_principal,
        "principal after payment",
    )
    assert_amount(financials["interest_outstanding"], stub, "stub after the payment")
    assert_amount(financials["total_claim"], expected_principal + stub, "total claim")
    paid = sum(Decimal(row["payment"]) for row in financials["ledger"])
    assert paid == Decimal("100000.00"), "the payment on the rest day must be applied"
    assert_ledger_consistent(financials, first_from=appointed)


def test_payment_before_the_appointed_day_reduces_principal_only(client):
    """Section 11: a payment before the delay starts.

    Hand calculation:
      delivery 2026-07-01, no agreement -> due 2026-07-16, appointed 2026-07-17
      payment 100000 on 2026-07-05, calc 2026-07-10 - both before the
      appointed day, so no interest has accrued yet:
        interest total = 0.00
        principal      = 365000.00 - 100000.00 = 265000.00
        total claim    = 265000.00
    """
    body = evaluate_ok(
        client,
        base_request(
            transaction={
                "supply_date": "2026-07-01",
                "delivery_date": "2026-07-01",
                "calculation_date": "2026-07-10",
            },
            part_payments=[
                {"date": "2026-07-05", "amount": "100000.00", "reference": None}
            ],
        ),
    )
    financials = body["financials"]
    assert_amount(
        financials["interest_total"], Decimal("0.00"), "nothing has accrued yet"
    )
    assert_amount(
        financials["principal_outstanding"], Decimal("265000.00"), "principal"
    )
    assert_amount(financials["total_claim"], Decimal("265000.00"), "total claim")
    assert_ledger_consistent(financials)
    paid = sum(Decimal(row["payment"]) for row in financials["ledger"])
    assert paid == Decimal(
        "100000.00"
    ), "the payment must be visible in the ledger rows"


def test_two_payments_are_both_applied(client):
    """Section 11: two payments, both before the appointed day.

    Hand calculation:
      delivery 2026-07-01 -> due 2026-07-16, appointed 2026-07-17
      payments 100000 (2026-07-05) + 50000 (2026-07-10), calc 2026-07-15 -
      both payments *and* the calculation date fall before the appointed day,
      so no interest has accrued yet:
        interest total = 0.00
        principal = 365000.00 - 150000.00 = 215000.00
        total claim = 215000.00
    """
    body = evaluate_ok(
        client,
        base_request(
            transaction={
                "supply_date": "2026-07-01",
                "delivery_date": "2026-07-01",
                "calculation_date": "2026-07-15",
            },
            part_payments=[
                {"date": "2026-07-05", "amount": "100000.00", "reference": "first"},
                {"date": "2026-07-10", "amount": "50000.00", "reference": "second"},
            ],
        ),
    )
    financials = body["financials"]
    assert_amount(financials["interest_total"], Decimal("0.00"), "interest")
    assert_amount(
        financials["principal_outstanding"], Decimal("215000.00"), "principal"
    )
    assert_amount(financials["total_claim"], Decimal("215000.00"), "total claim")
    paid = sum(Decimal(row["payment"]) for row in financials["ledger"])
    assert paid == Decimal("150000.00"), "both payments must be applied"
    assert_ledger_consistent(financials)


def test_payment_larger_than_the_balance_clears_and_warns(client):
    """Section 11: payment larger than the balance.

    Hand calculation (open-questions CQ-17: the payment column carries the
    amount *applied*, the excess goes into the OVERPAYMENT warning):
      delivery 2026-06-01 -> due 2026-06-16, appointed 2026-06-17
      payment 500000 on 2026-06-20, calc 2026-06-27
      accrual to the payment date: 2026-06-17 -> 2026-06-20 = 3 days
        365000 x 16.50% x 3/365 = 495.00
      claim at that moment = 365000.00 + 495.00 = 365495.00, so the payment
      applies 365495.00 and the excess 134505.00 is reported, not booked:
        principal outstanding = 0.00, interest outstanding = 0.00
        interest total (accrued) = 495.00, total claim = 0.00
    """
    appointed = "2026-06-17"
    expected_accrued = simple_interest(
        PRINCIPAL, RATE_EARLY, days_between(appointed, "2026-06-20")
    )
    assert expected_accrued == Decimal("495.00")
    claim_at_payment = Decimal(PRINCIPAL) + expected_accrued
    assert claim_at_payment == Decimal("365495.00")

    body = evaluate_ok(
        client,
        base_request(
            transaction={
                "supply_date": "2026-06-01",
                "delivery_date": "2026-06-01",
                "calculation_date": "2026-06-27",
            },
            part_payments=[
                {"date": "2026-06-20", "amount": "500000.00", "reference": None}
            ],
        ),
    )
    financials = body["financials"]
    assert_amount(
        financials["interest_total"], expected_accrued, "accrued before the payment"
    )
    assert_amount(financials["principal_outstanding"], Decimal("0.00"), "claim cleared")
    assert_amount(financials["interest_outstanding"], Decimal("0.00"), "claim cleared")
    assert_amount(financials["total_claim"], Decimal("0.00"), "nothing left to claim")
    applied = sum(Decimal(row["payment"]) for row in financials["ledger"])
    assert (
        applied == claim_at_payment
    ), "the ledger books what was applied, not what was offered"
    assert "OVERPAYMENT" in warning_codes(
        body
    ), "the excess must be reported (open-questions CQ-17)"
    assert_ledger_consistent(financials, first_from=appointed)


def test_bank_rate_change_mid_delay_under_floating(client):
    """Section 11: a mid-delay rate change in the default FLOATING mode.

    Hand calculation (architecture 6.3: FLOATING splits at epoch boundaries):
      principal 365000.00, delivery 2026-09-16, no agreement
        -> due 2026-10-01, appointed 2026-10-02, rest 1 = 2026-11-02,
        calc 2026-11-11
      the configured boundary 2026-10-07 sits inside period 1:
        2026-10-02 -> 2026-10-07 = 5 days at 16.50%
        2026-10-07 -> 2026-11-02 = 26 days at 17.25%
        365000 x (16.50% x 5 + 17.25% x 26) / 365 = 5310.00
      balance after the rest = 370310.00
      period 2: 2026-11-02 -> 2026-11-11 = 9 days at 17.25%
        370310.00 x 17.25% x 9/365 = 1575.09 (half-up)
      interest total = 5310.00 + 1575.09 = 6885.09
      total claim    = 365000.00 + 6885.09 = 371885.09
    """
    assert RATE_EARLY == Decimal("16.50") and RATE_LATE == Decimal("17.25")
    body = evaluate_ok(
        client,
        base_request(
            transaction={
                "supply_date": "2026-09-16",
                "delivery_date": "2026-09-16",
                "calculation_date": "2026-11-11",
            }
        ),
    )
    financials = body["financials"]
    assert financials["rate_mode"] == "FLOATING"
    assert RATE_MODE_DEFAULT == "FLOATING", "OQ-4 default is FLOATING (config)"
    assert "FLOATING" in assumptions_blob(
        body
    ), "the open default must be stated (OQ-4)"

    split_days = days_between("2026-10-02", BOUNDARY)
    assert split_days == 5
    period_1 = rupees(
        Decimal(PRINCIPAL)
        * (RATE_EARLY * split_days + RATE_LATE * days_between(BOUNDARY, "2026-11-02"))
        / Decimal("100")
        / Decimal(str(DAY_COUNT))
    )
    assert period_1 == Decimal("5310.00")
    period_2 = simple_interest(
        Decimal(PRINCIPAL) + period_1,
        RATE_LATE,
        days_between("2026-11-02", "2026-11-11"),
    )
    assert period_2 == Decimal("1575.09")
    expected_total = period_1 + period_2
    assert expected_total == Decimal("6885.09")

    assert_amount(financials["interest_total"], expected_total, "floating interest")
    assert_amount(
        financials["total_claim"], Decimal(PRINCIPAL) + expected_total, "total claim"
    )
    assert_ledger_consistent(financials, first_from="2026-10-02")

    statutory_rates = {
        segment["statutory_rate_pct"] for segment in financials["rate_segments"]
    }
    assert statutory_rates == {
        "16.50",
        "17.25",
    }, f"FLOATING must show both rates around the epoch, saw {statutory_rates}"
    boundaries = {segment["from"] for segment in financials["rate_segments"]} | {
        segment["to"] for segment in financials["rate_segments"]
    }
    assert BOUNDARY in boundaries, "a segment must break exactly on the epoch date"


def test_bank_rate_change_mid_delay_under_frozen(client):
    """Section 11 again: the same delay in FROZEN_AT_APPOINTED_DAY mode.

    Hand calculation (architecture 6.3: the appointed-day rate runs the whole
    period; appointed 2026-10-02 sits in the 5.50% epoch -> 16.50% throughout):
      period 1: 2026-10-02 -> 2026-11-02 = 31 days
        365000 x 16.50% x 31/365 = 5115.00
      balance after the rest = 370115.00
      period 2: 2026-11-02 -> 2026-11-11 = 9 days
        370115.00 x 16.50% x 9/365 = 1505.81 (half-up)
      interest total = 5115.00 + 1505.81 = 6620.81
      total claim    = 365000.00 + 6620.81 = 371620.81
      and every rate segment must read 16.50, whatever the segmentation is.
    """
    body = evaluate_ok(
        client,
        base_request(
            transaction={
                "supply_date": "2026-09-16",
                "delivery_date": "2026-09-16",
                "calculation_date": "2026-11-11",
            },
            config_overrides={"rate_mode": "FROZEN_AT_APPOINTED_DAY"},
        ),
    )
    financials = body["financials"]
    assert financials["rate_mode"] == "FROZEN_AT_APPOINTED_DAY"

    period_1 = simple_interest(
        PRINCIPAL, RATE_EARLY, days_between("2026-10-02", "2026-11-02")
    )
    assert period_1 == Decimal("5115.00")
    period_2 = simple_interest(
        Decimal(PRINCIPAL) + period_1,
        RATE_EARLY,
        days_between("2026-11-02", "2026-11-11"),
    )
    assert period_2 == Decimal("1505.81")
    expected_total = period_1 + period_2
    assert expected_total == Decimal("6620.81")

    assert_amount(financials["interest_total"], expected_total, "frozen interest")
    assert_amount(
        financials["total_claim"], Decimal(PRINCIPAL) + expected_total, "total claim"
    )
    assert_ledger_consistent(financials, first_from="2026-10-02")
    statutory = {
        segment["statutory_rate_pct"] for segment in financials["rate_segments"]
    }
    assert statutory == {"16.50"}, f"frozen mode must hold one rate, saw {statutory}"
    frozen_starts = {segment["from"] for segment in financials["rate_segments"]}
    assert (
        BOUNDARY not in frozen_starts
    ), "a frozen mode must not start a segment at the epoch"


def test_the_appointed_day_on_an_epoch_date_takes_the_new_rate(client):
    """Section 11: epoch boundary dates (half-open segments, open-questions).

    Hand calculation:
      delivery 2026-09-21 -> due 2026-10-06, appointed 2026-10-07 - the very
      day the second configured epoch starts, so the whole delay runs at
      3 x 5.75 = 17.25%
      period: 2026-10-07 -> 2026-10-20 = 13 days
        365000 x 17.25% x 13/365 = 2242.50
      total claim = 365000.00 + 2242.50 = 367242.50
    """
    body = evaluate_ok(
        client,
        base_request(
            transaction={
                "supply_date": "2026-09-21",
                "delivery_date": "2026-09-21",
                "calculation_date": "2026-10-20",
            }
        ),
    )
    financials = body["financials"]
    assert body["timeline"]["appointed_day"] == BOUNDARY
    first = financials["rate_segments"][0]
    assert first["from"] == BOUNDARY, "the segment starts on the appointed day"
    assert Decimal(first["bank_rate_pct"]) == bank_rate_on(
        BOUNDARY
    ), "the day an epoch starts carries that epoch's rate"
    assert Decimal(first["statutory_rate_pct"]) == RATE_LATE

    expected = simple_interest(
        PRINCIPAL, RATE_LATE, days_between(BOUNDARY, "2026-10-20")
    )
    assert expected == Decimal("2242.50")
    assert_amount(financials["interest_total"], expected, "interest at the new rate")
    assert_amount(
        financials["total_claim"], Decimal(PRINCIPAL) + expected, "total claim"
    )
    assert_ledger_consistent(financials, first_from=BOUNDARY)


def test_default_modes_are_announced_as_assumptions(client):
    """Open rules OQ-4 and the appropriation default must be visible (principle 6)."""
    body = evaluate_ok(
        client,
        base_request(
            transaction={
                "supply_date": "2026-06-01",
                "delivery_date": "2026-06-01",
                "calculation_date": "2026-06-27",
            }
        ),
    )
    blob = assumptions_blob(body)
    assert RATE_MODE_DEFAULT in blob, "the rate mode actually used must be named"
    assert APPROPRIATION_MODE_DEFAULT in blob, "so must the appropriation mode"
    unverified = " ".join(
        warning["text"]
        for warning in body["warnings"]
        if warning["code"] == "UNVERIFIED_CONSTANT"
    )
    assert (
        "bank_rate_epochs" in unverified
    ), "the Bank Rate epochs are unverified (V1) and must be flagged while used"


# ------------------------------------------------------------ assertions ----


def assert_amount(actual, expected, label: str) -> None:
    """Compare a response money string with the hand-computed Decimal."""
    assert Decimal(actual) == expected, f"{label}: expected {expected}, got {actual}"
