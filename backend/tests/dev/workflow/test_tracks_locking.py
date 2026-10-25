"""The track-locking table (section 5.3), the unique index, and optimistic versions.

Every row of the locking table is a test. The database half is tested directly too,
because "the application check forgot" must still lose.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from backend.app.schemas_v4 import TrackKind, TrackState
from backend.store import db as store_db
from backend.store.ids import new_ulid
from backend.store.models import Case, Track
from backend.workflow import tracks
from backend.workflow.tracks import LockDecision, StaleVersion, TrackConflict


def _track(kind: str, state: str) -> Track:
    return Track(id=new_ulid(), case_id="CASE-1", kind=kind, state=state, version=1)


def _case(session: Session, case_id: str = "CASE-1") -> Case:
    row = Case(
        id=case_id,
        supplier_ref="SUP-SYN-0001",
        invoice_no="INV-0042",
        invoice_date=date(2026, 9, 16),
        accepted_amount=Decimal("1250000.00"),
        input_json={},
    )
    session.add(row)
    session.flush()
    return row


# ------------------------------------------------------------ the table ----


def test_no_track_financing_financeable_is_allowed():
    assert tracks.can_start(TrackKind.FINANCING, None, financeable=True).allowed is True


def test_no_track_financing_not_financeable_is_refused():
    decision = tracks.can_start(TrackKind.FINANCING, None, financeable=False)
    assert decision.allowed is False
    assert decision.code == "NOT_FINANCEABLE"


def test_no_track_recovery_is_always_allowed():
    """A gentle reminder does not need the Act's help, so recovery is never blocked here."""
    assert tracks.can_start(TrackKind.RECOVERY, None).allowed is True


@pytest.mark.parametrize(
    "state",
    [TrackState.STAGE_1_PREPARED, TrackState.STAGE_1_SENT_BY_OWNER, TrackState.STAGE_2_PREPARED],
)
def test_recovery_before_stage_three_may_switch_to_financing(state):
    decision = tracks.can_start(TrackKind.FINANCING, _track("RECOVERY", state.value))
    assert decision.allowed is True
    assert decision.code == "RECOVERY_PAUSED"


@pytest.mark.parametrize(
    "state",
    [TrackState.STAGE_3_PREPARED, TrackState.STAGE_3_SENT_BY_OWNER, TrackState.STAGE_4_PACK_READY],
)
def test_recovery_at_stage_three_or_later_blocks_financing(state):
    decision = tracks.can_start(TrackKind.FINANCING, _track("RECOVERY", state.value))
    assert decision.allowed is False
    assert decision.code == "RECOVERY_STAGE_LOCKED"


@pytest.mark.parametrize(
    "state",
    [
        TrackState.NEW,
        TrackState.FINANCEABLE,
        TrackState.AWAITING_BUYER_ACCEPTANCE,
        TrackState.BIDDING_OPEN,
        TrackState.BIDS_AVAILABLE,
    ],
)
def test_financing_before_signature_may_switch_to_recovery(state):
    decision = tracks.can_start(TrackKind.RECOVERY, _track("FINANCING", state.value))
    assert decision.allowed is True
    assert decision.code == "FINANCING_CANCELLED"


@pytest.mark.parametrize(
    "state",
    [
        TrackState.AWAITING_ESIGN,
        TrackState.AWAITING_DISBURSEMENT,
        TrackState.DISBURSED,
        TrackState.DISBURSEMENT_FAILED,
    ],
)
def test_financing_after_signature_blocks_recovery(state):
    decision = tracks.can_start(TrackKind.RECOVERY, _track("FINANCING", state.value))
    assert decision.allowed is False
    assert decision.code == "FINANCING_ASSIGNED"


@pytest.mark.parametrize(
    "state",
    [TrackState.BUYER_DECLINED, TrackState.NO_BIDS, TrackState.CANCELLED],
)
def test_a_dead_financing_track_allows_a_one_click_switch(state):
    decision = tracks.can_start(TrackKind.RECOVERY, _track("FINANCING", state.value))
    assert decision.allowed is True


def test_starting_the_same_track_kind_twice_is_reported_as_active():
    decision = tracks.can_start(TrackKind.FINANCING, _track("FINANCING", "FINANCEABLE"))
    assert decision.allowed is True
    assert decision.code == "TRACK_ALREADY_ACTIVE", "the opener turns this into a 409"


# ----------------------------------------------------- the database half ----


