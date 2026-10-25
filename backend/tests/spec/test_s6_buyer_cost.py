"""Architecture 6.4: the buyer-cost lines - the 31 March checkpoint (section 11).

Section 11 asks for "31 March checkpoint with partial payment before it". The
three lines stay separate and are never summed (6.4, golden rule 8), the tax
timing effect is never added to interest, and the gated pressure points stay
off while OQ-8 is open.
"""

from decimal import Decimal

from backend.tests.spec.helpers import (
    SECTION_43BH_FIRST_FY,
    base_request,
    const,
    evaluate_ok,
    unverified_keys_mentioned,
)

DELIVERY = "2026-04-10"  # no agreement -> due 2026-04-25, appointed 2026-04-26
PAYMENT_DATE = "2026-05-10"
CHECKPOINT = "2027-03-31"
CALC = "2027-04-10"


def test_43bh_checkpoint_after_a_partial_payment(client):
    """Section 11: a 31 March checkpoint with a partial payment before it.

    Hand calculation (architecture 6.4, request inputs: tax 30%, cost of
    capital 12%, 1.00 year deferred; appropriation pinned to INTEREST_FIRST):
      principal 365000.00, rate 3 x 5.50 = 16.50%
      appointed day 2026-04-26; accrual to the payment date
        2026-04-26 -> 2026-05-10 = 14 days: 365000 x 16.50% x 14/365 = 2310.00
      payment 100000.00 on 2026-05-10, INTEREST_FIRST:
        2310.00 to interest, 100000 - 2310 = 97690.00 to principal
        principal outstanding = 365000.00 - 97690.00 = 267310.00
      checkpoint 2027-03-31 (inside [due 2026-04-25, calc 2027-04-10], and the
      FY 2026-27 sits on or after the configured section_43bh_first_fy):
        unpaid principal  = 267310.00
        tax timing effect = 267310.00 x 30%   = 80193.00
        deferral cost     = 80193.00 x 12% x 1.00 = 9623.16
      deferral.applies = True, inputs echoed back from the request.
    """
    assert SECTION_43BH_FIRST_FY, "the first s.43B(h) year comes from config (V3)"
    assert const("gated_features")["gst_itc_180d"] is False, "OQ-8 keeps gating off"

    body = _evaluate(client)
    buyer_cost = body["buyer_cost"]
    assert buyer_cost is not None, "an eligible case must report buyer cost (8.3)"

    deferral = buyer_cost["deferral"]
    assert deferral["applies"] is True, "a checkpoint falls inside the window"
    assert len(deferral["checkpoints"]) == 1, "only 2027-03-31 sits in the window"
    checkpoint = deferral["checkpoints"][0]
    assert checkpoint["fy_end"] == CHECKPOINT
    assert_amount(checkpoint["unpaid_principal"], "267310.00", "unpaid principal")
    assert_amount(checkpoint["tax_timing_effect"], "80193.00", "tax timing effect")
    assert_amount(deferral["deferral_cost"], "9623.16", "deferral cost")
    assert Decimal(deferral["inputs"]["cost_of_capital_pct"]) == Decimal("12")
    assert Decimal(deferral["inputs"]["years_deferred"]) == Decimal("1.00")

    # The partial payment before the checkpoint is what the unpaid figure shows.
    assert_amount(body["financials"]["principal_outstanding"], "267310.00", "principal")


def test_three_buyer_cost_lines_are_reported_separately(client):
    """6.4 and golden rule 8: three lines, never one total."""
    body = _evaluate(client)
    buyer_cost = body["buyer_cost"]
    assert set(buyer_cost) >= {"permanent_loss", "deferral", "disclosure_flags"}
    permanent = buyer_cost["permanent_loss"]
    assert (
        Decimal(permanent["interest_non_deductible"]) > 0
    ), "accrued interest is the loss"
    assert (
        Decimal(permanent["pretax_equivalent_rate_pct"]) > 0
    ), "the pre-tax rate exists"
    assert buyer_cost[
        "disclosure_flags"
    ], "6.4: the s.22 disclosure line is always reported"


def test_gated_pressure_points_stay_off_while_oq_8_is_open(client):
    """OQ-8 documented default: gated_features false -> no pressure points."""
    body = _evaluate(client)
    assert (
        body["buyer_cost"]["other_pressure_points"] == []
    ), "no gated feature is enabled, so nothing may be emitted (6.4)"
    assert "gated_features" in unverified_keys_mentioned(
        body
    ), "the gate itself is unverified (V9) and must be flagged while read (5)"


def _evaluate(client) -> dict:
    return evaluate_ok(
        client,
        base_request(
            transaction={
                "supply_date": DELIVERY,
                "delivery_date": DELIVERY,
                "calculation_date": CALC,
            },
            part_payments=[
                {"date": PAYMENT_DATE, "amount": "100000.00", "reference": None}
            ],
            config_overrides={"appropriation_mode": "INTEREST_FIRST"},
        ),
    )


def assert_amount(actual, expected, label: str) -> None:
    assert Decimal(str(actual)) == Decimal(
        expected
    ), f"{label}: expected {expected}, got {actual}"
