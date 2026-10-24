"""Dev tests for backend/engine/defenses.py (the engine author's smoke tests).

Covers: all seven rows in order, each status driven by engine state, arbitration
and set-off staying OPEN_QUESTION under every state, and evidence lists split
from the request as EvidenceKind codes.

These are NOT the spec tests in tests/spec/.
"""

from backend.engine.defenses import (
    STATUS_AT_RISK,
    STATUS_OPEN_QUESTION,
    STATUS_STRONG,
    evaluate_defenses,
)

SEVEN = [
    "defective_goods",
    "never_accepted",
    "po_90_days",
    "not_eligible",
    "arbitration_clause",
    "set_off",
    "time_barred",
]


class Ev:
    """Minimal evidence item satisfying EvidenceLike."""

    def __init__(self, kind, present=True, ref=None):
        self.kind = kind
        self.present = present
        self.ref = ref


ALL_EVIDENCE = [
    Ev("PO", True, "PO-001"),
    Ev("INVOICE", True, "INV-001"),
    Ev("DELIVERY_PROOF", True, "LR-001"),
    Ev("WHATSAPP", True, "WA-001"),
    Ev("UDYAM", True, "UDYAM-001"),
    Ev("GST_RETURN", False, None),
]


def defend(**kwargs):
    """A well-supported case unless overridden."""
    facts = dict(
        gate_status="ELIGIBLE",
        acceptance_status="DEEMED_ACCEPTANCE",
        agreed_days=30,
        credit_clamped=False,
        limitation_status="OK",
        evidence=ALL_EVIDENCE,
    )
    facts.update(kwargs)
    return evaluate_defenses(**facts)


def row(result, defense_id):
    return next(r for r in result.rows if r.id == defense_id)


# ------------------------------------------------------------ shape ----


def test_all_seven_rows_are_always_returned_in_the_documented_order():
    """Section 6.6 order; the guidance card takes the first at-risk row."""
    assert [r.id for r in defend().rows] == SEVEN


def test_every_row_carries_a_module_prefixed_rule_ref():
    result = defend()
    for r in result.rows:
        assert r.rule_ref == f"defenses.{r.id}"  # rules.<code>.title on the UI


def test_every_status_is_one_of_the_three_allowed():
    """Whatever the engine state, no row may invent a fourth answer."""
    allowed = {STATUS_STRONG, STATUS_AT_RISK, STATUS_OPEN_QUESTION}
    states = [
        {},
        {"gate_status": "EXCLUDED_MEDIUM", "limitation_status": "EXPIRED"},
        {"acceptance_status": None, "agreed_days": None, "limitation_status": "UNKNOWN"},
        {"gate_status": "INSUFFICIENT_DATA", "acceptance_status": "NO_DELIVERY_PROOF"},
        {"evidence": []},
    ]
    for state in states:
        statuses = {r.status for r in defend(**state).rows}
        assert statuses <= allowed, state


def test_no_config_constant_is_read_so_no_citations_are_claimed():
    """This module cites nothing because it reads no statutory constant."""
    assert defend().citations == []


def test_assumptions_state_the_oq7_position():
    joined = " ".join(defend().assumptions)
    assert "OQ-7" in joined
    assert "never decided here" in joined
    assert "independently" in joined


# --------------------------------------------------- acceptance-driven rows ----


def test_defective_goods_is_strong_after_deemed_acceptance():
    assert row(defend(), "defective_goods").status == STATUS_STRONG


def test_defective_goods_is_at_risk_while_a_written_objection_is_open():
    assert row(defend(acceptance_status="PENDING_RESOLUTION"), "defective_goods").status == STATUS_AT_RISK


def test_defective_goods_is_strong_after_a_resolved_objection():
    """Acceptance was fixed at the resolution date, so the claim is answered.

    An objection raised inside the window and then resolved is exactly what
    section 6.2 turns into an acceptance date, so the engine has a verdict.
    """
    assert row(defend(acceptance_status="RESOLVED"), "defective_goods").status == STATUS_STRONG


