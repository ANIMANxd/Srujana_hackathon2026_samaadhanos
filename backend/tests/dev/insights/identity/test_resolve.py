"""Resolution decisions: PAN grouping, provisional matching and warnings."""

from __future__ import annotations

from backend.insights.identity import CustomerRecord, resolve


def _pan_customer(*, gstins: tuple[str, ...] = ()) -> CustomerRecord:
    return CustomerRecord(
        id="c1",
        kind="PAN",
        pan="ABCDE1234F",
        display_name="Acme Industries Private Limited",
        gstins=gstins,
    )


def test_the_same_pan_in_two_states_is_one_customer():
    existing = [_pan_customer(gstins=("27ABCDE1234F1Z5",))]

    result = resolve("29ABCDE1234F1Z9", "Acme Industries Pvt. Ltd.", existing)

    assert result.customer_id == "c1"
    assert result.key == "PAN:ABCDE1234F"
    assert result.kind == "PAN"
    assert result.pan == "ABCDE1234F"
    assert result.create is False
    assert result.attach_gstin is True
    assert result.promote_to_pan is False
    assert result.warnings == ()


def test_a_new_valid_gstin_creates_a_pan_customer():
    result = resolve("27ABCDE1234F1Z5", "Acme Industries", [])

    assert result.customer_id is None
    assert result.create is True
    assert result.kind == "PAN"
    assert result.pan == "ABCDE1234F"
    assert result.key == "PAN:ABCDE1234F"
    assert result.attach_gstin is True
    assert result.gstin == "27ABCDE1234F1Z5"


def test_no_gstin_maps_to_a_provisional_by_normalised_name():
    existing = [
        CustomerRecord(
            id="p1",
            kind="PROVISIONAL",
            display_name="Acme Industries Pvt. Ltd.",
        )
    ]

    result = resolve(None, "ACME INDUSTRIES PRIVATE LIMITED", existing)

    assert result.customer_id == "p1"
    assert result.key == "NAME:ACME INDUSTRIES PRIVATE LIMITED"
    assert result.kind == "PROVISIONAL"
    assert result.create is False
    assert result.attach_gstin is False


def test_no_gstin_with_a_new_name_creates_a_provisional():
    result = resolve(None, "Beta Traders", [])

    assert result.create is True
    assert result.kind == "PROVISIONAL"
    assert result.pan is None
    assert result.key == "NAME:BETA TRADERS"
    assert result.attach_gstin is False


def test_an_invalid_gstin_is_a_provisional_with_a_warning():
    result = resolve("29SYN000000000Z1", "Sample Buyer Corp", [])

    assert result.kind == "PROVISIONAL"
    assert result.create is True
    assert result.gstin == "29SYN000000000Z1"
    assert result.attach_gstin is True, "the GSTIN is kept, the format is the warning"
    assert result.key == "NAME:SAMPLE BUYER CORP"
    assert result.warnings
    assert "format" in result.warnings[0]


def test_an_unnamed_case_without_a_gstin_gets_its_own_provisional():
    result = resolve(None, "", [])

    assert result.create is True
    assert result.key == "UNNAMED"
    assert result.display_name == "Unnamed buyer"
    assert any("No buyer name or GSTIN" in warning for warning in result.warnings)


def test_a_valid_gstin_on_a_provisional_row_promotes_it_to_pan():
    existing = [
        CustomerRecord(
            id="p1",
            kind="PROVISIONAL",
            display_name="Acme Industries",
            gstins=("27ABCDE1234F1Z5",),
        )
    ]

    result = resolve("27ABCDE1234F1Z5", "Acme Industries", existing)

    assert result.customer_id == "p1"
    assert result.kind == "PAN"
    assert result.pan == "ABCDE1234F"
    assert result.promote_to_pan is True
    assert result.create is False
    assert result.attach_gstin is False


def test_a_different_pan_is_never_reused_for_a_new_gstin():
    existing = [_pan_customer()]

    result = resolve("29ZZZZZ9999Z1Z5", "Acme Industries Private Limited", existing)

    assert result.customer_id is None, "a different PAN must never merge into c1"
    assert result.create is True
    assert result.pan == "ZZZZZ9999Z"
    assert result.key == "PAN:ZZZZZ9999Z"


def test_the_snapshot_is_frozen_and_is_not_mutated():
    existing = [_pan_customer(gstins=("27ABCDE1234F1Z5",))]
    before = tuple(existing)

    resolve("29ABCDE1234F1Z9", "Acme", existing)

    assert tuple(existing) == before
    assert existing[0].gstins == ("27ABCDE1234F1Z5",)
