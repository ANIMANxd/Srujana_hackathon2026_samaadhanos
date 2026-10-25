"""The recovery transition table, exhaustively, plus the no-auto-send invariant."""

from __future__ import annotations

import pytest

from backend.app.schemas_v4 import TrackState
from backend.workflow import recovery_sm
from backend.workflow.recovery_sm import (
    TRANSITIONS,
    InvalidRecoveryTransition,
    RecoveryEvent,
    allowed_events,
    stage_number,
    transition,
)

ALL_EVENTS = list(RecoveryEvent)
RECOVERY_STATES = [state for state in TrackState if state.value.startswith("STAGE_")]
ALL_STATES = [TrackState.NEW, *RECOVERY_STATES, TrackState.ODR_FILED_BY_OWNER, TrackState.PAID, TrackState.SETTLED, TrackState.CLOSED]


def test_the_table_is_complete():
    report = recovery_sm.validate_table()
    assert report["leaving_terminal"] == []
    assert report["transitions"] == len(TRANSITIONS) == 15


@pytest.mark.parametrize(("state", "event"), sorted(TRANSITIONS, key=lambda p: (p[0].value, p[1].value)))
def test_every_allowed_recovery_transition(state, event):
    assert transition(state, event) is TRANSITIONS[(state, event)]


@pytest.mark.parametrize(("state", "event"), [(s, e) for s in ALL_STATES for e in ALL_EVENTS])
def test_every_pair_is_allowed_or_refused(state, event):
    if (state, event) in TRANSITIONS:
        assert transition(state, event) in TrackState
    else:
        with pytest.raises(InvalidRecoveryTransition):
            transition(state, event)


def test_the_ladder_walks_from_new_to_odr_filed():
    """PREPARE, MARK_SENT, PREPARE, ... exactly as section 5.2 draws it."""
    state = transition(TrackState.NEW, RecoveryEvent.PREPARE)
    assert state is TrackState.STAGE_1_PREPARED
    state = transition(state, RecoveryEvent.MARK_SENT)
    assert state is TrackState.STAGE_1_SENT_BY_OWNER
    state = transition(state, RecoveryEvent.PREPARE)
    assert state is TrackState.STAGE_2_PREPARED
    state = transition(state, RecoveryEvent.MARK_SENT)
    assert state is TrackState.STAGE_2_SENT_BY_OWNER
    state = transition(state, RecoveryEvent.PREPARE)
    assert state is TrackState.STAGE_3_PREPARED
    state = transition(state, RecoveryEvent.MARK_SENT)
    assert state is TrackState.STAGE_3_SENT_BY_OWNER
    state = transition(state, RecoveryEvent.PREPARE)
    assert state is TrackState.STAGE_4_PACK_READY
    state = transition(state, RecoveryEvent.MARK_ODR_FILED)
    assert state is TrackState.ODR_FILED_BY_OWNER


@pytest.mark.parametrize("event", ["mark_paid", "mark_settled"])
def test_a_filed_case_can_end_paid_or_settled(event):
    outcome = transition(TrackState.ODR_FILED_BY_OWNER, RecoveryEvent(event))
    assert outcome in {TrackState.PAID, TrackState.SETTLED}
    assert transition(outcome, RecoveryEvent.CLOSE) is TrackState.CLOSED


def test_there_is_no_send_event():
    """Golden rule 10: the machine can record the owner's claim, never a delivery."""
    assert not any(event.value in {"send", "send_message", "auto_send"} for event in RecoveryEvent)


def test_marking_sent_is_the_only_way_into_a_sent_state():
    """No stage can reach `_SENT_BY_OWNER` except through `mark_sent`."""
    for (state, event), target in TRANSITIONS.items():
        if target.value.endswith("_SENT_BY_OWNER"):
            assert event is RecoveryEvent.MARK_SENT, f"{target.value} reachable via {event.value}"


def test_allowed_events_for_a_prepared_stage():
    assert allowed_events(TrackState.STAGE_1_PREPARED) == ["mark_sent", "prepare"]
    assert allowed_events(TrackState.CLOSED) == []


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        (TrackState.STAGE_1_PREPARED, 1),
        (TrackState.STAGE_2_SENT_BY_OWNER, 2),
        (TrackState.STAGE_4_PACK_READY, 4),
        (TrackState.NEW, None),
        (TrackState.PAID, None),
    ],
)
def test_stage_number(state, expected):
    assert stage_number(state) == expected