def test_both_acceptance_driven_rows_agree():
    """They answer the same question - was acceptance fixed? - so one verdict."""
    for state in (None, "DEEMED_ACCEPTANCE", "RESOLVED", "PENDING_RESOLUTION", "NO_DELIVERY_PROOF"):
        result = defend(acceptance_status=state)
        assert row(result, "defective_goods").status == row(result, "never_accepted").status, state


def test_defective_goods_is_at_risk_without_delivery_proof():
    assert row(defend(acceptance_status="NO_DELIVERY_PROOF"), "defective_goods").status == STATUS_AT_RISK


def test_defective_goods_is_an_open_question_without_a_verdict():
    assert row(defend(acceptance_status=None), "defective_goods").status == STATUS_OPEN_QUESTION


def test_never_accepted_is_strong_on_deemed_acceptance():
    assert row(defend(), "never_accepted").status == STATUS_STRONG


def test_never_accepted_is_at_risk_without_delivery_proof():
    assert row(defend(acceptance_status="NO_DELIVERY_PROOF"), "never_accepted").status == STATUS_AT_RISK


def test_never_accepted_is_at_risk_while_the_window_is_open():
    assert row(defend(acceptance_status="PENDING_RESOLUTION"), "never_accepted").status == STATUS_AT_RISK


def test_never_accepted_is_an_open_question_without_a_verdict():
    assert row(defend(acceptance_status=None), "never_accepted").status == STATUS_OPEN_QUESTION


# --------------------------------------------------- credit-period rows ----


def test_po_term_is_strong_when_the_statutory_cap_bit():
    """agreed 90 against a 45-day cap: clamped, so the PO term does not govern."""
    assert row(defend(agreed_days=90, credit_clamped=True), "po_90_days").status == STATUS_STRONG


def test_po_term_is_at_risk_when_the_agreed_period_stands():
    assert row(defend(agreed_days=90, credit_clamped=False), "po_90_days").status == STATUS_AT_RISK


def test_po_term_is_an_open_question_when_no_written_period_is_held():
    """No written credit period in the request, and OQ-5 is still open."""
    assert row(defend(agreed_days=None), "po_90_days").status == STATUS_OPEN_QUESTION


# --------------------------------------------------- gate-driven rows ----


def test_not_eligible_is_strong_when_the_gate_allows_the_case():
    assert row(defend(gate_status="ELIGIBLE"), "not_eligible").status == STATUS_STRONG


def test_not_eligible_is_at_risk_when_the_gate_blocks():
    for status in ("BARRED_SILPI", "EXCLUDED_TRADER", "EXCLUDED_MEDIUM"):
        assert row(defend(gate_status=status), "not_eligible").status == STATUS_AT_RISK


def test_not_eligible_is_at_risk_when_the_gate_cannot_decide():
    assert row(defend(gate_status="INSUFFICIENT_DATA"), "not_eligible").status == STATUS_AT_RISK


def test_not_eligible_is_an_open_question_for_an_unrecognised_gate_status():
    assert row(defend(gate_status="SOMETHING_ELSE"), "not_eligible").status == STATUS_OPEN_QUESTION


# ------------------------------------ arbitration and set-off never decided ----


def test_arbitration_and_set_off_are_always_open_questions():
    """OQ-7: neither is decided here, whatever the rest of the engine says."""
    states = [
        {"gate_status": "ELIGIBLE", "acceptance_status": "DEEMED_ACCEPTANCE", "limitation_status": "OK"},
        {"gate_status": "EXCLUDED_MEDIUM", "acceptance_status": "NO_DELIVERY_PROOF", "limitation_status": "EXPIRED"},
        {"gate_status": "INSUFFICIENT_DATA", "acceptance_status": None, "limitation_status": "UNKNOWN"},
        {"credit_clamped": True, "agreed_days": 90},
    ]
    for state in states:
        result = defend(**state)
        assert row(result, "arbitration_clause").status == STATUS_OPEN_QUESTION, state
        assert row(result, "set_off").status == STATUS_OPEN_QUESTION, state


# --------------------------------------------------- limitation-driven rows ----


def test_time_barred_is_strong_when_the_claim_is_in_time():
    for status in ("OK", "WARN_12M"):
        assert row(defend(limitation_status=status), "time_barred").status == STATUS_STRONG


