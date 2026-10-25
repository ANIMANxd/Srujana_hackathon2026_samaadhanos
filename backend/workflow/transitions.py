"""The track state machine's action table (architecture_v4 section 5).

One table, used by three callers so they cannot drift apart:
- `GET /api/v1/cases/{id}` (available_actions),
- the fixture generator (`backend/app/export_v4_fixtures.py`),
- whatever the workflow routes add later.

`available_actions` deliberately encodes the **track-locking rules** from section
5.3: `switch_to_recovery` is absent from every financing state from AWAITING_ESIGN
onward, because after signature the receivable belongs to the financier and a
recovery action would be wrong and confusing. There is no separate lock table to
forget to consult.

This module is pure data plus one lookup: no I/O, no clock, no policy.
"""

from __future__ import annotations

from backend.app.schemas_v4 import TrackKind, TrackState

# The action codes a UI may offer from each state. Order is the order to show them.
ACTIONS: dict[TrackState, tuple[str, ...]] = {
    # --- financing (option 1) ---
    TrackState.NEW: ("check_financeability", "start_recovery"),
    TrackState.FINANCEABLE: ("request_buyer_acceptance", "switch_to_recovery", "cancel_financing"),
    TrackState.NOT_FINANCEABLE: ("switch_to_recovery",),
    TrackState.AWAITING_BUYER_ACCEPTANCE: (
        "wait_for_buyer",
        "switch_to_recovery",
        "cancel_financing",
    ),
    TrackState.BIDDING_OPEN: ("wait_for_bids", "cancel_financing"),
    TrackState.BIDS_AVAILABLE: ("select_bid", "cancel_financing"),
    TrackState.NO_BIDS: ("switch_to_recovery", "cancel_financing"),
    # From here the receivable is assigned: no way back to recovery.
    TrackState.AWAITING_ESIGN: ("complete_esign", "cancel_financing"),
    TrackState.AWAITING_DISBURSEMENT: ("wait_for_payout",),
    TrackState.DISBURSEMENT_FAILED: ("retry_payout",),
    TrackState.DISBURSED: ("view_events", "download_pack"),
    TrackState.SETTLED_WITHOUT_RECOURSE: ("view_events",),
    TrackState.BUYER_DECLINED: ("switch_to_recovery", "cancel_financing"),
    TrackState.CANCELLED: ("switch_to_recovery",),
    # --- recovery (option 2) ---
    TrackState.STAGE_1_PREPARED: ("mark_sent", "prepare_next_stage"),
    TrackState.STAGE_1_SENT_BY_OWNER: ("prepare_next_stage",),
    TrackState.STAGE_2_PREPARED: ("mark_sent", "prepare_next_stage"),
    TrackState.STAGE_2_SENT_BY_OWNER: ("prepare_next_stage",),
    TrackState.STAGE_3_PREPARED: ("mark_sent", "prepare_next_stage"),
    TrackState.STAGE_3_SENT_BY_OWNER: ("prepare_next_stage",),
    TrackState.STAGE_4_PACK_READY: ("mark_odr_filed",),
    TrackState.ODR_FILED_BY_OWNER: ("mark_paid", "mark_settled"),
    TrackState.PAID: ("view_events",),
    TrackState.SETTLED: ("view_events",),
    TrackState.CLOSED: ("view_events",),
}

# States from which a recovery action is still legitimate. Everything else locks it.
FINANCING_STATES_BEFORE_ASSIGNMENT: frozenset[TrackState] = frozenset(
    {
        TrackState.NEW,
        TrackState.FINANCEABLE,
        TrackState.NOT_FINANCEABLE,
        TrackState.AWAITING_BUYER_ACCEPTANCE,
        TrackState.BIDDING_OPEN,
        TrackState.BIDS_AVAILABLE,
        TrackState.NO_BIDS,
        TrackState.BUYER_DECLINED,
        TrackState.CANCELLED,
    }
)

TERMINAL_STATES: frozenset[TrackState] = frozenset(
    {
        TrackState.NOT_FINANCEABLE,
        TrackState.NO_BIDS,
        TrackState.BUYER_DECLINED,
        TrackState.CANCELLED,
        TrackState.SETTLED,
        TrackState.SETTLED_WITHOUT_RECOURSE,
        TrackState.PAID,
        TrackState.CLOSED,
    }
)


def available_actions(state: TrackState | str | None, kind: TrackKind | str | None = None) -> list[str]:
    """The action codes allowed from `state`.

    No track yet means `NEW`, which is where every case starts. An unknown state
    returns only `view_events`: it is safer to offer nothing than to offer an action
    the workflow cannot honour.
    """
    if state is None:
        state = TrackState.NEW
    if isinstance(state, str):
        try:
            state = TrackState(state)
        except ValueError:
            return ["view_events"]
    return list(ACTIONS.get(state, ("view_events",)))


def is_terminal(state: TrackState | str | None) -> bool:
    if state is None:
        return False
    if isinstance(state, str):
        try:
            state = TrackState(state)
        except ValueError:
            return False
    return state in TERMINAL_STATES


def recovery_allowed(state: TrackState | str | None) -> bool:
    """Whether a recovery action may still start from this financing state."""
    if state is None:
        return True
    if isinstance(state, str):
        try:
            state = TrackState(state)
        except ValueError:
            return False
    return state in FINANCING_STATES_BEFORE_ASSIGNMENT
