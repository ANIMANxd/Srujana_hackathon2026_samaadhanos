"""Dev tests for backend/engine/limitation.py (the engine author's smoke tests).

Covers: every status band including the month boundaries, a null limitation
period, a missing due date, restarts by signed confirmation and part-payment,
and WhatsApp promises that are recorded but never restart the clock.

Every expected date is hand-computed in a comment. These are NOT the spec tests
in tests/spec/.
"""

from datetime import date

from backend.engine.limitation import (
    WARNING_MISSING_LIMITATION_YEARS,
    WARNING_NO_DUE_DATE,
    WARNING_POTENTIAL_ACKNOWLEDGMENT,
    STATUS_EXPIRED,
    STATUS_OK,
    STATUS_UNKNOWN,
    STATUS_WARN_12M,
    STATUS_WARN_6M,
    evaluate_limitation,
)
from backend.tests.dev.test_gate import make_config

# Anchors used throughout: due 2024-06-15, three-year period, so the expiry is
# 2027-06-15 unless an acknowledgment moves it.
DUE = date(2024, 6, 15)
EXPIRY = date(2027, 6, 15)


def cfg_years(years=3):
    """A config whose limitation period is exactly `years`."""
    cfg = make_config()
    cfg._entries["limitation_years"]["value"] = years
    return cfg


class Ack:
    """Minimal acknowledgment satisfying AcknowledgmentLike."""

    def __init__(self, when, kind, signed=True, ref=None):
        self.date = when
        self.kind = kind
        self.is_signed = signed
        self.source_ref = ref


def run(cfg=None, **kwargs):
    """Due 2024-06-15, three-year period, calculated 2026-01-01."""
    facts = dict(
        due_date=DUE,
        calculation_date=date(2026, 1, 1),
        acknowledgments=[],
    )
    facts.update(kwargs)
    return evaluate_limitation(cfg or cfg_years(), **facts)


def event(result, when):
    return next(e for e in result.events if e.date == when)


# ------------------------------------------------------------ expiry and bands ----


def test_expiry_is_due_date_plus_limitation_years():
    """2024-06-15 plus 3 years = 2027-06-15."""
    assert run().expiry == EXPIRY


def test_status_ok_when_more_than_twelve_months_remain():
    # 2026-06-15 is exactly twelve months before the expiry.
    assert run(calculation_date=date(2026, 6, 14)).status == STATUS_OK


def test_status_warn_12m_at_the_twelve_month_boundary():
    # Exactly twelve months out: 2026-06-15 + 12m = 2027-06-15 = expiry.
    assert run(calculation_date=date(2026, 6, 15)).status == STATUS_WARN_12M
    assert run(calculation_date=date(2026, 7, 1)).status == STATUS_WARN_12M


def test_status_warn_6m_at_the_six_month_boundary():
    # 2026-12-15 + 6m = 2027-06-15 = expiry (boundary counts as within six months).
    assert run(calculation_date=date(2026, 12, 15)).status == STATUS_WARN_6M
    # One day earlier is still seven months out.
    assert run(calculation_date=date(2026, 12, 14)).status == STATUS_WARN_12M


def test_status_expired_only_after_the_expiry_date():
    """The expiry day itself is still in time (CQ-25)."""
    assert run(calculation_date=date(2027, 6, 15)).status == STATUS_WARN_6M
    assert run(calculation_date=date(2027, 6, 16)).status == STATUS_EXPIRED


def test_expired_stays_expired_when_long_past():
    assert run(calculation_date=date(2030, 1, 1)).status == STATUS_EXPIRED


def test_null_limitation_years_is_unknown_with_a_warning():
    """Section 6.5: no configured period means UNKNOWN, never a comfortable OK."""
    cfg = make_config()  # limitation_years is null in the shipped config
    result = run(cfg)
    assert result.status == STATUS_UNKNOWN
    assert result.expiry is None
    warning = next(w for w in result.warnings if w.code == WARNING_MISSING_LIMITATION_YEARS)
    assert "not a finding that there is plenty of time left" in warning.text
    assert any("UNKNOWN means the inputs do not support a date" in a for a in result.assumptions)


def test_null_due_date_is_unknown_with_a_warning():
    result = run(due_date=None)
    assert result.status == STATUS_UNKNOWN
    assert result.expiry is None
    assert any(w.code == WARNING_NO_DUE_DATE for w in result.warnings)


def test_null_due_date_lets_the_assertion_stay_honest():
    joined = " ".join(run(due_date=None).assumptions)
    assert "UNKNOWN means the inputs do not support a date" in joined


# ------------------------------------------------------------ restarts ----


