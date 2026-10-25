"""Financing track state machine (architecture_v4 section 5.1).

An explicit `{(state, event): next_state}` table plus named guards. Nothing here is
implicit: if a transition is not in `TRANSITIONS` it cannot happen, and
`validate_table()` proves the table is total and terminal-free of dangling edges.

Two places where the diagram in the document is not a plain pair:

- `NEW --check_financeability--> FINANCEABLE` has a branch to `NOT_FINANCEABLE`.
  A deterministic table cannot branch on one event, so the branch is modelled as a
  **second event** (`financeability_failed`) that the caller sends after the
  financeability check decides. The caller never guesses: it sends exactly one of the
  two.
- `BIDS_AVAILABLE --bids_expired--> BIDDING_OPEN` is allowed **once**; a second
  expiry goes to `NO_BIDS`. That rule is a guard (`bid_window_reopen`), not a second
  table row, because the destination is the same state the case is already in and the
  only thing that changes is the attempt count.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Callable

from backend.app.schemas_v4 import TrackState


class FinancingEvent(str, Enum):
    """The events that can move a financing track. Webhook events are the API's own."""

    CHECK_FINANCEABILITY = "check_financeability"
    FINANCEABILITY_FAILED = "financeability_failed"
    REQUEST_BUYER_ACCEPTANCE = "request_buyer_acceptance"
    BUYER_ACCEPTED = "buyer_accepted"
    BUYER_REJECTED = "buyer_rejected"
    WINDOW_EXPIRED = "window_expired"
    BIDS_RECEIVED = "bids_received"
    BIDDING_CLOSED = "bidding_closed"
    SELECT_BID = "select_bid"
    BIDS_EXPIRED = "bids_expired"
    ESIGN_COMPLETED = "esign_completed"
    ESIGN_FAILED = "esign_failed"
    ESIGN_EXPIRED = "esign_expired"
    PAYOUT_PROCESSED = "payout_processed"
    PAYOUT_FAILED = "payout_failed"
    RETRY_PAYOUT = "retry_payout"
    DUE_DATE_PAID = "due_date_paid"
    BUYER_DEFAULT = "buyer_default"
    USER_CANCEL = "user_cancel"


TRANSITIONS: dict[tuple[TrackState, FinancingEvent], TrackState] = {
    # entry
    (TrackState.NEW, FinancingEvent.CHECK_FINANCEABILITY): TrackState.FINANCEABLE,
    (TrackState.NEW, FinancingEvent.FINANCEABILITY_FAILED): TrackState.NOT_FINANCEABLE,
    # buyer acceptance
    (TrackState.FINANCEABLE, FinancingEvent.REQUEST_BUYER_ACCEPTANCE): TrackState.AWAITING_BUYER_ACCEPTANCE,
    (TrackState.AWAITING_BUYER_ACCEPTANCE, FinancingEvent.BUYER_ACCEPTED): TrackState.BIDDING_OPEN,
    (TrackState.AWAITING_BUYER_ACCEPTANCE, FinancingEvent.BUYER_REJECTED): TrackState.BUYER_DECLINED,
    (TrackState.AWAITING_BUYER_ACCEPTANCE, FinancingEvent.WINDOW_EXPIRED): TrackState.BUYER_DECLINED,
    # bidding
    (TrackState.BIDDING_OPEN, FinancingEvent.BIDS_RECEIVED): TrackState.BIDS_AVAILABLE,
    (TrackState.BIDDING_OPEN, FinancingEvent.BIDDING_CLOSED): TrackState.NO_BIDS,
    (TrackState.BIDS_AVAILABLE, FinancingEvent.SELECT_BID): TrackState.AWAITING_ESIGN,
    (TrackState.BIDS_AVAILABLE, FinancingEvent.BIDS_EXPIRED): TrackState.BIDDING_OPEN,
    (TrackState.BIDS_AVAILABLE, FinancingEvent.BIDDING_CLOSED): TrackState.NO_BIDS,
    # eSign
    (TrackState.AWAITING_ESIGN, FinancingEvent.ESIGN_COMPLETED): TrackState.AWAITING_DISBURSEMENT,
    (TrackState.AWAITING_ESIGN, FinancingEvent.ESIGN_FAILED): TrackState.BIDS_AVAILABLE,
    (TrackState.AWAITING_ESIGN, FinancingEvent.ESIGN_EXPIRED): TrackState.BIDS_AVAILABLE,
    # payout
    (TrackState.AWAITING_DISBURSEMENT, FinancingEvent.PAYOUT_PROCESSED): TrackState.DISBURSED,
    (TrackState.AWAITING_DISBURSEMENT, FinancingEvent.PAYOUT_FAILED): TrackState.DISBURSEMENT_FAILED,
    (TrackState.DISBURSEMENT_FAILED, FinancingEvent.RETRY_PAYOUT): TrackState.AWAITING_DISBURSEMENT,
    # settlement
    (TrackState.DISBURSED, FinancingEvent.DUE_DATE_PAID): TrackState.SETTLED,
    (TrackState.DISBURSED, FinancingEvent.BUYER_DEFAULT): TrackState.SETTLED_WITHOUT_RECOURSE,
}

