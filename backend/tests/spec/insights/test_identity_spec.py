"""Customer-book identity: PAN, name keys, and what must never merge.

Oracles are the identity rules as the task states them:

- a 15-character GSTIN carries its PAN in characters 3-12;
- two spellings of the same business name are the same key only when the words
  and the legal form agree after normalisation;
- the same PAN is one legal entity (so two state GSTINs are one customer), and
  two different PANs are never merged automatically - at most a group link is
  suggested.
"""

from __future__ import annotations

from backend.insights.identity import normalize_name, pan_from_gstin
from backend.tests.spec.insights.helpers import (
    GSTIN_KA_ACME,
    GSTIN_MH_OTHER,
    GSTIN_TN_ACME,
    book,
    create_case,
)


def test_pan_is_characters_3_to_12_of_a_valid_gstin():
    """`29ABCDE1234F1Z5`: 2 digits, then PAN at 3-12, then the entity code, Z, check."""
    assert pan_from_gstin("29ABCDE1234F1Z5") == "ABCDE1234F"
    # Trimmed and upper-cased before the format check, so a pasted value works.
    assert pan_from_gstin(" 33abcde1234f1z5 ") == "ABCDE1234F"


def test_a_value_that_is_not_a_gstin_gives_no_pan():
    """Never guess a PAN from a short, long or mis-shaped value."""
    assert pan_from_gstin("29ABCDE1234F") is None  # 12 characters, not 15
    assert pan_from_gstin("29ABCDE1234F1Z") is None  # 14 characters
    assert pan_from_gstin("ABCDE1234F") is None  # a bare PAN is not a GSTIN
    assert pan_from_gstin(None) is None
    assert pan_from_gstin("") is None


def test_the_same_name_spelt_two_ways_has_one_key():
    """Legal-form words and punctuation are spelling, not identity."""
    assert normalize_name("Acme Industries Pvt. Ltd.") == normalize_name(
        "ACME INDUSTRIES PRIVATE LIMITED"
    )
    assert normalize_name("M/s Ganga & Sons") == normalize_name("GANGA AND SONS")
    assert normalize_name("Kaveri Auto Components Co.") == normalize_name(
        "Kaveri Auto Components Company"
    )


def test_a_missing_legal_form_or_a_different_word_is_a_different_key():
    """Similar is not the same: these pairs must stay apart."""
    assert normalize_name("Ganga Precision Works") != normalize_name(
        "Ganga Precision Works Private Limited"
    )
    assert normalize_name("Acme Industries Private Limited") != normalize_name(
        "Acme Industries Limited"
    )


def test_the_same_pan_in_two_states_is_one_customer(client):
    """29 (Karnataka) and 33 (Tamil Nadu) with the same PAN are one legal entity."""
    create_case(
        client,
        invoice_no="IDENT-KA-1",
        delivery="2026-06-01",
        buyer_name="Identity Buyer Private Limited",
        buyer_gstin=GSTIN_KA_ACME,
    )
    create_case(
        client,
        invoice_no="IDENT-TN-1",
        delivery="2026-06-02",
        buyer_name="Identity Buyer Private Limited",
        buyer_gstin=GSTIN_TN_ACME,
    )

    entries = book(client)["entries"]
    customers = [entry["customer"] for entry in entries if entry["kind"] == "CUSTOMER"]
    assert len(customers) == 1, "one PAN must produce one customer, not two"
    assert customers[0]["pan"] == "ABCDE1234F"
    assert customers[0]["gstins"] == sorted([GSTIN_KA_ACME, GSTIN_TN_ACME])


def test_different_pans_are_never_merged_automatically(client):
    """Two PANs with the same trading name stay two customers; a group is a choice."""
    first = create_case(
        client,
        invoice_no="IDENT-MH-1",
        delivery="2026-06-01",
        buyer_name="Acme Industries Private Limited",
        buyer_gstin=GSTIN_KA_ACME,
    )
    second = create_case(
        client,
        invoice_no="IDENT-MH-2",
        delivery="2026-06-02",
        buyer_name="Acme Industries Pvt Ltd",
        buyer_gstin=GSTIN_MH_OTHER,
    )
    assert first != second

    entries = book(client)["entries"]
    customers = [entry["customer"] for entry in entries if entry["kind"] == "CUSTOMER"]
    assert len(customers) == 2, "different PANs must never be merged automatically"
    assert {customer["pan"] for customer in customers} == {"ABCDE1234F", "PQRSX5678K"}
    assert all(customer["group_id"] is None for customer in customers)

    suggestions = client.get("/api/v1/customers/suggestions")
    assert suggestions.status_code == 200, suggestions.text[:400]
    kinds = {(item["kind"], frozenset((item["a"], item["b"]))) for item in suggestions.json()["suggestions"]}
    assert ("LINK_AS_GROUP", frozenset(c["id"] for c in customers)) in kinds, (
        "the owner should be offered a group link, never a merge"
    )


def test_a_case_with_no_gstin_is_its_own_provisional_customer(client):
    """No GSTIN means no PAN, so the buyer is provisional even with a familiar name."""
    create_case(
        client,
        invoice_no="IDENT-P-1",
        delivery="2026-06-01",
        buyer_name="Ganga Provisional Buyer Pvt Ltd",
    )
    entries = book(client)["entries"]
    customers = [entry["customer"] for entry in entries if entry["kind"] == "CUSTOMER"]
    assert len(customers) == 1
    assert customers[0]["kind"] == "PROVISIONAL"
    assert customers[0]["pan"] is None
