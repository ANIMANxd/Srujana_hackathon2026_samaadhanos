"""Invariants of the evaluation, whatever the inputs (AGENTS section 6 maths).

These are the properties a reader can check without knowing any statute:

1. the ledger's rows sum to `interest_total` and each row balances;
2. the total balance is identical under both appropriation modes;
3. interest never goes down when days pass and no payment intervenes;
4. moving the calculation date forward never reduces the total claim;
5. a larger principal never produces less interest;
6. the same request twice gives byte-identical output (no clock, no randomness);
7. shuffling the input lists (payments, objections) changes nothing.

Hand calculations are unnecessary here: every assertion is a comparison
between two runs of the public interface, which is exactly the point.
"""

from decimal import Decimal

from backend.tests.spec.helpers import (
    assert_ledger_consistent,
    base_request,
    evaluate_ok,
    post_evaluate,
)

DATES = {
    "supply_date": "2026-06-01",
    "delivery_date": "2026-06-01",
    "calculation_date": "2026-06-27",
}


def test_totals_equal_the_sum_of_ledger_rows(client):
    """Invariant 1 (section 11 too): rows chain, balance, and sum to the total."""
    body = evaluate_ok(client, base_request(transaction=dict(DATES)))
    financials = body["financials"]
    assert_ledger_consistent(financials)  # chain + row identity + sum
    assert Decimal(financials["total_claim"]) == (
        Decimal(financials["principal_outstanding"])
        + Decimal(financials["interest_outstanding"])
    ), "with no payment the claim is principal plus outstanding interest"


def test_total_balance_is_identical_across_appropriation_modes(client):
    """Invariant 2 (6.3): only the principal/interest split changes, never the total.

    Same request twice, one payment in the middle, modes flipped:
      INTEREST_FIRST    -> interest bucket absorbs the payment first
      PRINCIPAL_FIRST   -> principal absorbs it first
    The two buckets must differ while `total_claim` (and `interest_total`,
    which is the sum of the rows) stay equal.
    """
    request_args = dict(
        transaction=dict(DATES),
        part_payments=[{"date": "2026-06-20", "amount": "50000.00", "reference": None}],
    )
    interest_first = evaluate_ok(
        client,
        base_request(
            config_overrides={"appropriation_mode": "INTEREST_FIRST"}, **request_args
        ),
    )["financials"]
    principal_first = evaluate_ok(
        client,
        base_request(
            case_id="spec-invariants-pf",
            config_overrides={"appropriation_mode": "PRINCIPAL_FIRST"},
            **request_args,
        ),
    )["financials"]

    assert (
        interest_first["total_claim"] == principal_first["total_claim"]
    ), "6.3: the total balance is identical in both modes"
    assert (
        interest_first["interest_total"] == principal_first["interest_total"]
    ), "the rows accrue identically; only the split differs (6.3)"
    assert (
        interest_first["principal_outstanding"]
        != principal_first["principal_outstanding"]
    ), "the buckets should differ - otherwise the modes are indistinguishable"
    assert Decimal(interest_first["principal_outstanding"]) + Decimal(
        interest_first["interest_outstanding"]
    ) == Decimal(principal_first["principal_outstanding"]) + Decimal(
        principal_first["interest_outstanding"]
    ), "and both splits must still add up to the same balance"


def test_interest_is_monotonic_non_decreasing_as_days_pass(client):
    """Invariant 3: with no payment, more days can only add interest."""
    totals = []
    for calculation_date in ("2026-06-10", "2026-06-17", "2026-06-27"):
        body = evaluate_ok(
            client,
            base_request(
                transaction={
                    **DATES,
                    "calculation_date": calculation_date,
                }
            ),
        )
        totals.append(Decimal(body["financials"]["interest_total"]))
    assert totals == sorted(totals), f"interest went down as days passed: {totals}"


def test_moving_the_calculation_date_forward_never_reduces_the_claim(client):
    """Invariant 4: the total claim never falls by waiting."""
    claims = []
    for calculation_date in ("2026-06-10", "2026-06-17", "2026-06-27"):
        body = evaluate_ok(
            client,
            base_request(
                transaction={
                    **DATES,
                    "calculation_date": calculation_date,
                }
            ),
        )
        claims.append(Decimal(body["financials"]["total_claim"]))
    assert claims == sorted(claims), f"the claim shrank over time: {claims}"


def test_a_larger_principal_never_reduces_interest(client):
    """Invariant 5: same dates, double the principal -> at least as much interest."""
    small = evaluate_ok(client, base_request(transaction=dict(DATES)))["financials"]
    large = evaluate_ok(
        client,
        base_request(
            case_id="spec-invariants-big",
            transaction={**DATES, "principal": "730000.00"},
        ),
    )["financials"]
    assert Decimal(large["interest_total"]) >= Decimal(small["interest_total"]), (
        f"larger principal produced less interest: {large['interest_total']} "
        f"< {small['interest_total']}"
    )


def test_evaluate_is_idempotent(client):
    """Invariant 6: the same request twice, byte for byte (no clock, no randomness)."""
    request = base_request(transaction=dict(DATES))
    first = post_evaluate(client, request)
    second = post_evaluate(client, request)
    assert first.status_code == second.status_code == 200
    assert (
        first.content == second.content
    ), "two identical requests must answer identically"


def test_shuffling_part_payments_does_not_change_the_output(client):
    """Invariant 7a: payment order in the request must not matter."""
    payments = [
        {"date": "2026-06-05", "amount": "40000.00", "reference": "a"},
        {"date": "2026-06-15", "amount": "30000.00", "reference": "b"},
        {"date": "2026-06-22", "amount": "20000.00", "reference": "c"},
    ]
    forwards = evaluate_ok(
        client, base_request(transaction=dict(DATES), part_payments=payments)
    )
    backwards = evaluate_ok(
        client,
        base_request(
            transaction=dict(DATES),
            part_payments=list(reversed(payments)),
        ),
    )
    assert (
        forwards == backwards
    ), "the ledger must not depend on the order payments were listed"


def test_shuffling_objections_does_not_change_the_output(client):
    """Invariant 7b: objection order in the request must not matter.

    Two late objections (both after the window), listed forwards and
    backwards: acceptance is decided by the dates, not by the array order.
    """
    objections = [
        {
            "raised_date": "2026-05-26",
            "is_written": True,
            "description": "Late note one (synthetic)",
            "resolved_date": None,
        },
        {
            "raised_date": "2026-05-28",
            "is_written": True,
            "description": "Late note two (synthetic)",
            "resolved_date": None,
        },
    ]
    transaction = {
        "supply_date": "2026-05-10",
        "delivery_date": "2026-05-10",
        "calculation_date": "2026-06-20",
    }
    forwards = evaluate_ok(
        client, base_request(transaction=transaction, objections=objections)
    )
    backwards = evaluate_ok(
        client,
        base_request(
            transaction=transaction,
            objections=list(reversed(objections)),
        ),
    )
    assert (
        forwards == backwards
    ), "the outcome must not depend on the objection array order"
