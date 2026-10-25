"""Architecture 6.2: what anchors the clock, when the window ends, which period applies.

Section 11 of architecture.md lists the edge cases these cover: delivery later
than invoice, no delivery proof, objection on the last day of the window and
the day after, objection unresolved, written vs non-written objection, and
no agreement vs Net 90 vs Net 30.

Every date below is worked out in the test itself from the statute config
(`objection_window_days`, `no_agreement_days`, `credit_cap_days`) - the rules
under test are: acceptance anchors on **delivery** (never the invoice), the
window runs delivery + window days, due = acceptance + applied days, and the
appointed day is due + 1 (architecture 6.2).

Scenario dates keep every appointed day on or after the first configured Bank
Rate epoch (2026-04-01, V1 uncaptured): a delay priced before that has no rate
and the evaluation is refused.
"""

from backend.tests.spec.helpers import (
    CREDIT_CAP_DAYS,
    NO_AGREEMENT_DAYS,
    WINDOW_DAYS,
    add_days,
    assumptions_blob,
    base_request,
    evaluate_ok,
    unverified_keys_mentioned,
    warning_codes,
)

# "delivery later than invoice": the invoice is dated first, delivery follows.
INVOICE_EARLY = "2026-03-16"
DELIVERY_LATER = "2026-03-20"
# Window and due date both run from delivery:
#   window end   = 2026-03-20 + 15 = 2026-04-04
#   deemed acceptance = 2026-03-20 (delivery, no objection)
#   due date     = 2026-03-20 + 15 (no written agreement) = 2026-04-04
#   appointed day = 2026-04-05 (due + 1), inside the 5.50% epoch
EXPECTED_DUE = "2026-04-04"
EXPECTED_APPOINTED = "2026-04-05"


def test_delivery_later_than_invoice_anchors_on_delivery(client):
    """The clock follows delivery, not the invoice (6.2, section 11)."""
    body = evaluate_ok(
        client,
        base_request(
            transaction={
                "invoice_date": INVOICE_EARLY,
                "supply_date": DELIVERY_LATER,
                "delivery_date": DELIVERY_LATER,
                "calculation_date": "2026-04-15",
            }
        ),
    )
    timeline = body["timeline"]
    assert timeline["delivery_date"] == DELIVERY_LATER
    assert timeline["objection_window_end"] == add_days(DELIVERY_LATER, WINDOW_DAYS)
    assert timeline["objection_status"] == "DEEMED_ACCEPTANCE"
    assert (
        timeline["acceptance_date"] == DELIVERY_LATER
    ), "acceptance must anchor on delivery"
    assert (
        timeline["due_date"] == EXPECTED_DUE
    ), f"due = {DELIVERY_LATER} + {NO_AGREEMENT_DAYS} (no written agreement) = {EXPECTED_DUE}"
    assert timeline["appointed_day"] == EXPECTED_APPOINTED, "appointed day is due + 1"
    assert timeline["days_overdue"] is not None, "the delay has started"


def test_invoice_date_cannot_move_the_due_date(client):
    """Same delivery, two invoice dates -> the same due date (6.2).

    If the invoice date ever moved the clock, these two runs would differ;
    the assertion is on equality of due/appointed across the pair.
    """

    def due_for(invoice_date: str) -> tuple:
        body = evaluate_ok(
            client,
            base_request(
                transaction={
                    "invoice_date": invoice_date,
                    "supply_date": DELIVERY_LATER,
                    "delivery_date": DELIVERY_LATER,
                    "calculation_date": "2026-04-15",
                }
            ),
        )
        timeline = body["timeline"]
        return timeline["due_date"], timeline["appointed_day"]

    first = due_for("2026-01-01")
    second = due_for("2026-03-16")
    assert first == second == (EXPECTED_DUE, EXPECTED_APPOINTED)


def test_no_delivery_proof_leaves_the_clock_empty(client):
    """No delivery proof -> no acceptance, no due date, no money (6.2, section 7).

    Mirrors the documented blocked state: the timeline reports
    NO_DELIVERY_PROOF, and a null block must carry a reason in warnings[]
    rather than zeros (8.1).
    """
    body = evaluate_ok(
        client,
        base_request(
            transaction={"delivery_date": None, "calculation_date": "2026-07-15"},
            evidence={
                "items": [
                    {"kind": "PO", "present": True, "ref": "spec-po"},
                    {"kind": "INVOICE", "present": True, "ref": "spec-invoice"},
                    {"kind": "DELIVERY_PROOF", "present": False, "ref": None},
                    {"kind": "WHATSAPP", "present": False, "ref": None},
                    {"kind": "UDYAM", "present": True, "ref": "spec-udyam"},
                    {"kind": "GST_RETURN", "present": True, "ref": "spec-gst"},
                ]
            },
        ),
    )
    timeline = body["timeline"]
    assert timeline["objection_status"] == "NO_DELIVERY_PROOF"
    assert timeline["acceptance_date"] is None
    assert timeline["due_date"] is None
    assert timeline["appointed_day"] is None
    assert body["financials"] is None, "no due date, so no ledger can exist"
    assert body["warnings"], "a null block must carry a reason in warnings[]"
    readiness = body["evidence_readiness"]
    assert (
        4 in readiness["blocked_stages"]
    ), "missing delivery proof caps and blocks Stage 4 (6.2 and 6.6)"


