"""Architecture 6.5: limitation - what restarts the clock, and OQ-6's default.

Section 11's case here: "limitation restart by signed confirmation but not by
WhatsApp". The configured period is null (V7 uncaptured, OQ-6), so the expiry
must read UNKNOWN rather than "plenty of time" - the engine's own wording for
that distinction is exactly what this file pins down.
"""

from backend.tests.spec.helpers import (
    LIMITATION_YEARS,
    base_request,
    evaluate_ok,
    unverified_keys_mentioned,
)

DELIVERY = "2026-06-01"  # no written agreement -> due 2026-06-16 (delivery + 15)
CALC = "2026-06-27"

BASE = {
    "transaction": {
        "supply_date": DELIVERY,
        "delivery_date": DELIVERY,
        "calculation_date": CALC,
    }
}


def _events_by_kind(body: dict) -> dict:
    return {event["kind"]: event for event in body["limitation"]["events"]}


def test_limitation_default_is_unknown_and_flagged(client):
    """OQ-6 documented default: null period -> UNKNOWN, never a comfort date.

    Config: limitation_years is null (V7 uncaptured), so expiry must be null
    and status UNKNOWN, and the unverified/null constant must surface a
    warning naming it (architecture 5).
    """
    assert LIMITATION_YEARS is None, "the shipped config keeps OQ-6 open"
    body = evaluate_ok(client, base_request(**BASE))
    limitation = body["limitation"]
    assert limitation["expiry"] is None, "no period, no expiry date (6.5)"
    assert (
        limitation["status"] == "UNKNOWN"
    ), "UNKNOWN means the inputs do not support a date, not that time remains"
    assert "limitation_years" in unverified_keys_mentioned(
        body
    ), "the null period must be named in a warning rather than left silent (5)"


def test_signed_confirmation_and_part_payment_restart_the_clock(client):
    """Section 11: signed confirmation restarts, WhatsApp does not (6.5).

    Hand set-up:
      delivery 2026-06-01 -> due 2026-06-16 (anchor), calc 2026-06-27
      acknowledgments:
        2026-06-20 SIGNED_BALANCE_CONFIRMATION, signed   -> qualifies (6.5)
        2026-06-22 WHATSAPP_PROMISE,          unsigned -> never restarts (6.5)
        2026-06-24 PART_PAYMENT,              signed   -> qualifies (6.5)
      Each acknowledgment's `restarts_clock` flag must say exactly that; the
      expiry date itself stays UNKNOWN because the period is still uncaptured.
    """
    body = evaluate_ok(
        client,
        base_request(
            **BASE,
            acknowledgments=[
                {
                    "date": "2026-06-20",
                    "kind": "SIGNED_BALANCE_CONFIRMATION",
                    "is_signed": True,
                    "source_ref": "spec-signed-confirmation",
                },
                {
                    "date": "2026-06-22",
                    "kind": "WHATSAPP_PROMISE",
                    "is_signed": False,
                    "source_ref": "spec-chat",
                },
                {
                    "date": "2026-06-24",
                    "kind": "PART_PAYMENT",
                    "is_signed": True,
                    "source_ref": "spec-part-payment",
                },
            ],
        ),
    )
    events = _events_by_kind(body)
    assert (
        events["SIGNED_BALANCE_CONFIRMATION"]["restarts_clock"] is True
    ), "a signed balance confirmation qualifies (6.5)"
    assert (
        events["PART_PAYMENT"]["restarts_clock"] is True
    ), "a part-payment qualifies (6.5)"
    assert (
        events["WHATSAPP_PROMISE"]["restarts_clock"] is False
    ), "a chat promise must be recorded but never restart the clock (6.5)"
    assert (
        body["limitation"]["status"] == "UNKNOWN"
    ), "the flags are decided; the expiry date still needs V7 (OQ-6)"


def test_unsigned_confirmation_does_not_restart_the_clock(client):
    """6.5 requires is_signed *and* a qualifying kind: unsigned does not count.

    Same dates as above, but the balance confirmation arrives unsigned.
    """
    body = evaluate_ok(
        client,
        base_request(
            **BASE,
            acknowledgments=[
                {
                    "date": "2026-06-20",
                    "kind": "SIGNED_BALANCE_CONFIRMATION",
                    "is_signed": False,
                    "source_ref": "spec-unsigned",
                }
            ],
        ),
    )
    events = _events_by_kind(body)
    assert (
        events["SIGNED_BALANCE_CONFIRMATION"]["restarts_clock"] is False
    ), "6.5: the restart needs is_signed true as well as a qualifying kind"
