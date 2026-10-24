"""Dev tests for backend/engine/gate.py (the engine author's own smoke tests).

Covers: every status by the section 6.1 precedence, a null silpi config value
returning passed=None plus an OPEN_QUESTION warning, reverse graduation on the
2025-04-01 size-epoch boundary, and that the output validates against the frozen
Pydantic models.

These are NOT the spec tests in tests/spec/; those come from the independent test
author and must pass without this module.
"""

from datetime import date
from decimal import Decimal

import pytest

from backend.engine.config import StatuteConfig
from backend.engine.gate import (
    ALTERNATIVE_REMEDY,
    CHECK_ACTIVITY_MATCH,
    CHECK_ENTERPRISE_CLASS,
    CHECK_SILPI_CHRONOLOGY,
    CHECK_TRADER_EXCLUSION,
    STATUS_BARRED_SILPI,
    STATUS_ELIGIBLE,
    STATUS_EXCLUDED_MEDIUM,
    STATUS_EXCLUDED_TRADER,
    STATUS_INSUFFICIENT_DATA,
    STATUS_PRECEDENCE,
    WARNING_NO_SIZE_EPOCH,
    WARNING_OPEN_QUESTION,
    WARNING_TRADING_EVIDENCE_CONFLICT,
    evaluate_gate,
)


def make_config(**overrides):
    """A config dict with the two size epochs from section 5, overridable."""
    base = {
        "interest_multiplier": {"value": 3, "source_ref": "V2:s.16", "verified": False, "note": ""},
        "objection_window_days": {"value": 15, "source_ref": "V2:s.2(b)", "verified": False, "note": ""},
        "credit_cap_days": {"value": 45, "source_ref": "V2:s.15 proviso", "verified": False, "note": ""},
        "no_agreement_days": {"value": 15, "source_ref": "V2:s.15", "verified": False, "note": ""},
        "bank_rate_epochs": {
            "value": [{"from": "2026-04-01", "bank_rate_pct": "5.50"}],
            "source_ref": "V1",
            "verified": False,
            "note": "",
        },
        "size_epochs": {
            "value": [
                {"from": "2025-04-01",
                 "micro": {"investment_cr": "2.5", "turnover_cr": "10"},
                 "small": {"investment_cr": "25", "turnover_cr": "100"},
                 "medium": {"investment_cr": "125", "turnover_cr": "500"}},
                {"from": None,
                 "micro": {"investment_cr": "1", "turnover_cr": "5"},
                 "small": {"investment_cr": "10", "turnover_cr": "50"},
                 "medium": {"investment_cr": "50", "turnover_cr": "250"}},
            ],
            "source_ref": "V6",
            "verified": False,
            "note": "",
        },
        "silpi_test_date": {"value": None, "source_ref": "V4", "verified": False, "note": ""},
        "trader_nic_prefixes": {"value": ["45", "46", "47"], "source_ref": "V5", "verified": False, "note": ""},
        "limitation_years": {"value": None, "source_ref": "V7", "verified": False, "note": ""},
        "section_43bh_first_fy": {"value": "2023-24", "source_ref": "V3", "verified": False, "note": ""},
        "rate_mode_default": {"value": "FLOATING", "source_ref": "open:OQ-4", "verified": False, "note": ""},
        "appropriation_mode_default": {"value": "INTEREST_FIRST", "source_ref": "open", "verified": False, "note": ""},
        "payment_boundary_convention": {"value": "PAYMENT_DATE_IS_REST_BOUNDARY", "source_ref": "open:OQ-3", "verified": False, "note": ""},
        "day_count_fraction_days": {"value": 365, "source_ref": "convention", "verified": False, "note": ""},
        "tax_presets": {"value": [], "source_ref": "V3", "verified": False, "note": ""},
        "gated_features": {"value": {"gst_itc_180d": False, "msme1_return": False, "s19_deposit": False}, "source_ref": "V9", "verified": False, "note": ""},
    }
    base.update(overrides)
    return StatuteConfig.from_dict(base)