def test_objection_on_the_last_window_day_moves_the_clock(client):
    """Written objection on the final window day qualifies (6.2, section 11).

    delivery 2026-05-10, window end = 2026-05-25 (delivery + 15):
      objection raised 2026-05-25 (inside), resolved 2026-05-26
      -> acceptance = 2026-05-26 (the resolution date)
      -> due = 2026-05-26 + 15 = 2026-06-10, appointed = 2026-06-11
    """
    delivery = "2026-05-10"
    body = evaluate_ok(
        client,
        base_request(
            transaction={
                "supply_date": delivery,
                "delivery_date": delivery,
                "calculation_date": "2026-06-20",
            },
            objections=[
                {
                    "raised_date": "2026-05-25",
                    "is_written": True,
                    "description": "Two cartons short (synthetic)",
                    "resolved_date": "2026-05-26",
                }
            ],
        ),
    )
    timeline = body["timeline"]
    assert timeline["objection_window_end"] == "2026-05-25"
    assert timeline["objection_status"] == "RESOLVED"
    assert (
        timeline["acceptance_date"] == "2026-05-26"
    ), "a qualifying objection moves acceptance"
    assert timeline["due_date"] == "2026-06-10", "due = 2026-05-26 + 15"
    assert timeline["appointed_day"] == "2026-06-11"
    assert timeline["late_complaints"] == [], "an in-window objection is not late"


def test_objection_the_day_after_the_window_is_recorded_not_counted(client):
    """Raised one day late: recorded in late_complaints, clock unmoved (6.2).

    delivery 2026-05-10, window end 2026-05-25:
      objection raised 2026-05-26 (outside) -> deemed acceptance stays
      acceptance = 2026-05-10, due = 2026-05-25, appointed = 2026-05-26,
      and the complaint is listed with a reason.
    """
    delivery = "2026-05-10"
    body = evaluate_ok(
        client,
        base_request(
            transaction={
                "supply_date": delivery,
                "delivery_date": delivery,
                "calculation_date": "2026-06-20",
            },
            objections=[
                {
                    "raised_date": "2026-05-26",
                    "is_written": True,
                    "description": "Now we say the boxes were short (synthetic)",
                    "resolved_date": None,
                }
            ],
        ),
    )
    timeline = body["timeline"]
    assert timeline["objection_status"] == "DEEMED_ACCEPTANCE"
    assert (
        timeline["acceptance_date"] == delivery
    ), "a late objection must not move acceptance"
    assert timeline["due_date"] == "2026-05-25"
    assert timeline["appointed_day"] == "2026-05-26"
    assert len(timeline["late_complaints"]) == 1, "it must still be recorded"
    assert timeline["late_complaints"][0]["date"] == "2026-05-26"
    assert timeline["late_complaints"][0]["reason"], "with a plain-English reason"


def test_unwritten_objection_does_not_move_the_clock(client):
    """Only *written* objections qualify (6.2, section 11).

    delivery 2026-05-10, a verbal complaint on 2026-05-15 (inside the window)
    -> acceptance stays on delivery: 2026-05-10, due 2026-05-25.
    """
    delivery = "2026-05-10"
    body = evaluate_ok(
        client,
        base_request(
            transaction={
                "supply_date": delivery,
                "delivery_date": delivery,
                "calculation_date": "2026-06-20",
            },
            objections=[
                {
                    "raised_date": "2026-05-15",
                    "is_written": False,
                    "description": "A call, nothing in writing (synthetic)",
                    "resolved_date": None,
                }
            ],
        ),
    )
    timeline = body["timeline"]
    assert timeline["objection_status"] == "DEEMED_ACCEPTANCE"
    assert timeline["acceptance_date"] == delivery
    assert timeline["due_date"] == "2026-05-25"
    assert (
        len(timeline["late_complaints"]) == 1
    ), "an unwritten objection is listed in late_complaints (6.2)"