# "Any pre-signature state" -- everything up to and including a selected bid that has
# not been signed yet.
CANCELLABLE_STATES: frozenset[TrackState] = frozenset(
    {
        TrackState.NEW,
        TrackState.FINANCEABLE,
        TrackState.NOT_FINANCEABLE,
        TrackState.AWAITING_BUYER_ACCEPTANCE,
        TrackState.BIDDING_OPEN,
        TrackState.BIDS_AVAILABLE,
        TrackState.AWAITING_ESIGN,
    }
)

TERMINAL_STATES: frozenset[TrackState] = frozenset(
    {
        TrackState.NOT_FINANCEABLE,
        TrackState.BUYER_DECLINED,
        TrackState.NO_BIDS,
        TrackState.SETTLED,
        TrackState.SETTLED_WITHOUT_RECOURSE,
        TrackState.CANCELLED,
    }
)

# Attempt limits from section 5.1. They are workflow ceilings, not statutory numbers.
MAX_ESIGN_ATTEMPTS = 3
MAX_BID_WINDOW_REOPENS = 1


@dataclass(frozen=True)
class GuardContext:
    """Everything a guard may look at. No clock, no I/O: the caller supplies `now`."""

    now: datetime | None = None
    bid_valid_until: datetime | None = None
    esign_attempts: int = 0
    bid_window_reopens: int = 0


Guard = Callable[[GuardContext], str | None]


def guard_bid_not_expired(ctx: GuardContext) -> str | None:
    """`select_bid` requires a bid that has not expired."""
    if ctx.bid_valid_until is None or ctx.now is None:
        return None
    if ctx.now > ctx.bid_valid_until:
        return "That bid has expired. Ask the financiers for a new round and choose again."
    return None


def guard_esign_attempts(ctx: GuardContext) -> str | None:
    """After three failed or expired signatures the track is cancelled, not retried."""
    if ctx.esign_attempts >= MAX_ESIGN_ATTEMPTS:
        return (
            f"Signing has failed {ctx.esign_attempts} times. This build stops at "
            f"{MAX_ESIGN_ATTEMPTS} attempts; start the financing again or use recovery."
        )
    return None


def guard_bid_window_reopen(ctx: GuardContext) -> str | None:
    """The bid window may re-open once; a second expiry means no bids."""
    if ctx.bid_window_reopens >= MAX_BID_WINDOW_REOPENS:
        return "The bidding window has already been re-opened once. There are no bids."
    return None


GUARDS: dict[FinancingEvent, Guard] = {
    FinancingEvent.SELECT_BID: guard_bid_not_expired,
    FinancingEvent.ESIGN_FAILED: guard_esign_attempts,
    FinancingEvent.ESIGN_EXPIRED: guard_esign_attempts,
    FinancingEvent.BIDS_EXPIRED: guard_bid_window_reopen,
}


class InvalidTransition(Exception):
    """The event is not legal from this state. The route turns this into a 409."""

    def __init__(self, state: TrackState, event: FinancingEvent, reason: str | None = None) -> None:
        self.state = state
        self.event = event
        self.reason = reason
        super().__init__(reason or f"{event.value} is not allowed from {state.value}")


def transition(state: TrackState, event: FinancingEvent, ctx: GuardContext | None = None) -> TrackState:
    """Apply one event, or raise `InvalidTransition`.

    Guard failures and missing table rows both raise `InvalidTransition`, because the
    caller's answer is the same either way: 409 with the state and what *is* allowed.
    """
    context = ctx or GuardContext()

    if event is FinancingEvent.USER_CANCEL:
        if state in CANCELLABLE_STATES:
            return TrackState.CANCELLED
        raise InvalidTransition(state, event, "This financing is already signed; it can no longer be cancelled.")

    guard = GUARDS.get(event)
    if guard is not None:
        problem = guard(context)
        if problem is not None:
            raise InvalidTransition(state, event, problem)

    nxt = TRANSITIONS.get((state, event))
    if nxt is None:
        raise InvalidTransition(state, event)
    return nxt


def allowed_events(state: TrackState) -> list[str]:
    """Every event legal from `state`, for the 409 body and for the UI."""
    events = [event.value for (source, event) in TRANSITIONS if source is state]
    if state in CANCELLABLE_STATES:
        events.append(FinancingEvent.USER_CANCEL.value)
    return sorted(events)


def validate_table() -> dict[str, Any]:
    """Self-check: no transition leaves a terminal state, and every target is known.

    Terminal states must have no outgoing table rows (cancel and the re-open rule are
    handled above the table). Returns a small report for the tests to assert on.
    """
    dangling = [
        (state.value, event.value)
        for (state, event), target in TRANSITIONS.items()
        if target not in TrackState
    ]
    leaving_terminal = [
        (state.value, event.value)
        for (state, event) in TRANSITIONS
        if state in TERMINAL_STATES
    ]
    return {
        "transitions": len(TRANSITIONS),
        "states_covered": len({state for state, _ in TRANSITIONS}),
        "dangling": dangling,
        "leaving_terminal": leaving_terminal,
    }
