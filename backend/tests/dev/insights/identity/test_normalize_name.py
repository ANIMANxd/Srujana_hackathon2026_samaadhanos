"""Name normalisation: the "same business, different typing" cases."""

from __future__ import annotations

from backend.insights.identity import normalize_name


def test_private_and_limited_variants_normalise_equal():
    assert normalize_name("Acme Industries Pvt. Ltd.") == (
        "ACME INDUSTRIES PRIVATE LIMITED"
    )
    assert normalize_name("ACME INDUSTRIES PRIVATE LIMITED") == (
        "ACME INDUSTRIES PRIVATE LIMITED"
    )
    assert normalize_name("Acme Industries PVT LTD") == (
        "ACME INDUSTRIES PRIVATE LIMITED"
    )
    assert normalize_name("Acme Industries Limited") == "ACME INDUSTRIES LIMITED"


def test_ms_prefix_ampersand_and_company_are_mapped():
    assert normalize_name("M/s. Acme & Co.") == "ACME AND COMPANY"
    assert normalize_name("M/S ACME") == "ACME"
    assert normalize_name("M / S. Beta Trading Co.") == "BETA TRADING COMPANY"


def test_punctuation_and_whitespace_collapse():
    assert normalize_name("  Acme   Trading,  Co.  ") == "ACME TRADING COMPANY"
    assert normalize_name("Acme (India) Pvt. Ltd.") == "ACME INDIA PRIVATE LIMITED"


def test_legal_suffixes_are_not_stripped_so_similar_names_stay_distinct():
    # The suffixes are canonicalised, not removed: "Acme" and "Acme Pvt Ltd" are
    # different keys, which is why a close match is a suggestion, not a merge.
    assert normalize_name("Acme Pvt Ltd") != normalize_name("Acme Ltd")
    assert normalize_name("Acme Pvt Ltd") == "ACME PRIVATE LIMITED"
    assert normalize_name("Acme Ltd") == "ACME LIMITED"


def test_empty_and_non_string_inputs_are_empty():
    assert normalize_name(None) == ""
    assert normalize_name("") == ""
    assert normalize_name("   ") == ""
