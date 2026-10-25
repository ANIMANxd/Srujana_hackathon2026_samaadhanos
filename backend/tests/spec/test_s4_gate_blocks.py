"""Architecture 6.1: the gate - medium, trader and Silpi blocks (section 11).

The gate's status precedence (6.1) is BARRED_SILPI > EXCLUDED_TRADER >
EXCLUDED_MEDIUM > INSUFFICIENT_DATA > ELIGIBLE, ineligible results carry an
`alternative_remedy`, and their money blocks are absent with a BLOCK warning
rather than zeros (8.1, section 7: blocked cases are a first-class screen).

Silpi has an open rule (OQ-2): the config value is null, so the default case
must return *undecided* plus an OPEN_QUESTION warning - and the override path
is what a rehearsed judge manipulation uses.
"""

from backend.tests.spec.helpers import (
    SILPI_TEST_DATE,
    SMALL_CEILING_INVESTMENT_CR,
    TRADER_PREFIXES,
    base_request,
    evaluate_ok,
    warning_codes,
)

DEFAULT_NIC = "25990"  # manufacturing: outside every configured trading prefix


def _check(body: dict, check_id: str) -> dict:
    return next(c for c in body["jurisdiction"]["checks"] if c["id"] == check_id)


def test_medium_supplier_is_stopped_at_the_gate(client):
    """Section 11: the medium block, by reverse graduation.

    Hand calculation (config size_epochs, set from 2025-04-01):
      small investment ceiling = 25 crore
      investment 25 + 1 = 26 crore > 25 -> MEDIUM on the supply date
      -> enterprise_class fails, status EXCLUDED_MEDIUM,
      money blocks null, alternative_remedy present.
    """
    ceiling = SMALL_CEILING_INVESTMENT_CR
    over = str(ceiling + 1)
    body = evaluate_ok(client, base_request(supplier={"investment_cr": over}))

    jurisdiction = body["jurisdiction"]
    assert (
        jurisdiction["status"] == "EXCLUDED_MEDIUM"
    ), f"investment {over} cr is above the small ceiling {ceiling} cr (config)"
    assert jurisdiction["eligible"] is False
    assert _check(body, "enterprise_class")["passed"] is False
    assert body["financials"] is None, "an ineligible case must not compute money"
    assert body["buyer_cost"] is None
    assert any(
        w["severity"] == "BLOCK" for w in body["warnings"]
    ), "a null block must carry a BLOCK warning explaining why (8.1)"
    assert jurisdiction["alternative_remedy"], "6.1: ineligible results name a remedy"


def test_a_supplier_inside_the_ceiling_is_not_excluded_as_medium(client):
    """The same request just under the ceiling must not trip the medium block."""
    inside = str(SMALL_CEILING_INVESTMENT_CR - 1)  # 24 cr: small, not medium
    body = evaluate_ok(client, base_request(supplier={"investment_cr": inside}))
    assert (
        body["jurisdiction"]["status"] != "EXCLUDED_MEDIUM"
    ), f"investment {inside} cr sits below the configured small ceiling"
    failed = [c for c in body["jurisdiction"]["checks"] if c["passed"] is False]
    assert not any(c["id"] == "enterprise_class" for c in failed)


def test_trader_nic_division_is_excluded(client):
    """Section 11: the trader block, from the configured NIC prefixes (V5).

    The prefix comes from config (`trader_nic_prefixes`), so this test does
    not hard-code which divisions count as trading.
    """
    trading_nic = f"{TRADER_PREFIXES[0]}100"  # e.g. 45100: inside the first prefix
    body = evaluate_ok(
        client,
        base_request(supplier={"nic_codes": [trading_nic], "activity": "TRADING"}),
    )
    jurisdiction = body["jurisdiction"]
    assert jurisdiction["status"] == "EXCLUDED_TRADER"
    assert _check(body, "trader_exclusion")["passed"] is False
    assert body["financials"] is None
    assert any(w["severity"] == "BLOCK" for w in body["warnings"])
    assert jurisdiction["alternative_remedy"]

    control = evaluate_ok(client, base_request(case_id="spec-control"))
    assert (
        control["jurisdiction"]["status"] != "EXCLUDED_TRADER"
    ), f"the default NIC {DEFAULT_NIC} is outside the configured prefixes"


def test_silpi_default_is_undecided_and_flagged(client):
    """OQ-2 documented default: null config -> check undecided, never a guess.

    Architecture 6.1: if `silpi_test_date` is null the check returns null with
    an OPEN_QUESTION warning, "not a pass" - so the gate stays at
    INSUFFICIENT_DATA under the 6.1 precedence.
    """
    assert SILPI_TEST_DATE is None, "the shipped config keeps OQ-2 open"
    body = evaluate_ok(client, base_request())
    assert _check(body, "silpi_chronology")["passed"] is None, "not a pass, not a fail"
    assert "OPEN_QUESTION" in warning_codes(body), "6.1: the undecided check must warn"
    assert (
        body["jurisdiction"]["status"] == "INSUFFICIENT_DATA"
    ), "with one check undecided the gate cannot read ELIGIBLE (6.1 precedence)"


def test_silpi_block_when_the_udyam_date_falls_after_the_test_date(client):
    """Section 11: the Silpi block, via the documented override.

    Hand calculation (architecture 6.1, OQ-2):
      config silpi_test_date is null -> the test only decides under
      config_overrides.silpi_test_date = SUPPLY:
        supply 2026-06-01, Udyam registration 2026-06-15 (AFTER the supply)
        -> not registered when the supply happened -> BARRED_SILPI
      control: the same request with a 2020 registration (BEFORE the supply)
        -> every check passes -> ELIGIBLE (6.1 precedence).
    """
    late = evaluate_ok(
        client,
        base_request(
            supplier={"udyam_registration_date": "2026-06-15"},
            transaction={
                "supply_date": "2026-06-01",
                "delivery_date": "2026-06-01",
                "calculation_date": "2026-06-27",
            },
            config_overrides={"silpi_test_date": "SUPPLY"},
        ),
    )
    assert (
        late["jurisdiction"]["status"] == "BARRED_SILPI"
    ), "registered after the supply date: the Silpi check must bar (6.1, section 11)"
    assert _check(late, "silpi_chronology")["passed"] is False
    assert late["financials"] is None

    early = evaluate_ok(
        client,
        base_request(
            case_id="spec-silpi-early",
            supplier={"udyam_registration_date": "2020-01-01"},
            transaction={
                "supply_date": "2026-06-01",
                "delivery_date": "2026-06-01",
                "calculation_date": "2026-06-27",
            },
            config_overrides={"silpi_test_date": "SUPPLY"},
        ),
    )
    assert (
        early["jurisdiction"]["status"] == "ELIGIBLE"
    ), "registered before the supply date: every check passes (6.1 precedence)"
    assert _check(early, "silpi_chronology")["passed"] is True