def test_signed_balance_confirmation_restarts_the_clock():
    """Restarted 2025-06-15, so the expiry becomes 2028-06-15."""
    result = run(acknowledgments=[Ack(date(2025, 6, 15), "SIGNED_BALANCE_CONFIRMATION")])
    assert result.expiry == date(2028, 6, 15)
    assert event(result, date(2025, 6, 15)).restarts_clock is True


def test_part_payment_restarts_the_clock():
    result = run(acknowledgments=[Ack(date(2025, 3, 1), "PART_PAYMENT")])
    assert result.expiry == date(2028, 3, 1)
    assert event(result, date(2025, 3, 1)).restarts_clock is True


def test_an_unsigned_confirmation_does_not_restart():
    result = run(
        acknowledgments=[Ack(date(2025, 6, 15), "SIGNED_BALANCE_CONFIRMATION", signed=False)]
    )
    assert result.expiry == EXPIRY
    assert event(result, date(2025, 6, 15)).restarts_clock is False


def test_an_unsigned_part_payment_does_not_restart():
    """Section 6.5 asks for is_signed true AND a qualifying kind, both of them."""
    result = run(acknowledgments=[Ack(date(2025, 3, 1), "PART_PAYMENT", signed=False)])
    assert result.expiry == EXPIRY
    assert event(result, date(2025, 3, 1)).restarts_clock is False


def test_whatsapp_promise_never_restarts_but_is_recorded():
    result = run(acknowledgments=[Ack(date(2025, 6, 15), "WHATSAPP_PROMISE", signed=False)])
    assert result.expiry == EXPIRY
    assert event(result, date(2025, 6, 15)).restarts_clock is False
    warning = next(w for w in result.warnings if w.code == WARNING_POTENTIAL_ACKNOWLEDGMENT)
    assert "2025-06-15" in warning.text
    assert "do not restart" in warning.text
    assert warning.severity == "INFO"


def test_a_signed_whatsapp_promise_still_does_not_restart():
    """Being signed does not promote a chat promise to a qualifying kind."""
    result = run(acknowledgments=[Ack(date(2025, 6, 15), "WHATSAPP_PROMISE", signed=True)])
    assert result.expiry == EXPIRY
    assert event(result, date(2025, 6, 15)).restarts_clock is False


def test_an_acknowledgment_before_the_due_date_does_not_shorten_the_window():
    """Signed 2024-01-01, before the due date: the clock cannot be pulled back."""
    result = run(acknowledgments=[Ack(date(2024, 1, 1), "SIGNED_BALANCE_CONFIRMATION")])
    assert result.expiry == EXPIRY  # not 2027-01-01
    assert event(result, date(2024, 1, 1)).restarts_clock is False


def test_an_acknowledgment_after_the_calculation_date_is_ignored():
    """The evaluation cannot act on something that has not happened yet."""
    result = run(
        calculation_date=date(2026, 1, 1),
        acknowledgments=[Ack(date(2026, 6, 1), "SIGNED_BALANCE_CONFIRMATION")],
    )
    assert result.expiry == EXPIRY
    assert event(result, date(2026, 6, 1)).restarts_clock is False


def test_the_latest_qualifying_acknowledgment_wins():
    """Two qualifying acknowledgments: the later one sets the anchor.

    2025-03-01 + 3 years = 2028-03-01.
    """
    result = run(
        acknowledgments=[
            Ack(date(2025, 1, 1), "SIGNED_BALANCE_CONFIRMATION"),
            Ack(date(2025, 3, 1), "PART_PAYMENT"),
        ]
    )
    assert result.expiry == date(2028, 3, 1)


def test_acknowledgments_are_processed_in_date_order_not_input_order():
    result = run(
        acknowledgments=[
            Ack(date(2025, 6, 1), "PART_PAYMENT"),
            Ack(date(2025, 2, 1), "SIGNED_BALANCE_CONFIRMATION"),
        ]
    )
    assert result.expiry == date(2028, 6, 1)


def test_earlier_restart_does_not_block_a_later_one():
    """After restarting on 2025-02-01, a later 2025-05-01 restarts again."""
    result = run(
        acknowledgments=[
            Ack(date(2025, 2, 1), "SIGNED_BALANCE_CONFIRMATION"),
            Ack(date(2025, 5, 1), "PART_PAYMENT"),
        ]
    )
    assert result.expiry == date(2028, 5, 1)


def test_a_restart_moved_past_the_calculation_date_changes_the_band():
    """Restarted 2026-06-01 -> expiry 2029-06-01, well beyond twelve months."""
    result = run(
        calculation_date=date(2026, 7, 1),
        acknowledgments=[Ack(date(2026, 6, 1), "SIGNED_BALANCE_CONFIRMATION")],
    )
    assert result.expiry == date(2029, 6, 1)
    assert result.status == STATUS_OK


