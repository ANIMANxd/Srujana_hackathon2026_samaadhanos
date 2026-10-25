"""Malformed input must fail cleanly: the error envelope, never a stack trace.

Architecture 8.1: HTTP 422 for validation, 400 for rule violations, 500
otherwise - and the error model for every endpoint is
`{error: {code, message, field?}}`. A 500, an HTML traceback or a silent 200
that computes nonsense from an impossible input would all be findings; each
is recorded in docs/test-oracles.md if it happens.
"""

import pytest

from backend.tests.spec.helpers import base_request, post_evaluate

VALID_CODES = {"VALIDATION_ERROR", "RULE_VIOLATION"}


def assert_clean_refusal(response, label: str) -> dict:
    """A malformed input must come back as 400/422 with the contract envelope."""
    assert response.status_code in (400, 422), (
        f"{label}: expected 400 or 422, got {response.status_code}; "
        f"body was: {response.text[:400]}"
    )
    assert "Traceback" not in response.text, f"{label}: the response leaked a traceback"
    payload = response.json()
    error = payload.get("error")
    assert isinstance(
        error, dict
    ), f"{label}: response is not the error envelope: {payload}"
    assert (
        error.get("code") in VALID_CODES
    ), f"{label}: unexpected code {error.get('code')}"
    assert error.get("message"), f"{label}: the error carries no plain-English message"
    return payload


def test_negative_principal_is_refused(client):
    """A negative supply value is not a claim; it must not be computed."""
    response = post_evaluate(
        client, base_request(transaction={"principal": "-1000.00"})
    )
    assert_clean_refusal(response, "negative principal")


def test_calculation_date_before_delivery_is_refused(client):
    """A delay cannot end before the delivery it counts from."""
    response = post_evaluate(
        client,
        base_request(
            transaction={
                "supply_date": "2026-06-01",
                "delivery_date": "2026-06-01",
                "calculation_date": "2026-05-20",
            }
        ),
    )
    assert_clean_refusal(response, "calculation date before delivery")


def test_duplicate_payments_are_refused(client):
    """The same payment twice would double-count; it must be rejected."""
    duplicate = {"date": "2026-06-10", "amount": "50000.00", "reference": None}
    response = post_evaluate(
        client, base_request(part_payments=[duplicate, dict(duplicate)])
    )
    assert_clean_refusal(response, "duplicate payments")


def test_impossible_calendar_dates_are_refused(client):
    """30 February and month 13 are not dates; the schema must reject them."""
    impossible_day = post_evaluate(
        client, base_request(transaction={"invoice_date": "2026-02-30"})
    )
    assert_clean_refusal(impossible_day, "invoice date 2026-02-30")

    impossible_month = post_evaluate(
        client, base_request(transaction={"delivery_date": "2026-13-01"})
    )
    assert_clean_refusal(impossible_month, "delivery date 2026-13-01")


@pytest.mark.parametrize(
    "field,value,label",
    [
        ("written_credit_days", -20, "negative credit days"),
        ("years_deferred", "-1.00", "negative years deferred"),
    ],
)
def test_other_impossible_values_are_refused(client, field, value, label):
    """The same clean failure for the other impossible numbers in a transaction."""
    response = post_evaluate(client, base_request(transaction={field: value}))
    assert_clean_refusal(response, label)