def test_unresolved_written_objection_holds_the_clock(client):
    """Open objection inside the window -> PENDING_RESOLUTION, nothing computed.

    delivery 2026-05-10, written objection 2026-05-15 never resolved:
    acceptance cannot be fixed yet, so acceptance/due/appointed stay null and
    the money block is absent with a reason in warnings[] (8.1).
    """
    delivery = "2026-05-10"
    body = evaluate_ok(
        client,
        base_request(
            transaction={
                "supply_date": delivery,
                "delivery_date": delivery,
                "calculation_date": "2026-06-20",
            },
            objections=[
                {
                    "raised_date": "2026-05-15",
                    "is_written": True,
                    "description": "Quality dispute still open (synthetic)",
                    "resolved_date": None,
                }
            ],
        ),
    )
    timeline = body["timeline"]
    assert timeline["objection_status"] == "PENDING_RESOLUTION"
    assert timeline["acceptance_date"] is None
    assert timeline["due_date"] is None
    assert timeline["appointed_day"] is None
    assert body["financials"] is None
    assert "PENDING_RESOLUTION" in warning_codes(body), (
        "open-questions CQ-11: an unresolved objection leaves acceptance null "
        "with a PENDING_RESOLUTION warning"
    )


def test_no_written_agreement_uses_the_configured_period(client):
    """No written terms -> the configured no_agreement_days (6.2, OQ-5).

    delivery 2026-06-01: acceptance 2026-06-01, due = +15 = 2026-06-16,
    appointed 2026-06-17. The period comes from config, not from a literal.
    """
    body = evaluate_ok(
        client,
        base_request(
            transaction={
                "supply_date": "2026-06-01",
                "delivery_date": "2026-06-01",
                "written_credit_days": None,
                "calculation_date": "2026-06-27",
            }
        ),
    )
    timeline = body["timeline"]
    assert timeline["agreed_days"] is None
    assert timeline["applied_days"] == NO_AGREEMENT_DAYS
    assert timeline["clamped"] is False
    assert timeline["due_date"] == "2026-06-16"
    assert timeline["appointed_day"] == "2026-06-17"


def test_net_90_is_clamped_to_the_credit_cap(client):
    """A 90-day term is capped at the configured 45 days (6.2, section 7 trap 2).

    delivery 2026-06-01, agreed 90 -> applied = credit_cap_days = 45,
    clamped = True, due = 2026-06-01 + 45 = 2026-07-16, appointed 2026-07-17.
    There are no regimes: the cap applies to every supply.
    """
    body = evaluate_ok(
        client,
        base_request(
            transaction={
                "supply_date": "2026-06-01",
                "delivery_date": "2026-06-01",
                "written_credit_days": 90,
                "calculation_date": "2026-07-20",
            }
        ),
    )
    timeline = body["timeline"]
    assert timeline["agreed_days"] == 90, "the agreement itself is reported"
    assert timeline["applied_days"] == CREDIT_CAP_DAYS, "but the cap is what applies"
    assert timeline["clamped"] is True, "the clamp must be visible (6.2)"
    assert timeline["due_date"] == "2026-07-16", "due = 2026-06-01 + 45 (capped)"
    assert timeline["appointed_day"] == "2026-07-17"
    assert "OQ-5" in assumptions_blob(
        body
    ), "what counts as a written agreement is open (OQ-5) and must be stated"
    assert "credit_cap_days" in unverified_keys_mentioned(
        body
    ), "architecture 5: an unverified constant the computation uses must warn"


def test_net_30_applies_exactly_as_agreed(client):
    """Inside the cap -> the agreed period applies untouched (6.2).

    delivery 2026-06-01, agreed 30 (30 < 45): due = 2026-06-01 + 30 =
    2026-07-01, appointed 2026-07-02, no clamp.
    """
    body = evaluate_ok(
        client,
        base_request(
            transaction={
                "supply_date": "2026-06-01",
                "delivery_date": "2026-06-01",
                "written_credit_days": 30,
                "calculation_date": "2026-07-20",
            }
        ),
    )
    timeline = body["timeline"]
    assert timeline["agreed_days"] == 30
    assert timeline["applied_days"] == 30
    assert timeline["clamped"] is False
    assert timeline["due_date"] == "2026-07-01"
    assert timeline["appointed_day"] == "2026-07-02"


def test_objection_window_is_read_from_config_and_flagged(client):
    """OQ-1 default: window = configured days from delivery, and flagged.

    The window value itself is V2 and unverified, so the response must warn
    (architecture 5) while still applying 15 days.
    """
    delivery = "2026-05-10"
    body = evaluate_ok(
        client,
        base_request(
            transaction={
                "supply_date": delivery,
                "delivery_date": delivery,
                "calculation_date": "2026-06-20",
            }
        ),
    )
    assert body["timeline"]["objection_window_end"] == add_days(delivery, WINDOW_DAYS)
    assert "objection_window_days" in unverified_keys_mentioned(
        body
    ), "the window is unverified (V2/OQ-1); silently using it would hide it"