def run_gate(cfg=None, **kwargs):
    """Run the gate over a small manufacturing supplier unless overridden."""
    cfg = cfg or make_config()
    facts = {
        "enterprise_class": "SMALL",
        "activity": "MANUFACTURING",
        "nic_codes": ["27900"],
        "contract_date": date(2025, 11, 1),
        "supply_date": date(2025, 12, 1),
        "investment_cr": Decimal("20"),
        "turnover_cr": Decimal("80"),
    }
    facts.update(kwargs)
    return evaluate_gate(cfg, **facts)


def check(result, check_id):
    return next(c for c in result.checks if c.id == check_id)


# --------------------------------------------------------------- shape ----


def test_result_carries_all_four_checks_in_order():
    result = run_gate()
    assert [c.id for c in result.checks] == [
        CHECK_ENTERPRISE_CLASS,
        CHECK_SILPI_CHRONOLOGY,
        CHECK_TRADER_EXCLUSION,
        CHECK_ACTIVITY_MATCH,
    ]


def test_every_check_has_a_rule_ref_and_a_citation():
    """Section 6: every rule emits a citation."""
    result = run_gate()
    for c in result.checks:
        assert c.rule_ref.startswith("gate."), c.rule_ref
    # One citation per config key the gate read, all carrying a source_ref.
    cited = {c.config_key for c in result.citations}
    assert "size_epochs" in cited
    assert "silpi_test_date" in cited
    assert "trader_nic_prefixes" in cited
    for citation in result.citations:
        assert citation.statute_ref
        assert citation.id.startswith("gate.")


def test_citations_carry_the_config_verified_flag():
    cfg = make_config()
    cfg._entries["size_epochs"]["verified"] = True
    result = run_gate(cfg)
    size_citation = next(c for c in result.citations if c.config_key == "size_epochs")
    assert size_citation.verified is True
    other = next(c for c in result.citations if c.config_key == "silpi_test_date")
    assert other.verified is False


def test_gate_reads_config_and_those_keys_are_reported_unverified():
    """Usage tracking: the constants this gate relied on are named."""
    cfg = make_config()
    run_gate(cfg)
    warnings = cfg.warnings()
    assert {w.code for w in warnings} == {"UNVERIFIED_CONSTANT"}
    joined = " ".join(w.text for w in warnings)
    for key in ("size_epochs", "silpi_test_date", "trader_nic_prefixes"):
        assert key in joined


# -------------------------------------------------------------- statuses ----


def test_status_precedence_is_the_documented_order():
    assert STATUS_PRECEDENCE == (
        STATUS_BARRED_SILPI,
        STATUS_EXCLUDED_TRADER,
        STATUS_EXCLUDED_MEDIUM,
        STATUS_INSUFFICIENT_DATA,
        STATUS_ELIGIBLE,
    )


def test_decidable_small_supplier_is_insufficient_data_while_silpi_is_open():
    """With silpi_test_date null (OQ-2 open), nothing can be fully ELIGIBLE.

    Section 6.1: INSUFFICIENT_DATA outranks ELIGIBLE, and a null silpi check is
    undecidable. The enterprise check itself still passes on its own terms.
    """
    result = run_gate()
    assert result.status == STATUS_INSUFFICIENT_DATA
    assert result.eligible is False
    assert check(result, CHECK_ENTERPRISE_CLASS).passed is True
    assert check(result, CHECK_SILPI_CHRONOLOGY).passed is None


def test_small_supplier_is_eligible_once_silpi_is_settled():
    """OQ-2 resolved to SUPPLY would let a clean small supplier reach ELIGIBLE."""
    cfg = make_config(silpi_test_date={"value": "SUPPLY", "source_ref": "V4", "verified": False, "note": ""})
    result = run_gate(cfg)
    assert result.status == STATUS_ELIGIBLE
    assert result.eligible is True
    assert result.alternative_remedy is None
    assert check(result, CHECK_ENTERPRISE_CLASS).passed is True