# ------------------------------------------------------------ events ----


def test_every_acknowledgment_appears_as_an_event():
    result = run(
        acknowledgments=[
            Ack(date(2025, 1, 1), "SIGNED_BALANCE_CONFIRMATION"),
            Ack(date(2025, 2, 1), "WHATSAPP_PROMISE", signed=False),
            Ack(date(2025, 3, 1), "PART_PAYMENT"),
        ]
    )
    assert [(e.date, e.kind, e.restarts_clock) for e in result.events] == [
        (date(2025, 1, 1), "SIGNED_BALANCE_CONFIRMATION", True),
        (date(2025, 2, 1), "WHATSAPP_PROMISE", False),
        (date(2025, 3, 1), "PART_PAYMENT", True),
    ]


def test_no_acknowledgments_gives_an_empty_event_list():
    assert run().events == []


def test_no_due_date_means_nothing_can_restart():
    """There is no clock to move, so every event reads as not restarting."""
    result = run(
        due_date=None,
        acknowledgments=[Ack(date(2025, 6, 15), "SIGNED_BALANCE_CONFIRMATION")],
    )
    assert result.events[0].restarts_clock is False


# ------------------------------------------------------------ leap-year dates ----


def test_expiry_clamps_a_leap_anniversary():
    """Due 2024-02-29 plus one year lands on 2025-02-28."""
    result = evaluate_limitation(
        cfg_years(1), due_date=date(2024, 2, 29), calculation_date=date(2026, 1, 1)
    )
    assert result.expiry == date(2025, 2, 28)
    assert result.status == STATUS_EXPIRED  # calculated long after it


def test_expiry_keeps_29_february_when_the_year_is_a_leap_year():
    """Due 2024-02-29 plus four years lands on 2028-02-29 (2028 is a leap year)."""
    result = evaluate_limitation(
        cfg_years(4), due_date=date(2024, 2, 29), calculation_date=date(2026, 1, 1)
    )
    assert result.expiry == date(2028, 2, 29)
    # 2026-01-01 to 2028-02-29 is about twenty-six months out, so still OK.
    assert result.status == STATUS_OK
    # Inside twelve months but not six: 2027-03-01 + 12m = 2028-03-01 covers it,
    # while + 6m = 2027-09-01 does not.
    within = evaluate_limitation(
        cfg_years(4), due_date=date(2024, 2, 29), calculation_date=date(2027, 3, 1)
    )
    assert within.status == STATUS_WARN_12M


# ------------------------------------------------------------ citations and shape ----


def test_limitation_years_is_cited_with_its_source():
    result = run()
    citation = next(c for c in result.citations if c.config_key == "limitation_years")
    assert citation.statute_ref  # V7
    assert citation.id == "limitation.limitation_years"
    assert citation.verified is False  # statute sheet not captured yet


def test_the_read_constant_is_reported_as_unverified():
    cfg = cfg_years()
    run(cfg)
    assert "limitation_years" in cfg.used_keys
    assert any("limitation_years" in w.text for w in cfg.warnings())


def test_assumptions_state_the_restart_rule():
    joined = " ".join(run().assumptions)
    assert "signed balance confirmation or a part-payment" in joined
    assert "never shorten" in joined
    assert "after the calculation date" in joined
    assert "calendar months" in joined


def test_result_validates_against_the_frozen_limitation_model():
    from backend.app.schemas import Limitation, LimitationStatus

    for kwargs in (
        {},
        {"acknowledgments": [Ack(date(2025, 6, 15), "SIGNED_BALANCE_CONFIRMATION")]},
        {"acknowledgments": [Ack(date(2025, 6, 15), "WHATSAPP_PROMISE", signed=False)]},
        {"calculation_date": date(2027, 6, 16)},
        {"due_date": None},
        {"due_date": date(2024, 2, 29)},
    ):
        result = run(**kwargs)
        model = Limitation(**result.to_dict())
        assert model.status == LimitationStatus(result.status)
        assert len(model.events) == len(result.events)
        if result.expiry is None:
            assert model.expiry is None
        else:
            assert model.expiry == result.expiry


def test_null_years_from_the_shipped_config_is_unknown_not_a_date():
    """The real config ships limitation_years as null (V7 uncaptured)."""
    import json
    from pathlib import Path

    from backend.engine.config import StatuteConfig

    path = Path(__file__).resolve().parents[2] / "config" / "statute_config.json"
    cfg = StatuteConfig.from_dict(json.loads(path.read_text(encoding="utf-8")))
    result = evaluate_limitation(
        cfg, due_date=DUE, calculation_date=date(2026, 1, 1)
    )
    assert result.status == STATUS_UNKNOWN
    assert result.expiry is None
