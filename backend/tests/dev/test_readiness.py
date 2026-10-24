"""Dev tests for backend/engine/readiness.py (the engine author's smoke tests).

Covers: every band, the score reproduced exactly from its listed reasons, the
cap when delivery proof is missing, blocked stages, and the recommended stage
branch by branch.

The band value is `EVIDENCE_COMPLETE`, which the frozen contract does not carry
yet - that rename is CR-3 and needs both humans (architecture section 9.3), so
these tests check the payload's *shape* against the contract model without
constructing it. See docs/open-questions.md CQ-23.

These are NOT the spec tests in tests/spec/.
"""

from datetime import date

from backend.engine.readiness import (
    BASE_SCORE,
    BAND_ACTION_NEEDED,
    BAND_BLOCKED,
    BAND_EVIDENCE_COMPLETE,
    DELIVERY_PROOF_SCORE_CAP,
    evaluate_readiness,
)

DELIVERY = date(2026, 1, 10)
DUE = date(2026, 2, 9)


class Ev:
    """Minimal evidence item satisfying EvidenceLike."""

    def __init__(self, kind, present=True, ref=None):
        self.kind = kind
        self.present = present
        self.ref = ref


# The five kinds that earn points, plus WhatsApp, which is optional by nature.
ALL_EVIDENCE = [
    Ev("PO", True, "PO-001"),
    Ev("INVOICE", True, "INV-001"),
    Ev("DELIVERY_PROOF", True, "LR-001"),
    Ev("WHATSAPP", True, "WA-001"),
    Ev("UDYAM", True, "UDYAM-001"),
    Ev("GST_RETURN", True, "GST-001"),
]


def ready(**kwargs):
    """An eligible, fully evidenced, overdue case unless overridden."""
    facts = dict(
        gate_status="ELIGIBLE",
        delivery_date=DELIVERY,
        due_date=DUE,
        days_overdue=40,
        evidence=list(ALL_EVIDENCE),
    )
    facts.update(kwargs)
    return evaluate_readiness(**facts)


def without(*kinds):
    """All evidence except the named kinds."""
    return [e for e in ALL_EVIDENCE if e.kind not in kinds]


def deltas(result):
    return [r.delta for r in result.reasons]


def test_every_band_value_is_one_of_the_three_named():
    bands = {
        ready().band,
        ready(gate_status="EXCLUDED_MEDIUM").band,
        ready(evidence=without("GST_RETURN")).band,
        ready(gate_status="INSUFFICIENT_DATA").band,
        ready(evidence=[]).band,
    }
    assert bands == {BAND_EVIDENCE_COMPLETE, BAND_ACTION_NEEDED, BAND_BLOCKED}


# ------------------------------------------------------------ bands per status ----


def test_eligible_case_with_everything_held_is_evidence_complete():
    result = ready()
    assert result.band == BAND_EVIDENCE_COMPLETE
    assert result.missing == []
    assert result.reasons == []


def test_each_gate_block_sets_the_blocked_band():
    for status in ("BARRED_SILPI", "EXCLUDED_TRADER", "EXCLUDED_MEDIUM"):
        assert ready(gate_status=status).band == BAND_BLOCKED, status


def test_gate_block_beats_missing_evidence():
    result = ready(gate_status="EXCLUDED_MEDIUM", evidence=[])
    assert result.band == BAND_BLOCKED
    assert "GST_RETURN" in result.missing  # the paperwork gap is still reported


def test_unresolved_gate_is_not_evidence_complete():
    """Eligibility is not evidence, but an unfinished case is not complete."""
    assert ready(gate_status="INSUFFICIENT_DATA").band == BAND_ACTION_NEEDED


def test_missing_evidence_takes_the_case_out_of_evidence_complete():
    for kind in ("PO", "INVOICE", "UDYAM", "GST_RETURN", "DELIVERY_PROOF"):
        result = ready(evidence=without(kind))
        assert result.band == BAND_ACTION_NEEDED, kind


def test_missing_delivery_date_alone_stops_evidence_complete():
    """Every document held, but no delivery date entered."""
    assert ready(delivery_date=None).band == BAND_ACTION_NEEDED


# ------------------------------------------------------------ score == reasons ----


def test_a_clean_case_scores_the_full_base_with_no_reasons():
    result = ready()
    assert result.score == BASE_SCORE
    assert result.reasons == []


