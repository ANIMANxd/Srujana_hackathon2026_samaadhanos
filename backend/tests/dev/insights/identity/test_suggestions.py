"""Suggestion maths: ATTACH, LINK_AS_GROUP, exclusions and the threshold."""

from __future__ import annotations

from dataclasses import replace

import pytest

from backend.insights.identity import CustomerRecord, suggestions


def _provisional(**overrides) -> CustomerRecord:
    values = {
        "id": "p1",
        "kind": "PROVISIONAL",
        "display_name": "Acme Industries Pvt. Ltd.",
    }
    values.update(overrides)
    return CustomerRecord(**values)


def _pan(customer_id: str = "c1", **overrides) -> CustomerRecord:
    values = {
        "id": customer_id,
        "kind": "PAN",
        "pan": "ABCDE1234F",
        "display_name": "ACME INDUSTRIES PRIVATE LIMITED",
    }
    values.update(overrides)
    return CustomerRecord(**values)


def test_a_provisional_with_a_matching_pan_customer_is_an_attach_suggestion():
    found = suggestions([_provisional(), _pan()], threshold=0.90)

    assert len(found) == 1
    suggestion = found[0]
    assert (suggestion["a"], suggestion["b"]) == ("p1", "c1")
    assert suggestion["kind"] == "ATTACH"
    assert suggestion["similarity"] == 1.0
    assert "Suggestion only" in suggestion["reason"]


def test_two_different_pans_with_similar_names_are_link_as_group_never_merged():
    first = _pan("c1", display_name="Acme Industries Private Limited")
    second = _pan(
        "c2",
        pan="ZZZZZ9999Z",
        display_name="Acme Industrial Private Limited",
    )
    before = (first, second)

    found = suggestions([first, second], threshold=0.90)

    assert len(found) == 1
    suggestion = found[0]
    assert suggestion["kind"] == "LINK_AS_GROUP"
    assert {suggestion["a"], suggestion["b"]} == {"c1", "c2"}
    assert suggestion["similarity"] >= 0.90
    assert "never merge" in suggestion["reason"].lower()
    # Pure: the suggestion does not change either record.
    assert (first, second) == before


def test_two_records_with_the_same_pan_are_not_a_group_suggestion():
    found = suggestions(
        [_pan("c1"), _pan("c2", display_name="ACME INDUSTRIES LIMITED")],
        threshold=0.90,
    )
    assert found == []


def test_a_dismissed_pair_is_not_suggested_again():
    provisional = replace(_provisional(), dismissed_with=frozenset({"c1"}))
    assert suggestions([provisional, _pan()], threshold=0.90) == []


def test_an_already_grouped_pair_is_not_suggested_again():
    provisional = replace(_provisional(), group_id="g1")
    pan = replace(_pan(), group_id="g1")
    assert suggestions([provisional, pan], threshold=0.90) == []


def test_a_grouped_pair_of_different_groups_is_still_suggested():
    provisional = replace(_provisional(), group_id="g1")
    pan = replace(_pan(), group_id="g2")
    assert len(suggestions([provisional, pan], threshold=0.90)) == 1


def test_the_threshold_is_the_caller_supplied_value():
    provisional = _provisional(display_name="Acme Trading Company")
    pan = _pan(display_name="Acme Trading Corporation")

    assert suggestions([provisional, pan], threshold=0.90) == []
    found = suggestions([provisional, pan], threshold=0.80)
    assert len(found) == 1
    assert found[0]["similarity"] < 0.90


def test_thresholds_outside_zero_to_one_are_refused():
    with pytest.raises(ValueError):
        suggestions([], threshold=1.5)
    with pytest.raises(ValueError):
        suggestions([], threshold=-0.1)
    with pytest.raises(TypeError):
        suggestions([], threshold=True)  # type: ignore[arg-type]


def test_no_customers_means_no_suggestions():
    assert suggestions([], threshold=0.90) == []
