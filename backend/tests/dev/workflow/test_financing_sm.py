"""The financing transition table, exhaustively.

Every (state, event) pair is asserted, not a sample: a table this central is either
complete or it is a source of 500s. Guards get their own cases.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from backend.app.schemas_v4 import TrackState
from backend.workflow import financing_sm
from backend.workflow.financing_sm import (
    CANCELLABLE_STATES,
    TERMINAL_STATES,
    TRANSITIONS,
    FinancingEvent,
    GuardContext,
    InvalidTransition,
    allowed_events,
    transition,
)

ALL_STATES = list(TrackState)
ALL_EVENTS = list(FinancingEvent)


def test_the_table_covers_every_declared_transition():
    report = financing_sm.validate_table()
    assert report["dangling"] == [], "a transition points at a state that does not exist"
    assert report["leaving_terminal"] == [], "a terminal state must have no outgoing rows"
    assert report["transitions"] == len(TRANSITIONS) == 19


@pytest.mark.parametrize(("state", "event"), sorted(TRANSITIONS, key=lambda p: (p[0].value, p[1].value)))
def test_every_allowed_transition(state, event):
    """The table's own rows are exactly what `transition` returns."""
    expected = TRANSITIONS[(state, event)]
    context = GuardContext(
        now=datetime(2026, 10, 25, 9, 0, tzinfo=UTC),
        bid_valid_until=datetime(2026, 10, 26, 9, 0, tzinfo=UTC),
        esign_attempts=0,
        bid_window_reopens=0,
    )
    assert transition(state, event, context) is expected


@pytest.mark.parametrize(("state", "event"), [(s, e) for s in ALL_STATES for e in ALL_EVENTS])
def test_every_pair_is_either_allowed_or_refused(state, event):
    """No pair may be silently accepted, and none may crash with something else."""
    context = GuardContext(
        now=datetime(2026, 10, 25, 9, 0, tzinfo=UTC),
        bid_valid_until=datetime(2026, 10, 26, 9, 0, tzinfo=UTC),
        esign_attempts=0,
        bid_window_reopens=0,
    )
    allowed = (state, event) in TRANSITIONS
    if event is FinancingEvent.USER_CANCEL:
        allowed = state in CANCELLABLE_STATES
    if allowed:
        assert transition(state, event, context) in TrackState
    else:
        with pytest.raises(InvalidTransition):
            transition(state, event, context)


def test_cancel_is_allowed_from_every_pre_signature_state():
    for state in CANCELLABLE_STATES:
        assert transition(state, FinancingEvent.USER_CANCEL) is TrackState.CANCELLED


def test_cancel_is_refused_after_signature():
    for state in (
        TrackState.AWAITING_DISBURSEMENT,
        TrackState.DISBURSED,
        TrackState.SETTLED,
        TrackState.DISBURSEMENT_FAILED,
    ):
        with pytest.raises(InvalidTransition, match="can no longer be cancelled"):
            transition(state, FinancingEvent.USER_CANCEL)


@pytest.mark.parametrize("state", sorted(TERMINAL_STATES, key=lambda s: s.value))
def test_a_terminal_state_refuses_every_event(state):
    for event in ALL_EVENTS:
        if event is FinancingEvent.USER_CANCEL and state in CANCELLABLE_STATES:
            continue
        with pytest.raises(InvalidTransition):
            transition(state, event)


def test_allowed_events_lists_what_the_table_permits():
    assert allowed_events(TrackState.BIDS_AVAILABLE) == [
        "bidding_closed",
        "bids_expired",
        "select_bid",
        "user_cancel",
    ]
    assert allowed_events(TrackState.NEW) == [
        "check_financeability",
        "financeability_failed",
        "user_cancel",
    ]
    assert allowed_events(TrackState.SETTLED) == []


# ---------------------------------------------------------------- guards ----


def test_an_expired_bid_cannot_be_selected():
    ctx = GuardContext(
        now=datetime(2026, 10, 27, 9, 0, tzinfo=UTC),
        bid_valid_until=datetime(2026, 10, 26, 9, 0, tzinfo=UTC),
    )
    with pytest.raises(InvalidTransition, match="bid has expired"):
        transition(TrackState.BIDS_AVAILABLE, FinancingEvent.SELECT_BID, ctx)


def test_a_bid_valid_exactly_now_is_still_selectable():
    """Expiry is `now > valid_until`, so the boundary instant is inside the window."""
    moment = datetime(2026, 10, 26, 9, 0, tzinfo=UTC)
    ctx = GuardContext(now=moment, bid_valid_until=moment)
    assert transition(TrackState.BIDS_AVAILABLE, FinancingEvent.SELECT_BID, ctx) is TrackState.AWAITING_ESIGN


def test_the_bid_window_may_reopen_exactly_once():
    first = GuardContext(bid_window_reopens=0)
    assert transition(TrackState.BIDS_AVAILABLE, FinancingEvent.BIDS_EXPIRED, first) is TrackState.BIDDING_OPEN

    second = GuardContext(bid_window_reopens=1)
    with pytest.raises(InvalidTransition, match="already been re-opened"):
        transition(TrackState.BIDS_AVAILABLE, FinancingEvent.BIDS_EXPIRED, second)


@pytest.mark.parametrize("attempts", [0, 1, 2])
def test_esign_may_be_retried_before_the_ceiling(attempts):
    ctx = GuardContext(esign_attempts=attempts)
    assert transition(TrackState.AWAITING_ESIGN, FinancingEvent.ESIGN_FAILED, ctx) is TrackState.BIDS_AVAILABLE


def test_esign_stops_at_three_attempts():
    ctx = GuardContext(esign_attempts=3)
    with pytest.raises(InvalidTransition, match="3 attempts"):
        transition(TrackState.AWAITING_ESIGN, FinancingEvent.ESIGN_EXPIRED, ctx)


def test_the_not_financeable_branch_is_a_separate_event():
    """A deterministic table cannot branch on one event, so the branch is explicit."""
    assert transition(TrackState.NEW, FinancingEvent.CHECK_FINANCEABILITY) is TrackState.FINANCEABLE
    assert transition(TrackState.NEW, FinancingEvent.FINANCEABILITY_FAILED) is TrackState.NOT_FINANCEABLE


def test_the_happy_path_end_to_end():
    """NEW -> ... -> DISBURSED, one documented event at a time."""
    state = TrackState.NEW
    now = datetime(2026, 10, 25, 9, 0, tzinfo=UTC)
    ctx = GuardContext(now=now, bid_valid_until=now + timedelta(days=1))
    for event in (
        FinancingEvent.CHECK_FINANCEABILITY,
        FinancingEvent.REQUEST_BUYER_ACCEPTANCE,
        FinancingEvent.BUYER_ACCEPTED,
        FinancingEvent.BIDS_RECEIVED,
        FinancingEvent.SELECT_BID,
        FinancingEvent.ESIGN_COMPLETED,
        FinancingEvent.PAYOUT_PROCESSED,
    ):
        state = transition(state, event, ctx)
    assert state is TrackState.DISBURSED
