"""Dev tests for backend/engine/config.py (the engine author's own smoke tests).

Covers: missing keys fail fast, epoch lookup on boundary dates, usage tracking,
and STRICT_VERIFIED strict mode. Round numbers so every expectation is
hand-checkable.

These are NOT the spec tests in tests/spec/; those come from the independent test
author and must pass without this module.
"""

from datetime import date
from decimal import Decimal

import pytest

from backend.engine.config import (
    REQUIRED_KEYS,
    ConfigError,
    NoEpochFound,
    StatuteConfig,
    StrictVerificationError,
    WARNING_UNVERIFIED_CONSTANT,
)


def make_config(**overrides):
    """A minimal valid config dict; override any key to build a broken variant."""
    base = {
        "interest_multiplier": {"value": 3, "source_ref": "V2:s.16", "verified": False, "note": ""},
        "objection_window_days": {"value": 15, "source_ref": "V2:s.2(b)", "verified": False, "note": ""},
        "credit_cap_days": {"value": 45, "source_ref": "V2:s.15 proviso", "verified": False, "note": ""},
        "no_agreement_days": {"value": 15, "source_ref": "V2:s.15", "verified": False, "note": ""},
        "bank_rate_epochs": {
            "value": [
                {"from": "2026-04-01", "bank_rate_pct": "5.50"},
                {"from": "2026-10-07", "bank_rate_pct": "5.75"},
            ],
            "source_ref": "V1",
            "verified": False,
            "note": "",
        },
        "size_epochs": {
            "value": [
                {"from": "2025-04-01", "micro": {"investment_cr": "2.5", "turnover_cr": "10"},
                 "small": {"investment_cr": "25", "turnover_cr": "100"},
                 "medium": {"investment_cr": "125", "turnover_cr": "500"}},
                {"from": None, "micro": {"investment_cr": "1", "turnover_cr": "5"},
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
        "tax_presets": {
            "value": [
                {"id": "company_115baa", "label": "Company (s.115BAA)", "tax_rate_pct": "25.168"},
                {"id": "other", "label": "Other", "tax_rate_pct": "31.2"},
            ],
            "source_ref": "V3",
            "verified": False,
            "note": "",
        },
        "gated_features": {
            "value": {"gst_itc_180d": False, "msme1_return": False, "s19_deposit": False},
            "source_ref": "V9",
            "verified": False,
            "note": "",
        },
    }
    base.update(overrides)
    return base


# ------------------------------------------------------- missing keys -------


def test_every_required_key_is_present_in_the_real_config():
    """The shipped statute_config.json must carry every documented key.

    Extra sections are allowed only when they are declared below, so a typo in a
    key name or a stray hand-edit still fails loudly. The API-level sections (v4
    provider settings and the v5 `insights` product settings) are read by the API
    layer (`GET /api/v1/config`) rather than `StatuteConfig`, whose REQUIRED_KEYS
    stays the engine's own set (documents/architecture_v4_two_options.md section 9).
    """
    import json
    from pathlib import Path

    api_sections = {"treds", "financing", "mock_financing", "insights"}

    path = Path(__file__).resolve().parents[2] / "config" / "statute_config.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    real_keys = {k for k in data if not k.startswith("_")}
    assert set(REQUIRED_KEYS) <= real_keys, f"missing: {set(REQUIRED_KEYS) - real_keys}"
    unexpected = real_keys - set(REQUIRED_KEYS) - api_sections
    assert not unexpected, f"undocumented config sections: {sorted(unexpected)}"

    # The API-level sections the file does carry must still look like config entries.
    for key in sorted(real_keys & api_sections):
        entry = data[key]
        assert set(entry) == {"value", "source_ref", "verified", "note"}, (
            f"{key} must be a {{value, source_ref, verified, note}} entry, got {sorted(entry)}"
        )
        assert entry["verified"] is False, (
            f"{key} is an unverified v4 constant and must ship with verified=false"
        )


@pytest.mark.parametrize("key", sorted(REQUIRED_KEYS))
def test_missing_key_fails_fast(key):
    broken = make_config()
    del broken[key]
    with pytest.raises(ConfigError, match=key):
        StatuteConfig.from_dict(broken)


def test_missing_entry_field_fails_fast():
    broken = make_config()
    del broken["credit_cap_days"]["verified"]
    with pytest.raises(ConfigError, match="verified"):
        StatuteConfig.from_dict(broken)


def test_non_object_config_fails_fast():
    with pytest.raises(ConfigError):
        StatuteConfig.from_dict(["not", "a", "dict"])


def test_real_config_loads():
    """The shipped file must be structurally valid, not just key-complete."""
    import json
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "config" / "statute_config.json"
    cfg = StatuteConfig.from_dict(json.loads(path.read_text(encoding="utf-8")))
    assert cfg.interest_multiplier() == Decimal("3")
    assert cfg.credit_cap_days() == 45


# ----------------------------------------------- epoch boundary lookup ------


def test_bank_rate_on_boundary_dates():
    cfg = StatuteConfig.from_dict(make_config())
    # Day before the first epoch: nothing covers it.
    with pytest.raises(NoEpochFound):
        cfg.bank_rate_on(date(2026, 3, 31))
    # First day of the 5.50 epoch, and its last day before the change.
    assert cfg.bank_rate_on(date(2026, 4, 1)) == Decimal("5.50")
    assert cfg.bank_rate_on(date(2026, 10, 6)) == Decimal("5.50")
    # First day of the 5.75 epoch, and far future.
    assert cfg.bank_rate_on(date(2026, 10, 7)) == Decimal("5.75")
    assert cfg.bank_rate_on(date(2030, 1, 1)) == Decimal("5.75")


def test_statutory_rate_is_multiplier_times_bank_rate():
    cfg = StatuteConfig.from_dict(make_config())
    # 3 x 5.50 = 16.50 on the 5.50 epoch.
    assert cfg.statutory_rate_on(date(2026, 4, 1)) == Decimal("16.50")
    # 3 x 5.75 = 17.25 once 5.75 is in force.
    assert cfg.statutory_rate_on(date(2026, 10, 7)) == Decimal("17.25")


def test_size_limits_on_boundary_dates():
    cfg = StatuteConfig.from_dict(make_config())
    # Before the dated epoch, the undated fallback (1/5, 10/50, 50/250) applies.
    early = cfg.size_limits_on(date(2020, 1, 1))
    assert early.small.investment_cr == Decimal("10")
    assert early.small.turnover_cr == Decimal("50")
    # On the dated epoch boundary and after, the 2025-04-01 set applies.
    current = cfg.size_limits_on(date(2025, 4, 1))
    assert current.small.investment_cr == Decimal("25")
    assert current.small.turnover_cr == Decimal("100")
    assert current.medium.investment_cr == Decimal("125")
    assert cfg.size_limits_on(date(2026, 6, 1)).micro.investment_cr == Decimal("2.5")


# ------------------------------------------------------- usage tracking -----


def test_no_warnings_when_nothing_used():
    cfg = StatuteConfig.from_dict(make_config())
    assert cfg.warnings() == []
    assert cfg.used_keys == frozenset()


def test_lookup_records_only_the_keys_it_used():
    cfg = StatuteConfig.from_dict(make_config())
    cfg.bank_rate_on(date(2026, 5, 1))
    # bank_rate_epochs used; interest_multiplier untouched by bank_rate_on alone.
    assert cfg.used_keys == frozenset({"bank_rate_epochs"})
    cfg.statutory_rate_on(date(2026, 5, 1))
    assert cfg.used_keys == frozenset({"bank_rate_epochs", "interest_multiplier"})


def test_unverified_used_constant_warns():
    cfg = StatuteConfig.from_dict(make_config())
    cfg.bank_rate_on(date(2026, 5, 1))
    warnings = cfg.warnings()
    assert len(warnings) == 1
    assert warnings[0].code == WARNING_UNVERIFIED_CONSTANT
    assert "bank_rate_epochs" in warnings[0].text
    assert warnings[0].to_dict()["severity"] == "WARN"


def test_verified_constant_produces_no_warning():
    verified = make_config()
    verified["bank_rate_epochs"]["verified"] = True
    cfg = StatuteConfig.from_dict(verified)
    cfg.bank_rate_on(date(2026, 5, 1))
    assert cfg.warnings() == []


def test_null_value_always_warns_even_if_verified():
    """A null is missing data, so it warns even when marked verified."""
    nulls = make_config()
    nulls["limitation_years"]["value"] = None
    nulls["limitation_years"]["verified"] = True
    cfg = StatuteConfig.from_dict(nulls)
    assert cfg.limitation_years() is None
    assert any("limitation_years" in w.text for w in cfg.warnings())


def test_reset_usage_clears_warnings():
    cfg = StatuteConfig.from_dict(make_config())
    cfg.bank_rate_on(date(2026, 5, 1))
    assert cfg.warnings()
    cfg.reset_usage()
    assert cfg.warnings() == []
    assert cfg.used_keys == frozenset()


def test_unmatched_size_lookup_records_no_usage():
    """A date no epoch covers must not report a constant it never used."""
    dated_only = make_config()
    dated_only["size_epochs"]["value"] = [dated_only["size_epochs"]["value"][0]]
    cfg = StatuteConfig.from_dict(dated_only)
    assert cfg.size_limits_on(date(1999, 1, 1)) is None
    assert "size_epochs" not in cfg.used_keys


def test_tax_preset_records_usage_on_hit_only():
    cfg = StatuteConfig.from_dict(make_config())
    assert cfg.tax_preset("nope") is None
    assert "tax_presets" not in cfg.used_keys
    preset = cfg.tax_preset("other")
    assert preset.tax_rate_pct == Decimal("31.2")
    assert "tax_presets" in cfg.used_keys


# ----------------------------------------------------------- strict mode ----


def test_strict_check_raises_when_unverified_constant_used():
    cfg = StatuteConfig.from_dict(make_config())
    cfg.bank_rate_on(date(2026, 5, 1))
    with pytest.raises(StrictVerificationError, match="bank_rate_epochs"):
        cfg.strict_check()


def test_strict_check_passes_when_everything_used_is_verified():
    verified = make_config()
    for key in ("bank_rate_epochs", "interest_multiplier"):
        verified[key]["verified"] = True
    cfg = StatuteConfig.from_dict(verified)
    cfg.statutory_rate_on(date(2026, 5, 1))
    cfg.strict_check()  # must not raise


def test_strict_check_passes_when_nothing_used():
    StatuteConfig.from_dict(make_config()).strict_check()


def test_env_flag_reads_strict_verified(monkeypatch):
    """STRICT_VERIFIED=1 is the documented switch (section 5)."""
    from backend.engine import env

    monkeypatch.setenv("STRICT_VERIFIED", "1")
    assert env.strict_verified_enabled() is True
    monkeypatch.delenv("STRICT_VERIFIED")
    assert env.strict_verified_enabled() is False
    monkeypatch.setenv("STRICT_VERIFIED", "0")
    assert env.strict_verified_enabled() is False
