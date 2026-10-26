"""GSTIN format checks and PAN slicing. Format only, never a checksum claim."""

from __future__ import annotations

from backend.insights.identity import pan_from_gstin, validate_gstin

VALID = "27ABCDE1234F1Z5"


def test_a_valid_gstin_is_accepted_and_the_reason_says_format_only():
    result = validate_gstin(VALID)
    assert result["ok"] is True
    assert "format only" in result["reason"]
    assert "check digit is not verified" in result["reason"]


def test_lowercase_and_surrounding_whitespace_are_normalised():
    assert validate_gstin(f"  {VALID.lower()}  ")["ok"] is True


def test_the_pan_is_characters_3_to_12_one_indexed():
    assert pan_from_gstin(VALID) == "ABCDE1234F"
    assert pan_from_gstin(VALID)[0] == VALID[2]  # 1-indexed character 3
    assert pan_from_gstin(VALID)[-1] == VALID[11]  # 1-indexed character 12


def test_an_invalid_gstin_yields_no_pan():
    for value in (None, "", "29SYN000000000Z1", "27ABCDE1234F1Z", "27ABCDE1234F1A5"):
        assert pan_from_gstin(value) is None


def test_every_bad_shape_is_rejected_with_a_plain_reason():
    bad_values = [
        None,
        "",
        "   ",
        "29SYN000000000Z1",  # 16 characters, like the synthetic demo GSTINs
        "27ABCDE1234F1Z",  # 14 characters
        "2AABCDE1234F1Z5",  # state code is not two digits
        "27ABCDE1234F0Z5",  # entity code may not be zero
        "27ABCDE1234F1A5",  # the separator must be Z
        "27ABCDE1234F1Z-",  # check character is not base-36
    ]
    for value in bad_values:
        result = validate_gstin(value)
        assert result["ok"] is False, f"{value!r} should be invalid"
        assert isinstance(result["reason"], str) and result["reason"]
