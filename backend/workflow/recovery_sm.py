"""Recovery track state machine (architecture_v4 section 5.2).

The v3 escalation ladder, now with state:

    NEW -> STAGE_1_PREPARED -> STAGE_1_SENT_BY_OWNER -> STAGE_2_PREPARED -> ...
        -> STAGE_4_PACK_READY -> ODR_FILED_BY_OWNER -> PAID / SETTLED -> CLOSED

`SENT_BY_OWNER` is recorded only when the owner taps "I've sent it" (golden rule 10:
nothing auto-sends). There is no `send` event in this table on purpose — there is no
code path that can claim a message was delivered.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from backend.app.schemas_v4 import TrackState


class RecoveryEvent(str, Enum):
    PREPARE = "prepare"
    MARK_SENT = "mark_sent"
    MARK_ODR_FILED = "mark_odr_filed"
    MARK_PAID = "mark_paid"
    MARK_SETTLED = "mark_settled"
    CLOSE = "close"


STAGE_STATES: tuple[TrackState, ...] = (
    TrackState.STAGE_1_PREPARED,
    TrackState.STAGE_1_SENT_BY_OWNER,
    TrackState.STAGE_2_PREPARED,
    TrackState.STAGE_2_SENT_BY_OWNER,
    TrackState.STAGE_3_PREPARED,
    TrackState.STAGE_3_SENT_BY_OWNER,
    TrackState.STAGE_4_PACK_READY,
)

TRANSITIONS: dict[tuple[TrackState, RecoveryEvent], TrackState] = {
    # start
    (TrackState.NEW, RecoveryEvent.PREPARE): TrackState.STAGE_1_PREPARED,
    # stage 1
    (TrackState.STAGE_1_PREPARED, RecoveryEvent.MARK_SENT): TrackState.STAGE_1_SENT_BY_OWNER,
    (TrackState.STAGE_1_PREPARED, RecoveryEvent.PREPARE): TrackState.STAGE_2_PREPARED,
    (TrackState.STAGE_1_SENT_BY_OWNER, RecoveryEvent.PREPARE): TrackState.STAGE_2_PREPARED,
    # stage 2
    (TrackState.STAGE_2_PREPARED, RecoveryEvent.MARK_SENT): TrackState.STAGE_2_SENT_BY_OWNER,
    (TrackState.STAGE_2_PREPARED, RecoveryEvent.PREPARE): TrackState.STAGE_3_PREPARED,
    (TrackState.STAGE_2_SENT_BY_OWNER, RecoveryEvent.PREPARE): TrackState.STAGE_3_PREPARED,
    # stage 3
    (TrackState.STAGE_3_PREPARED, RecoveryEvent.MARK_SENT): TrackState.STAGE_3_SENT_BY_OWNER,
    (TrackState.STAGE_3_PREPARED, RecoveryEvent.PREPARE): TrackState.STAGE_4_PACK_READY,
    (TrackState.STAGE_3_SENT_BY_OWNER, RecoveryEvent.PREPARE): TrackState.STAGE_4_PACK_READY,
    # stage 4 and beyond
    (TrackState.STAGE_4_PACK_READY, RecoveryEvent.MARK_ODR_FILED): TrackState.ODR_FILED_BY_OWNER,
    (TrackState.ODR_FILED_BY_OWNER, RecoveryEvent.MARK_PAID): TrackState.PAID,
    (TrackState.ODR_FILED_BY_OWNER, RecoveryEvent.MARK_SETTLED): TrackState.SETTLED,
    # closing
    (TrackState.PAID, RecoveryEvent.CLOSE): TrackState.CLOSED,
    (TrackState.SETTLED, RecoveryEvent.CLOSE): TrackState.CLOSED,
}

TERMINAL_STATES: frozenset[TrackState] = frozenset({TrackState.CLOSED})


class InvalidRecoveryTransition(Exception):
    """The event is not legal from this state."""

    def __init__(self, state: TrackState, event: RecoveryEvent) -> None:
        self.state = state
        self.event = event
        super().__init__(f"{event.value} is not allowed from {state.value}")


def transition(state: TrackState, event: RecoveryEvent) -> TrackState:
    nxt = TRANSITIONS.get((state, event))
    if nxt is None:
        raise InvalidRecoveryTransition(state, event)
    return nxt


def allowed_events(state: TrackState) -> list[str]:
    return sorted(event.value for (source, event) in TRANSITIONS if source is state)


def stage_number(state: TrackState) -> int | None:
    """1-4 for a stage state, else None. Used by the Dues list and the judge console."""
    if state.value.startswith("STAGE_"):
        head = state.value.split("_")[1]
        return int(head) if head.isdigit() else None
    return None


def validate_table() -> dict[str, Any]:
    """Self-check for the tests: no edge leaves a terminal state."""
    leaving_terminal = [
        (state.value, event.value)
        for (state, event) in TRANSITIONS
        if state in TERMINAL_STATES
    ]
    return {
        "transitions": len(TRANSITIONS),
        "states_covered": len({state for state, _ in TRANSITIONS}),
        "leaving_terminal": leaving_terminal,
    }