@pytest.fixture()
def session(tmp_path):
    url = f"sqlite:///{tmp_path / 'locks.db'}"
    store_db.dispose()
    store_db.init_db(url)
    active = store_db.get_session_factory()()
    try:
        yield active
    finally:
        active.rollback()
        active.close()
        store_db.dispose()


def test_the_unique_index_rejects_a_second_open_track(session):
    """Bypassing `open_track` must still fail: the index is the real guard."""
    _case(session)
    session.add(Track(id=new_ulid(), case_id="CASE-1", kind="FINANCING", state="FINANCEABLE", version=1))
    session.flush()
    session.add(Track(id=new_ulid(), case_id="CASE-1", kind="RECOVERY", state="STAGE_1_PREPARED", version=1))
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_open_track_refuses_when_one_is_already_open(session):
    _case(session)
    first = tracks.open_track(session, case_id="CASE-1", kind=TrackKind.FINANCING, state=TrackState.NEW)
    assert first.version == 1
    with pytest.raises(TrackConflict, match="already has an open"):
        tracks.open_track(session, case_id="CASE-1", kind=TrackKind.RECOVERY, state=TrackState.NEW)


def test_a_closed_track_does_not_block_a_new_one(session):
    _case(session)
    first = tracks.open_track(session, case_id="CASE-1", kind=TrackKind.FINANCING, state=TrackState.FINANCEABLE)
    first.closed_at = datetime(2026, 10, 26, 9, 0, tzinfo=UTC)
    session.flush()
    second = tracks.open_track(session, case_id="CASE-1", kind=TrackKind.RECOVERY, state=TrackState.NEW)
    assert second.id != first.id


def test_a_transition_bumps_the_version(session):
    _case(session)
    track = tracks.open_track(session, case_id="CASE-1", kind=TrackKind.FINANCING, state=TrackState.NEW)
    assert track.version == 1
    track = tracks.apply_transition(
        session, track, event="check_financeability", expected_version=1, actor="USER"
    )
    assert track.state == TrackState.FINANCEABLE.value
    assert track.version == 2


def test_a_stale_expected_version_loses(session):
    """This is the race: the second writer's WHERE clause matches nothing."""
    _case(session)
    track = tracks.open_track(session, case_id="CASE-1", kind=TrackKind.FINANCING, state=TrackState.NEW)
    tracks.apply_transition(session, track, event="check_financeability", expected_version=1, actor="USER")

    with pytest.raises(StaleVersion):
        tracks.apply_transition(
            session, track, event="request_buyer_acceptance", expected_version=1, actor="USER"
        )


def test_two_sessions_cannot_both_win_the_same_version(tmp_path):
    """Two independent sessions replaying version 1: exactly one UPDATE applies."""
    url = f"sqlite:///{tmp_path / 'race.db'}"
    store_db.dispose()
    store_db.init_db(url)

    with store_db.session_scope() as setup:
        _case(setup)
        track = tracks.open_track(setup, case_id="CASE-1", kind=TrackKind.FINANCING, state=TrackState.NEW)
        track_id = track.id

    factory = store_db.get_session_factory()
    first, second = factory(), factory()
    try:
        winner_a = tracks.apply_transition(
            first,
            first.get(Track, track_id),
            event="check_financeability",
            expected_version=1,
            actor="USER",
        )
        assert winner_a.version == 2
        first.commit()

        with pytest.raises(StaleVersion):
            tracks.apply_transition(
                second,
                second.get(Track, track_id),
                event="check_financeability",
                expected_version=1,
                actor="USER",
            )
    finally:
        first.close()
        second.close()
        store_db.dispose()


def test_every_transition_appends_an_audit_event(session):
    _case(session)
    track = tracks.open_track(session, case_id="CASE-1", kind=TrackKind.FINANCING, state=TrackState.NEW)
    tracks.apply_transition(session, track, event="check_financeability", expected_version=1, actor="USER")

    from backend.store import audit

    result = audit.verify_chain(session, "CASE-1")
    assert result["ok"] is True
    assert result["checked"] == 2, "track.created plus the transition"

    rows = session.exec(
        __import__("sqlmodel").select(__import__("backend.store.models", fromlist=["Event"]).Event)
    ).all()
    assert [row.type for row in rows] == ["track.created", "financing.check_financeability"]
    assert rows[1].actor == "USER"
    assert rows[1].payload_json == {"from": "NEW", "to": "FINANCEABLE"}
