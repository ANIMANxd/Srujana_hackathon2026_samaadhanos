"""Track locking and optimistic concurrency (architecture_v4 section 5.3).

Three separate defences, deliberately layered:

1. `can_start()` — the section 5.3 table, asked before anything is written.
2. The **database** — a partial unique index (`ux_tracks_one_active_per_case`) makes a
   second open track impossible even if the application check is bypassed.
3. **Optimistic versioning** — every transition is a conditional `UPDATE ... WHERE
   version = expected`, so of two racing requests exactly one wins and the other is
   told the current state.

A race must never produce two winners. That is the whole point of this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from backend.app.schemas_v4 import TrackKind, TrackState
from backend.store import audit
from backend.store.ids import new_ulid
from backend.store.models import Track
from backend.workflow import financing_sm, recovery_sm
from backend.workflow.recovery_sm import stage_number

# Financing states from which the receivable is already assigned to a financier, so a
# recovery action would be wrong and confusing (section 5.3, row 6).
ASSIGNED_STATES: frozenset[TrackState] = frozenset(
    {
        TrackState.AWAITING_ESIGN,
        TrackState.AWAITING_DISBURSEMENT,
        TrackState.DISBURSED,
        TrackState.DISBURSEMENT_FAILED,
        TrackState.SETTLED,
        TrackState.SETTLED_WITHOUT_RECOURSE,
    }
)

# Financing states that are over, so "switch to Option 2" is a one-click affordance.
FINANCING_OVER_STATES: frozenset[TrackState] = frozenset(
    {
        TrackState.BUYER_DECLINED,
        TrackState.NO_BIDS,
        TrackState.CANCELLED,
        TrackState.NOT_FINANCEABLE,
    }
)


@dataclass(frozen=True)
class LockDecision:
    """Whether a track may start, and why not."""

    allowed: bool
    code: str | None = None
    message: str | None = None


class TrackError(Exception):
    """Base for the errors the routes turn into a 409."""


class TrackConflict(TrackError):
    """A track is already open for this case (caught before or by the unique index)."""

    def __init__(self, existing: Track | None) -> None:
        self.existing = existing
        state = existing.state if existing is not None else "an open track"
        super().__init__(f"This case already has an open {state} track.")


class StaleVersion(TrackError):
    """The client's `If-Match` version is behind; it must re-read the case."""

    def __init__(self, current: Track) -> None:
        self.current = current
        super().__init__(
            f"This case moved on: the track is now {current.state} at version "
            f"{current.version}. Re-read the case and try again."
        )


class InvalidStep(TrackError):
    """The event is not legal from the track's state."""

    def __init__(self, state: TrackState, event: str, allowed: list[str], reason: str | None = None) -> None:
        self.state = state
        self.event = event
        self.allowed = allowed
        super().__init__(reason or f"{event} is not allowed from {state.value}")


# ------------------------------------------------------- the locking table ----


def can_start(
    kind: TrackKind | str,
    active: Track | None,
    *,
    financeable: bool | None = None,
) -> LockDecision:
    """The section 5.3 table, row by row.

    `financeable` is only consulted when starting financing from nothing; recovery is
    always available (a gentle reminder is allowed even without the Act's help).
    """
    kind = TrackKind(kind)

    if active is None:
        if kind is TrackKind.FINANCING and financeable is False:
            return LockDecision(
                False,
                "NOT_FINANCEABLE",
                "Option 1 is not available for this invoice yet; see the reasons.",
            )
        return LockDecision(True)

    active_kind = TrackKind(active.kind)
    active_state = TrackState(active.state)

    if active_kind is kind:
        return LockDecision(
            True,
            "TRACK_ALREADY_ACTIVE",
            f"This case already has an open {kind.value.lower()} track.",
        )

    if active_kind is TrackKind.RECOVERY and kind is TrackKind.FINANCING:
        stage = stage_number(active_state)
        if stage is not None and stage >= 3:
            return LockDecision(
                False,
                "RECOVERY_STAGE_LOCKED",
                f"Recovery is already at stage {stage}. Once a dispute is formal, "
                "financing this invoice is no longer realistic.",
            )
        return LockDecision(
            True,
            "RECOVERY_PAUSED",
            "Recovery is paused while you try Option 1, not deleted.",
        )

    # active is FINANCING, requested is RECOVERY
    if active_state in ASSIGNED_STATES:
        return LockDecision(
            False,
            "FINANCING_ASSIGNED",
            "This invoice is already assigned to a financier, so recovery actions "
            "would be wrong and confusing.",
        )
    return LockDecision(
        True,
        "FINANCING_CANCELLED",
        "The financing attempt is cancelled; nothing had been assigned.",
    )