def test_medium_supplier_is_excluded():
    result = run_gate(enterprise_class="MEDIUM", investment_cr=Decimal("200"), turnover_cr=Decimal("700"))
    assert result.status == STATUS_EXCLUDED_MEDIUM
    assert result.eligible is False
    assert check(result, CHECK_ENTERPRISE_CLASS).passed is False


def test_blocked_case_carries_the_alternative_remedy():
    result = run_gate(enterprise_class="MEDIUM", investment_cr=Decimal("200"), turnover_cr=Decimal("700"))
    assert result.alternative_remedy == ALTERNATIVE_REMEDY
    # Cautious language, no promise of winning (AGENTS.md section 7).
    assert "does not predict an outcome" in result.alternative_remedy


def test_an_undecided_case_is_offered_no_remedy():
    """Section 6.1 pairs the remedy with the ineligible results.

    INSUFFICIENT_DATA is undecided, not ineligible: telling a case the route
    "does not apply" while the engine goes on to compute its interest would
    contradict the response it appears in.
    """
    cfg = make_config()  # silpi_test_date is null, so the gate cannot decide
    result = run_gate(cfg)
    assert result.status == STATUS_INSUFFICIENT_DATA
    assert result.eligible is False
    assert result.alternative_remedy is None


def test_ineligible_statuses_are_exactly_the_three_that_block_the_money():
    from backend.engine.gate import INELIGIBLE_STATUSES

    assert INELIGIBLE_STATUSES == {"BARRED_SILPI", "EXCLUDED_TRADER", "EXCLUDED_MEDIUM"}
    assert STATUS_INSUFFICIENT_DATA not in INELIGIBLE_STATUSES
    assert STATUS_ELIGIBLE not in INELIGIBLE_STATUSES


def test_trading_nic_is_excluded_as_trader():
    result = run_gate(nic_codes=["45200"], activity="MANUFACTURING")
    assert result.status == STATUS_EXCLUDED_TRADER
    assert check(result, CHECK_TRADER_EXCLUSION).passed is False


def test_trading_activity_without_nic_codes_is_excluded():
    result = run_gate(nic_codes=[], activity="TRADING")
    assert result.status == STATUS_EXCLUDED_TRADER


def test_silpi_check_is_null_when_config_is_null_and_never_bars():
    """OQ-2: a null silpi_test_date is undecidable, not a pass and not a bar."""
    result = run_gate()
    silpi = check(result, CHECK_SILPI_CHRONOLOGY)
    assert silpi.passed is None
    assert result.status == STATUS_INSUFFICIENT_DATA
    assert result.eligible is False
    warn = next(w for w in result.warnings if w.code == WARNING_OPEN_QUESTION)
    assert "OQ-2" in warn.text
    assert "neither a pass nor a fail" in warn.text


def test_null_silpi_plus_medium_reports_worse_status_first():
    """BARRED_SILPI outranks EXCLUDED_MEDIUM, but a null silpi never bars."""
    result = run_gate(enterprise_class="MEDIUM", investment_cr=Decimal("200"), turnover_cr=Decimal("700"))
    assert result.status == STATUS_EXCLUDED_MEDIUM


def test_precedence_trader_beats_medium():
    result = run_gate(
        enterprise_class="MEDIUM", investment_cr=Decimal("200"), turnover_cr=Decimal("700"),
        nic_codes=["45200"],
    )
    assert result.status == STATUS_EXCLUDED_TRADER


def test_precedence_medium_beats_insufficient_data():
    result = run_gate(enterprise_class="MEDIUM", investment_cr=Decimal("200"), turnover_cr=Decimal("700"))
    # Silpi is null (would be insufficient data) but medium is a harder block.
    assert result.status == STATUS_EXCLUDED_MEDIUM


