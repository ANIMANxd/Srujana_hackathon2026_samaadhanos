"""Dev tests for backend/engine/evaluate.py (the engine author's smoke tests).

Covers the assembly rules: the gate decides first, an ineligible status nulls
the money while an undecided one still computes, blocks are never null, every
merged list is de-duplicated, and every hidden default appears in
assumptions[].

Requests are built through the Pydantic model on purpose: that is how the API
hands them over, and it is the only way to catch an enum being formatted as
"EvidenceKind.PO" instead of "PO".

These are NOT the spec tests in tests/spec/.
"""

from datetime import date
from decimal import Decimal as D

from backend.app.schemas import CaseEvaluationRequest, CaseEvaluationResponse
from backend.engine.evaluate import evaluate_case
from backend.engine.gate import INELIGIBLE_STATUSES, evaluate_gate
from backend.tests.dev.test_gate import make_config

# delivery 2026-02-16 + the clamped 45-day period puts the appointed day on
# 2026-04-03, inside the configured Bank Rate epoch, so interest can be priced.
CALC = "2026-04-15"


def _merge(base: dict, overrides: dict) -> dict:
    """Deep-merge dicts so `transaction={"delivery_date": None}` patches one field
    instead of replacing (or, worse, silently adding) a key."""
    out = dict(base)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def request_dict(**overrides):
    """A valid request dict; patch nested fields with `overrides`."""
    base = {
        "contract_version": "1.0",
        "case_id": "case_eval",
        "supplier": {
            "name": "Sample Supplies (synthetic)",
            "udyam_number": "UDYAM-SYN-000000007",
            "enterprise_class": "SMALL",
            "activity": "MANUFACTURING",
            "nic_codes": ["25990"],
            "udyam_registration_date": "2023-06-01",
            "investment_cr": "1.20",
            "turnover_cr": "8.00",
        },
        "buyer": {
            "name": "Sample Buyer (synthetic)",
            "gstin": "29SYN000000007Z1",
            "tax_rate_pct": "31.20",
            "cost_of_capital_pct": "12.00",
        },
        "transaction": {
            "contract_date": "2026-01-15",
            "supply_date": "2026-02-16",
            "invoice_date": "2026-02-16",
            "delivery_date": "2026-02-16",
            "principal": "1250000.00",
            "written_credit_days": 90,
            "calculation_date": CALC,
            "years_deferred": "1.00",
        },
        "objections": [],
        "part_payments": [],
        "acknowledgments": [
            {
                "date": "2026-04-10",
                "kind": "WHATSAPP_PROMISE",
                "is_signed": False,
                "source_ref": "synthetic whatsapp thread",
            }
        ],
        "evidence": {
            "items": [
                {"kind": "PO", "present": True, "ref": "PO-1"},
                {"kind": "INVOICE", "present": True, "ref": "INV-1"},
                {"kind": "DELIVERY_PROOF", "present": True, "ref": "LR-1"},
                {"kind": "WHATSAPP", "present": True, "ref": "WA-1"},
                {"kind": "UDYAM", "present": True, "ref": "UDYAM-1"},
                {"kind": "GST_RETURN", "present": False, "ref": None},
            ]
        },
        "config_overrides": None,
    }
    return CaseEvaluationRequest.model_validate(_merge(base, overrides))


def run(cfg=None, **overrides):
    return evaluate_case(cfg or make_config(), request_dict(**overrides))


def codes(result, block):
    return [w.code for w in getattr(result, block)]


# ------------------------------------------------------------- shape ----


def test_response_validates_and_echoes_the_request_identity():
    response = run(case_id="case_x")
    model = CaseEvaluationResponse.model_validate(response.model_dump(mode="json", by_alias=True))
    assert model.case_id == "case_x"
    assert model.calculation_date == date(2026, 4, 15)
    assert model.contract_version == "1.0"


def test_no_placeholder_warning_survives_the_real_engine():
    assert "PLACEHOLDER_DATA" not in codes(run(), "warnings")