def test_time_barred_is_at_risk_when_time_is_running_out_or_gone():
    for status in ("WARN_6M", "EXPIRED"):
        assert row(defend(limitation_status=status), "time_barred").status == STATUS_AT_RISK


def test_time_barred_is_an_open_question_when_the_band_is_unknown():
    assert row(defend(limitation_status="UNKNOWN"), "time_barred").status == STATUS_OPEN_QUESTION


def test_an_unrecognised_band_is_not_mistaken_for_expired():
    """Regression: a substring check against "EXPIRED" would match "RED"."""
    assert row(defend(limitation_status="RED"), "time_barred").status == STATUS_OPEN_QUESTION


# --------------------------------------------------- evidence lists ----


def test_evidence_lists_are_codes_translated_by_the_frontend():
    """GuidanceCard renders tCode("evidence", k, k), so only codes work."""
    r = row(defend(), "never_accepted")
    assert set(r.evidence_have) == {"DELIVERY_PROOF", "INVOICE", "PO"}
    assert r.evidence_missing == []


def test_absent_evidence_is_reported_as_missing():
    r = row(defend(evidence=[Ev("PO", True)]), "never_accepted")
    assert r.evidence_have == ["PO"]
    # Reported in the argument's own order: delivery proof, then invoice.
    assert r.evidence_missing == ["DELIVERY_PROOF", "INVOICE"]


def test_evidence_the_request_never_mentions_counts_as_missing():
    """Silence is not evidence: an unlisted kind is missing, not skipped."""
    r = row(defend(evidence=[]), "not_eligible")
    assert r.evidence_have == []
    assert r.evidence_missing == ["UDYAM", "GST_RETURN"]


def test_evidence_refs_are_not_embedded_in_the_lists():
    """The UI translates the code and shows refs separately, so no concat."""
    r = row(defend(), "defective_goods")
    assert all("PO-001" not in v for v in r.evidence_have + r.evidence_missing)


def test_present_false_is_missing_not_have():
    r = row(defend(), "not_eligible")  # GST_RETURN is present=False in ALL_EVIDENCE
    assert "GST_RETURN" in r.evidence_missing
    assert "GST_RETURN" not in r.evidence_have


# -------------------------------- status is decided by rules, not paperwork ----


def test_evidence_absence_does_not_change_a_status():
    """CQ-26: the two columns stay independent, so both are checkable."""
    with_evidence = row(defend(evidence=[Ev("INVOICE", True)]), "never_accepted")
    without_evidence = row(defend(evidence=[]), "never_accepted")
    assert with_evidence.status == without_evidence.status == STATUS_STRONG
    assert with_evidence.evidence_have != without_evidence.evidence_have


def test_missing_delivery_paperwork_does_not_hide_a_strong_rule_outcome():
    """The panel shows what is held separately from how strong the answer is."""
    r = row(defend(evidence=[]), "defective_goods")
    assert r.status == STATUS_STRONG
    assert r.evidence_missing == ["PO", "INVOICE", "DELIVERY_PROOF"]


# --------------------------------------------------- contract shape ----


def test_result_validates_against_the_frozen_defense_model():
    from backend.app.schemas import Defense as DefenseModel
    from backend.app.schemas import DefenseStatus

    for kwargs in (
        {},
        {"gate_status": "EXCLUDED_MEDIUM", "limitation_status": "EXPIRED"},
        {"acceptance_status": None, "agreed_days": None, "limitation_status": "UNKNOWN"},
        {"evidence": []},
    ):
        payload = defend(**kwargs).to_dict()
        assert len(payload) == 7
        for item in payload:
            model = DefenseModel(**item)
            assert model.status in (
                DefenseStatus.STRONG,
                DefenseStatus.AT_RISK,
                DefenseStatus.OPEN_QUESTION,
            )
            assert model.rule_ref == f"defenses.{model.id}"


def test_arbitration_and_set_off_validate_as_open_question():
    from backend.app.schemas import Defense as DefenseModel
    from backend.app.schemas import DefenseStatus

    payload = defend(limitation_status="EXPIRED", gate_status="EXCLUDED_MEDIUM").to_dict()
    for item in payload:
        if item["id"] in ("arbitration_clause", "set_off"):
            assert DefenseModel(**item).status == DefenseStatus.OPEN_QUESTION