def test_precedence_silpi_would_outrank_everything_when_set():
    cfg = make_config(silpi_test_date={"value": "SUPPLY", "source_ref": "V4", "verified": False, "note": ""})
    result = run_gate(cfg, nic_codes=["45200"], enterprise_class="MEDIUM",
                      investment_cr=Decimal("200"), turnover_cr=Decimal("700"))
    # With silpi decidable there is no silpi bar here, so the trader block wins.
    assert result.status == STATUS_EXCLUDED_TRADER
    assert check(result, CHECK_SILPI_CHRONOLOGY).passed is True


def test_insufficient_data_when_supply_date_missing():
    result = run_gate(supply_date=None)
    assert result.status == STATUS_INSUFFICIENT_DATA
    assert result.eligible is False
    assert check(result, CHECK_ENTERPRISE_CLASS).passed is None


def test_insufficient_data_when_class_unknown_and_no_figures():
    result = run_gate(enterprise_class="UNKNOWN", investment_cr=None, turnover_cr=None)
    assert result.status == STATUS_INSUFFICIENT_DATA
    assert check(result, CHECK_ENTERPRISE_CLASS).passed is None


def test_stated_small_with_no_figures_passes_but_is_an_assumption():
    result = run_gate(investment_cr=None, turnover_cr=None)
    assert check(result, CHECK_ENTERPRISE_CLASS).passed is True
    assert any("the case says so" in a for a in result.assumptions)


def test_activity_match_is_a_risk_flag_only():
    """Section 6.1: activity_match never blocks.

    An unmatched NIC with a TRADING activity disagrees (activity_match False). The
    trading exclusion cannot decide either, so it reports undecidable with a
    TRADING_EVIDENCE_CONFLICT warning rather than excluding on one source.
    """
    result = run_gate(nic_codes=["99999"], activity="TRADING")
    assert check(result, CHECK_ACTIVITY_MATCH).passed is False
    assert check(result, CHECK_TRADER_EXCLUSION).passed is None
    assert any(w.code == WARNING_TRADING_EVIDENCE_CONFLICT for w in result.warnings)
    assert STATUS_EXCLUDED_TRADER not in result.status


def test_trading_label_with_no_nic_codes_excludes_on_the_stated_activity():
    """A TRADING activity with no NIC codes to check against is the exclusion
    on its own terms, with the missing codes named in the detail."""
    result = run_gate(nic_codes=[], activity="TRADING")
    assert check(result, CHECK_TRADER_EXCLUSION).passed is False
    assert "No NIC codes" in check(result, CHECK_TRADER_EXCLUSION).detail
    assert STATUS_EXCLUDED_TRADER in result.status


def test_activity_match_missing_data_is_info_not_a_block():
    result = run_gate(nic_codes=[], activity="")
    flag = check(result, CHECK_ACTIVITY_MATCH)
    assert flag.passed is None
    assert any(w.code == "MISSING_ACTIVITY_DATA" and w.severity == "INFO" for w in result.warnings)


# ------------------------------------------- reverse graduation boundary ----


def test_reverse_graduation_on_the_2025_04_01_boundary():
    """The same supplier can pass the enterprise check before 2025-04-01 and
    fail it after.

    Under the earlier (undated) epoch the small ceilings are 10/50 crore; under
    the 2025-04-01 epoch they are 25/100 crore. A supplier at 20 crore investment
    and 80 crore turnover is over the earlier ceilings but within the later ones,
    so the same supplier fails the check on a 2025-03-31 supply and passes it on a
    2025-04-01 supply (golden rule 1: the date of supply picks the epoch, no
    regimes). The overall status stays INSUFFICIENT_DATA because silpi_test_date
    is null; the enterprise check carries the graduation.
    """
    cfg = make_config()
    before = run_gate(cfg, supply_date=date(2025, 3, 31),
                      investment_cr=Decimal("20"), turnover_cr=Decimal("80"))
    after = run_gate(cfg, supply_date=date(2025, 4, 1),
                     investment_cr=Decimal("20"), turnover_cr=Decimal("80"))
    assert check(before, CHECK_ENTERPRISE_CLASS).passed is False
    assert check(after, CHECK_ENTERPRISE_CLASS).passed is True
    # The failing check names the ceilings it measured against, and where the
    # reverse graduation comes from.
    assert "2025-03-31" in check(before, CHECK_ENTERPRISE_CLASS).detail
    assert "reverse graduation" in check(before, CHECK_ENTERPRISE_CLASS).detail.lower()
    assert check(after, CHECK_ENTERPRISE_CLASS).passed is not None
    detail = check(after, CHECK_ENTERPRISE_CLASS).detail
    assert "2025-04-01" in detail