def test_the_blocks_that_are_never_nullable_are_present():
    result = run()
    assert result.limitation is not None
    assert len(result.defenses) == 7
    assert result.evidence_readiness is not None
    assert result.jurisdiction is not None


# ------------------------------------------------------------- the gate first ----


def test_the_gate_decides_the_status_the_response_shows():
    cfg = make_config()
    request = request_dict()
    gate = evaluate_gate(
        cfg,
        enterprise_class=request.supplier.enterprise_class.value,
        activity=request.supplier.activity.value,
        nic_codes=list(request.supplier.nic_codes),
        contract_date=request.transaction.contract_date,
        supply_date=request.transaction.supply_date,
        investment_cr=request.supplier.investment_cr,
        turnover_cr=request.supplier.turnover_cr,
    )
    result = evaluate_case(cfg, request)
    assert result.jurisdiction.status.value == gate.status
    assert result.jurisdiction.checks[0].id == gate.checks[0].id


def test_a_null_silpi_config_leaves_the_status_undecided_but_the_money_runs():
    """Section 5: an uncaptured constant warns, it does not stop the engine."""
    result = run()  # shipped config has silpi_test_date null
    assert result.jurisdiction.status.value == "INSUFFICIENT_DATA"
    assert result.financials is not None, "an undecided case is not an ineligible one"
    assert result.buyer_cost is not None
    assert result.jurisdiction.alternative_remedy is None
    assert any(w.code == "OPEN_QUESTION" for w in result.warnings)


# ------------------------------------------------------------- ineligible ----


def test_an_ineligible_status_nulls_the_money_and_explains_it():
    result = run(
        supplier=dict(
            name="Sample Grown Exports (synthetic)",
            udyam_number="UDYAM-SYN-000000008",
            enterprise_class="SMALL",
            activity="MANUFACTURING",
            nic_codes=["25990"],
            udyam_registration_date="2021-05-01",
            investment_cr="300.00",
            turnover_cr="800.00",
        )
    )
    assert result.jurisdiction.status.value == "EXCLUDED_MEDIUM"
    assert result.jurisdiction.status.value in INELIGIBLE_STATUSES
    assert result.financials is None, "section 6.1: ineligible skips the interest block"
    assert result.buyer_cost is None, "section 6.1: ineligible skips the buyer-cost block"
    block = next(w for w in result.warnings if w.severity == "BLOCK")
    assert "not because the amounts are zero" in block.text
    assert result.jurisdiction.alternative_remedy, "an ineligible case is offered a remedy"


def test_an_ineligible_case_still_reports_the_never_null_blocks():
    result = run(
        supplier={"enterprise_class": "MEDIUM", "investment_cr": "200.00", "turnover_cr": "700.00"}
    )
    assert result.jurisdiction.status.value in INELIGIBLE_STATUSES
    assert result.limitation is not None
    assert result.defenses and result.evidence_readiness is not None
    assert result.evidence_readiness.band == "BLOCKED"


def test_an_eligible_status_computes_everything():
    """With the Silpi question settled the clean case reaches ELIGIBLE."""
    cfg = make_config()
    cfg._entries["silpi_test_date"]["value"] = "SUPPLY"
    result = run(cfg)
    assert result.jurisdiction.status.value == "ELIGIBLE"
    assert result.financials is not None
    assert result.buyer_cost is not None
    assert result.jurisdiction.alternative_remedy is None


# ------------------------------------------------------------- dates that cannot be fixed ----


def test_no_delivery_date_nulls_the_money_and_reports_no_appointed_day():
    """Not blocked, so §6.2 gives a first-class NO_DELIVERY_PROOF timeline —
    but with no anchor the money cannot be calculated and must say so."""
    result = run(transaction={"delivery_date": None, "supply_date": None})
    assert result.timeline is not None
    assert result.timeline.objection_status.value == "NO_DELIVERY_PROOF"
    assert result.timeline.due_date is None
    assert result.financials is None, "no appointed day, so no interest ran"
    assert result.buyer_cost is None
    assert any(w.code == "NO_APPOINTED_DAY" for w in result.warnings)