# ------------------------------------------------------------- DB helpers ----


def active_track(session: Session, case_id: str) -> Track | None:
    return session.exec(
        select(Track).where(Track.case_id == case_id, Track.closed_at.is_(None))
    ).first()


def open_track(
    session: Session,
    *,
    case_id: str,
    kind: TrackKind | str,
    state: TrackState | str,
    actor: str = "USER",
) -> Track:
    """Open a track. Raises `TrackConflict` if one is already open.

    The unique partial index is the real guard; the pre-check only produces a nicer
    message. `IntegrityError` is translated, never leaked.
    """
    existing = active_track(session, case_id)
    if existing is not None:
        raise TrackConflict(existing)

    track = Track(
        id=new_ulid(),
        case_id=case_id,
        kind=TrackKind(kind).value,
        state=TrackState(state).value,
        version=1,
    )
    session.add(track)
    try:
        session.flush()
    except IntegrityError as exc:  # the partial unique index won the race
        session.rollback()
        raise TrackConflict(None) from exc

    audit.append_event(
        session,
        case_id=case_id,
        track_id=track.id,
        type="track.created",
        payload={"kind": track.kind, "state": track.state},
        actor=actor,
    )
    return track


def apply_transition(
    session: Session,
    track: Track,
    *,
    event: str,
    expected_version: int,
    actor: str = "USER",
    payload: dict[str, Any] | None = None,
    guard_context: financing_sm.GuardContext | None = None,
) -> Track:
    """Apply one event with an optimistic lock, and append the audit event.

    The state change and the event that records it are written in the caller's
    transaction, so a crash cannot leave a transition without its trail entry.
    """
    if track.version != expected_version:
        raise StaleVersion(track)

    state = TrackState(track.state)
    kind = TrackKind(track.kind)

    if kind is TrackKind.FINANCING:
        try:
            next_state = financing_sm.transition(
                state, financing_sm.FinancingEvent(event), guard_context
            )
        except financing_sm.InvalidTransition as exc:
            raise InvalidStep(state, event, financing_sm.allowed_events(state), exc.reason) from exc
    else:
        try:
            next_state = recovery_sm.transition(state, recovery_sm.RecoveryEvent(event))
        except recovery_sm.InvalidRecoveryTransition as exc:
            raise InvalidStep(state, event, recovery_sm.allowed_events(state)) from exc

    closing = next_state in financing_sm.TERMINAL_STATES or next_state in recovery_sm.TERMINAL_STATES

    # The optimistic check *is* the WHERE clause: a racing request that already bumped
    # the version updates zero rows and loses cleanly.
    result = session.execute(
        update(Track)
        .where(Track.id == track.id, Track.version == expected_version)
        .values(
            state=next_state.value,
            version=expected_version + 1,
            closed_at=datetime.now(tz=None).astimezone() if closing else None,
        )
    )
    if result.rowcount != 1:
        session.expire(track)
        raise StaleVersion(track)

    session.expire(track)
    session.refresh(track)

    audit.append_event(
        session,
        case_id=track.case_id,
        track_id=track.id,
        type=f"{kind.value.lower()}.{event}",
        payload={"from": state.value, "to": next_state.value, **(payload or {})},
        actor=actor,
    )
    return track


def assert_open(track: Track | None) -> Track:
    """The track must exist and be open for a mutating financing route."""
    if track is None:
        raise TrackConflict(None)
    if track.closed_at is not None:
        raise TrackConflict(track)
    return track