def test_just_under_the_new_ceiling_still_passes_after_the_boundary():
    result = run_gate(supply_date=date(2025, 4, 1),
                      investment_cr=Decimal("25"), turnover_cr=Decimal("100"))
    assert check(result, CHECK_ENTERPRISE_CLASS).passed is True


def test_just_over_the_new_ceiling_fails_after_the_boundary():
    result = run_gate(supply_date=date(2025, 4, 1),
                      investment_cr=Decimal("25.01"), turnover_cr=Decimal("100"))
    assert check(result, CHECK_ENTERPRISE_CLASS).passed is False


def test_missing_size_epoch_is_insufficient_data_not_a_pass():
    """No epoch covers the date, so the gate will not guess a ceiling."""
    cfg = make_config()
    # Remove the undated fallback so an early date has nothing to match.
    cfg._size_epochs = [e for e in cfg._size_epochs if e.from_date is not None]
    result = run_gate(cfg, supply_date=date(2020, 1, 1))
    assert result.status == STATUS_INSUFFICIENT_DATA
    assert check(result, CHECK_ENTERPRISE_CLASS).passed is None
    assert any(w.code == WARNING_NO_SIZE_EPOCH for w in result.warnings)


def test_supply_date_defaults_are_not_applied_inside_the_gate():
    """The gate takes supply_date explicitly; it never reaches for delivery_date."""
    result = run_gate(supply_date=None)
    # A missing supply date is reported as missing, not silently backfilled.
    assert "supply date" in check(result, CHECK_ENTERPRISE_CLASS).detail.lower()


# ------------------------------------------------------- contract shape ----


def test_result_validates_against_the_frozen_models():
    from backend.app.schemas import Citation, Jurisdiction, JurisdictionCheck, JurisdictionStatus, Warning

    for kwargs in (
        {},
        {"enterprise_class": "MEDIUM", "investment_cr": Decimal("200"), "turnover_cr": Decimal("700")},
        {"nic_codes": ["45200"]},
        {"supply_date": None},
        {"enterprise_class": "UNKNOWN", "investment_cr": None, "turnover_cr": None},
    ):
        result = run_gate(**kwargs)
        jurisdiction = Jurisdiction(
            status=JurisdictionStatus(result.status),
            eligible=result.eligible,
            checks=[
                JurisdictionCheck(id=c.id, passed=c.passed, detail=c.detail, rule_ref=c.rule_ref)
                for c in result.checks
            ],
            alternative_remedy=result.alternative_remedy,
        )
        assert jurisdiction.status == JurisdictionStatus(result.status)
        for citation in result.citations:
            Citation(**citation.to_dict())
        for warning in result.warnings:
            Warning(**warning.to_dict())


def test_blocked_result_reports_downstream_must_be_null_not_zero():
    from backend.engine.gate import blocked_downstream_note

    result = run_gate(enterprise_class="MEDIUM", investment_cr=Decimal("200"), turnover_cr=Decimal("700"))
    note = blocked_downstream_note(result)
    assert note.severity == "BLOCK"
    assert "not because the amounts are zero" in note.text