def test_the_score_equals_the_base_adjusted_by_the_listed_deltas():
    """The acceptance criterion: add up the reasons and you get the number.

    The only adjustment is the 0 floor from section 6.6's "0-100", which binds
    only when the deductions exceed the base itself; every case below except the
    extreme one is checked against the raw sum too.
    """
    cases = [
        {},
        {"evidence": without("GST_RETURN")},
        {"evidence": without("PO")},
        {"evidence": without("PO", "INVOICE")},
        {"evidence": without("UDYAM", "GST_RETURN")},
        {"gate_status": "INSUFFICIENT_DATA"},
        {"gate_status": "EXCLUDED_MEDIUM"},
        {"due_date": None},
        {"evidence": without("DELIVERY_PROOF")},
        {"evidence": without("DELIVERY_PROOF", "GST_RETURN")},
        {"evidence": [], "gate_status": "INSUFFICIENT_DATA"},
    ]
    for state in cases:
        result = ready(**state)
        raw = BASE_SCORE + sum(deltas(result))
        assert result.score == max(0, raw), state
        assert 0 <= result.score <= BASE_SCORE, state


def test_score_never_goes_below_zero_when_deductions_outrun_the_base():
    """100 - 50 - 15 - 15 - 10 - 5 - 10 is negative, so the floor holds it at 0."""
    result = ready(evidence=[], gate_status="INSUFFICIENT_DATA")
    assert BASE_SCORE + sum(deltas(result)) < 0
    assert result.score == 0
    assert all(r.delta <= 0 for r in result.reasons)


def test_deductions_are_the_points_listed_on_each_reason():
    result = ready(evidence=without("PO", "UDYAM"))
    by_code = {r.code: r.delta for r in result.reasons}
    assert by_code == {
        "MISSING_EVIDENCE_PO": -15,
        "MISSING_EVIDENCE_UDYAM": -10,
    }
    # 100 - 15 - 10 = 75
    assert result.score == 75


def test_every_delta_is_zero_or_negative():
    for state in ({}, {"evidence": []}, {"gate_status": "EXCLUDED_MEDIUM"}):
        assert all(d <= 0 for d in deltas(ready(**state))), state


def test_the_gate_blocked_reason_costs_nothing():
    """It explains the band, so it must not move the score (CQ-24)."""
    clean = ready()
    blocked = ready(gate_status="EXCLUDED_MEDIUM")
    assert blocked.score == clean.score
    gate_reason = next(r for r in blocked.reasons if r.code == "GATE_BLOCKED")
    assert gate_reason.delta == 0
    assert "unchanged by this line" in gate_reason.text


def test_acceptance_unresolved_deducts_while_delivery_is_held():
    result = ready(due_date=None)
    assert result.score == BASE_SCORE - 10
    assert [r.code for r in result.reasons] == ["ACCEPTANCE_UNRESOLVED"]


# ------------------------------------------------------------ the cap ----


def test_missing_delivery_proof_caps_the_score():
    """The deduction is exactly BASE minus the cap, so the cap shows up as
    50 by both routes: the sum of the reasons, and the cap itself."""
    result = ready(evidence=without("DELIVERY_PROOF"))
    assert sum(deltas(result)) == -(BASE_SCORE - DELIVERY_PROOF_SCORE_CAP)
    assert BASE_SCORE + sum(deltas(result)) == DELIVERY_PROOF_SCORE_CAP == 50
    assert result.score == DELIVERY_PROOF_SCORE_CAP


def test_the_cap_never_raises_a_score_already_below_it():
    result = ready(evidence=without("DELIVERY_PROOF", "PO", "INVOICE", "UDYAM", "GST_RETURN"))
    # 100 - 50 - 15 - 15 - 10 - 5 = 5, below the cap, so left alone.
    assert result.score == 5
    assert result.score == BASE_SCORE + sum(deltas(result))


def test_the_cap_reason_says_it_was_applied():
    result = ready(evidence=without("DELIVERY_PROOF"))
    reason = next(r for r in result.reasons if r.code == "MISSING_DELIVERY_PROOF")
    assert "cap" in reason.text
    assert str(DELIVERY_PROOF_SCORE_CAP) in reason.text


def test_a_missing_delivery_date_counts_as_missing_delivery_proof():
    result = ready(delivery_date=None)
    assert result.score == DELIVERY_PROOF_SCORE_CAP
    assert result.missing == ["DELIVERY_PROOF"]
    assert result.blocked_stages == [4]


# ------------------------------------------------------------ missing[] ----


def test_missing_lists_the_absent_kinds_and_delivery_proof_first():
    result = ready(evidence=without("DELIVERY_PROOF", "PO"))
    assert result.missing == ["DELIVERY_PROOF", "PO"]