def test_a_pending_objection_leaves_the_timeline_but_nulls_the_money():
    """Acceptance can report the pending status even though no day is fixed."""
    result = run(
        objections=[
            {
                "raised_date": "2026-03-01",
                "is_written": True,
                "description": "Synthetic: defect note inside the window",
                "resolved_date": None,
            }
        ]
    )
    assert result.timeline is not None
    assert result.timeline.objection_status.value == "PENDING_RESOLUTION"
    assert result.timeline.due_date is None
    assert result.financials is None
    assert any(w.code == "NO_APPOINTED_DAY" for w in result.warnings)


def test_an_ineligible_case_with_no_delivery_date_nulls_the_timeline():
    """Section 8.3: null when the gate blocks AND no dates are computable.

    The block has to come from the trader exclusion here: without a supply date
    the medium check cannot look a class up, so it returns undecided rather than
    excluding, and only a date-free check can block in that state.
    """
    result = run(
        supplier={
            "enterprise_class": "MICRO",
            "activity": "TRADING",
            "nic_codes": ["46100"],
            "investment_cr": "1.00",
            "turnover_cr": "5.00",
        },
        transaction={"delivery_date": None, "supply_date": None},
    )
    assert result.jurisdiction.status.value in INELIGIBLE_STATUSES
    assert result.jurisdiction.status.value == "EXCLUDED_TRADER"
    assert result.timeline is None
    assert result.financials is None
    assert result.buyer_cost is None


# ------------------------------------------------------------- merged, de-duplicated ----


def test_citations_are_de_duplicated_by_id():
    result = run()
    ids = [c.id for c in result.citations]
    assert len(ids) == len(set(ids)), f"duplicate citations: {ids}"
    assert ids  # the gate always cites what it read


def test_warnings_are_de_duplicated_but_keyed_by_code_and_text():
    result = run()
    pairs = [(w.code, w.text) for w in result.warnings]
    assert len(pairs) == len(set(pairs)), "identical warnings must collapse"
    # Distinct UNVERIFIED_CONSTANT entries (one per key) must NOT collapse:
    unverified = [w for w in result.warnings if w.code == "UNVERIFIED_CONSTANT"]
    assert len(unverified) > 1
    assert len({w.text for w in unverified}) == len(unverified)


def test_assumptions_are_unique_and_ordered():
    result = run()
    assert len(result.assumptions) == len(set(result.assumptions))
    assert result.assumptions  # modules all contribute context


def test_every_module_contributes_to_the_merge():
    result = run()
    # Citations come from gate, acceptance and interest at the least.
    cited_keys = {c.config_key for c in result.citations}
    assert {"size_epochs", "objection_window_days", "interest_multiplier"} <= cited_keys
    # Each module's assumptions survive the merge.
    joined = " ".join(result.assumptions)
    assert "PAYMENT_DATE_IS_REST_BOUNDARY" in joined  # interest
    assert "OQ-3" in joined
    assert "OQ-7" in joined  # defenses
    assert "WhatsApp" in joined or "potential acknowledgment" in joined


# ------------------------------------------------------------- hidden defaults ----


def test_a_missing_supply_date_defaults_to_delivery_and_says_so():
    result = run(transaction={"supply_date": None})
    assert any(
        "supply_date was not given" in a and "delivery date stands in" in a
        for a in result.assumptions
    ), "a default that is not stated is a hidden one"
    # The gate still had an anchor, so the class check is decidable.
    enterprise = next(c for c in result.jurisdiction.checks if c.id == "enterprise_class")
    assert enterprise.passed is True


def test_a_missing_deferral_year_defaults_to_one_and_says_so():
    result = run(transaction={"years_deferred": None})
    assert any("years_deferred was not given" in a for a in result.assumptions)
    assert result.buyer_cost is not None
    assert str(result.buyer_cost.deferral.inputs.years_deferred) == "1.00"


def test_config_overrides_are_applied_and_announced():
    result = run(config_overrides={"bank_rate_pct": "9.00"})
    assert any("Bank Rate overridden to 9.00" in a for a in result.assumptions)
    # statutory = 3 x 9.00 = 27.00, which is what the ledger must price at.
    segment = result.financials.rate_segments[-1]
    assert segment.bank_rate_pct == D("9.00")
    assert segment.statutory_rate_pct == D("27.00")


def test_config_overrides_leave_the_shared_config_untouched():
    """One evaluation's override must not bleed into the next one."""
    cfg = make_config()
    evaluate_case(cfg, request_dict(config_overrides={"bank_rate_pct": "9.00"}))
    from backend.engine.config import StatuteConfig

    fresh = StatuteConfig.from_dict(cfg.public_config())
    assert str(fresh.bank_rate_on(date(2026, 4, 3))) == "5.50"


def test_rate_mode_override_reaches_the_financials():
    result = run(config_overrides={"rate_mode": "FROZEN_AT_APPOINTED_DAY"})
    assert result.financials.rate_mode.value == "FROZEN_AT_APPOINTED_DAY"
    assert any("Rate mode overridden" in a for a in result.assumptions)


# ------------------------------------------------------------- enumeration handling ----


def test_enum_values_from_the_request_reach_the_response_as_plain_codes():
    """Regression: str() on a Pydantic enum yields 'EvidenceKind.PO', not 'PO'."""
    result = run()
    # WhatsApp promise is an enum member in the request, yet it must be read as
    # a qualifying-kind miss and recorded as a potential acknowledgment.
    assert any(w.code == "POTENTIAL_ACKNOWLEDGMENT" for w in result.warnings)
    # The event keeps the contract's value.
    assert result.limitation.events[0].kind.value == "WHATSAPP_PROMISE"
    # Evidence codes stay codes in readiness's missing list.
    assert "GST_RETURN" in result.evidence_readiness.missing
    assert all(not k.startswith("EvidenceKind.") for k in result.evidence_readiness.missing)


def test_unverified_config_constants_reach_the_warnings():
    result = run()
    unverified = [w for w in result.warnings if w.code == "UNVERIFIED_CONSTANT"]
    assert unverified, "the shipped config is unverified, so its usage must surface"
    assert any("interest_multiplier" in w.text for w in unverified)


# ------------------------------------------------------------- purity ----


def test_the_same_request_twice_gives_the_same_response():
    first = run()
    second = run()
    assert first.model_dump(mode="json", by_alias=True) == second.model_dump(
        mode="json", by_alias=True
    )


def test_one_config_can_be_reused_across_cases_without_leaking_usage():
    """Usage is per-evaluation: case A must not report case B's constants."""
    cfg = make_config()
    rich = evaluate_case(cfg, request_dict(case_id="rich"))
    bare = evaluate_case(
        cfg,
        request_dict(
            case_id="bare",
            objections=[],
            acknowledgments=[],
            # Nothing that touches credit_cap_days: no written period.
            transaction=dict(
                contract_date="2026-01-15",
                # With no written period the delay is only 15 days, so delivery
                # must sit late enough for the appointed day (2026-04-05) to
                # land inside the configured Bank Rate epoch.
                supply_date="2026-03-20",
                invoice_date="2026-03-20",
                delivery_date="2026-03-20",
                principal="1250000.00",
                written_credit_days=None,
                calculation_date=CALC,
                years_deferred="1.00",
            ),
        ),
    )
    rich_texts = " ".join(w.text for w in rich.warnings if w.code == "UNVERIFIED_CONSTANT")
    bare_texts = " ".join(w.text for w in bare.warnings if w.code == "UNVERIFIED_CONSTANT")
    assert "credit_cap_days" in rich_texts, "the Net-90 case reads the cap"
    assert "credit_cap_days" not in bare_texts, "the no-agreement case never touched it"