def test_whatsapp_is_optional_so_never_missing():
    result = ready(evidence=without("WHATSAPP"))
    assert "WHATSAPP" not in result.missing
    assert result.band == BAND_EVIDENCE_COMPLETE
    assert result.score == BASE_SCORE


def test_absent_evidence_the_request_never_mentioned_is_still_missing():
    result = ready(evidence=[])
    assert set(result.missing) == {"DELIVERY_PROOF", "PO", "INVOICE", "UDYAM", "GST_RETURN"}


def test_whatsapp_alone_present_changes_nothing():
    """Optional paperwork is not counted, in either direction."""
    only_chat = ready(evidence=[Ev("WHATSAPP", True)])
    assert only_chat.missing == ["DELIVERY_PROOF", "PO", "INVOICE", "UDYAM", "GST_RETURN"]
    assert only_chat.score == BASE_SCORE + sum(deltas(only_chat))


# ------------------------------------------------------------ blocked stages ----


def test_stage_four_is_blocked_only_by_missing_delivery_proof():
    assert ready(evidence=without("DELIVERY_PROOF")).blocked_stages == [4]
    assert ready(evidence=without("PO", "GST_RETURN")).blocked_stages == []
    assert ready().blocked_stages == []


# ------------------------------------------------------------ recommended stage ----


def test_stage_four_when_everything_is_held():
    assert ready().recommended_stage == 4


def test_stage_one_when_delivery_proof_is_missing():
    assert ready(evidence=without("DELIVERY_PROOF")).recommended_stage == 1


def test_stage_one_when_the_gate_blocks():
    for status in ("BARRED_SILPI", "EXCLUDED_TRADER", "EXCLUDED_MEDIUM"):
        assert ready(gate_status=status).recommended_stage == 1, status


def test_stage_one_when_the_case_is_not_yet_past_its_appointed_day():
    assert ready(days_overdue=None).recommended_stage == 1


def test_stage_one_when_there_is_no_due_date_yet():
    """Even with every document in hand, there is no date to put in front of anyone."""
    assert ready(due_date=None).recommended_stage == 1


def test_stage_two_while_eligibility_is_unresolved():
    assert ready(gate_status="INSUFFICIENT_DATA").recommended_stage == 2


def test_stage_three_while_paperwork_is_outstanding():
    assert ready(evidence=without("GST_RETURN")).recommended_stage == 3
    assert ready(evidence=without("PO")).recommended_stage == 3


def test_stage_number_is_always_one_of_the_four():
    for state in (
        {},
        {"evidence": []},
        {"gate_status": "EXCLUDED_MEDIUM"},
        {"gate_status": "INSUFFICIENT_DATA"},
        {"days_overdue": None},
        {"due_date": None},
        {"evidence": without("GST_RETURN")},
    ):
        assert ready(**state).recommended_stage in (1, 2, 3, 4), state


# ------------------------------------------------------------ citations and shape ----


def test_no_config_constant_is_read_so_no_citations_are_claimed():
    assert ready().citations == []


def test_assumptions_explain_the_formula_and_the_band():
    joined = " ".join(ready().assumptions)
    assert "plus every reason" in joined
    assert "capped" in joined
    assert "delta of zero" in joined
    assert "WhatsApp" in joined
    assert "no day thresholds" in joined


def test_payload_has_exactly_the_contract_fields():
    """The shape matches EvidenceReadiness; only the band value differs (CR-3)."""
    from backend.app.schemas import EvidenceReadiness

    payload = ready().to_dict()
    assert set(payload) == set(EvidenceReadiness.model_fields)
    assert set(payload) == {
        "score",
        "band",
        "reasons",
        "missing",
        "blocked_stages",
        "recommended_stage",
    }


def test_each_reason_validates_against_the_frozen_reason_model():
    from backend.app.schemas import ReadinessReason as ReasonModel

    for state in ({}, {"evidence": []}, {"gate_status": "EXCLUDED_MEDIUM"}):
        for reason in ready(**state).reasons:
            model = ReasonModel(**reason.to_dict())
            assert model.delta <= 0
            assert model.code


def test_score_is_an_int_and_the_lists_are_plain():
    payload = ready(evidence=without("PO")).to_dict()
    assert isinstance(payload["score"], int)
    assert all(isinstance(k, str) for k in payload["missing"])
    assert all(isinstance(n, int) for n in payload["blocked_stages"])
    assert isinstance(payload["recommended_stage"], int)
