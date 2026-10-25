"""The audit chain verifies, and tampering with one row names that seq."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import text
from sqlmodel import Session

from backend.store.audit import append_event, event_count, verify_chain
from backend.store.models import GENESIS_HASH, Case


def _seed_chain(session: Session, case: Case) -> None:
    append_event(
        session,
        case_id=case.id,
        type="case.created",
        payload={"invoice_no": "INV-0042"},
        actor="USER",
        created_at=datetime(2026, 10, 25, 9, 12, 4, tzinfo=UTC),
    )
    append_event(
        session,
        case_id=case.id,
        type="evaluation.stored",
        payload={"as_of": "2026-10-25"},
        actor="SYSTEM",
        created_at=datetime(2026, 10, 25, 9, 12, 5, tzinfo=UTC),
    )
    append_event(
        session,
        case_id=case.id,
        type="track.created",
        payload={"kind": "FINANCING"},
        actor="USER",
        created_at=datetime(2026, 10, 25, 9, 13, 10, tzinfo=UTC),
    )
    append_event(
        session,
        case_id=case.id,
        type="financing.financeable",
        payload={"reasons": []},
        actor="SYSTEM",
        created_at=datetime(2026, 10, 25, 9, 13, 11, tzinfo=UTC),
    )


def test_the_chain_verifies(session: Session, case: Case):
    _seed_chain(session, case)
    assert event_count(session, case.id) == 4
    result = verify_chain(session, case.id)
    assert result == {"ok": True, "first_bad_seq": None, "checked": 4}


def test_seq_starts_at_one_and_is_contiguous(session: Session, case: Case):
    _seed_chain(session, case)
    seqs = [row[0] for row in session.execute(text("SELECT seq FROM events ORDER BY seq")).all()]
    assert seqs == [1, 2, 3, 4]


def test_the_first_event_links_to_genesis(session: Session, case: Case):
    _seed_chain(session, case)
    first = session.execute(
        text("SELECT prev_hash FROM events WHERE case_id = :cid AND seq = 1"),
        params={"cid": case.id},
    ).one()
    assert first[0] == GENESIS_HASH
    assert len(GENESIS_HASH) == 64


def test_each_event_links_to_the_previous_hash(session: Session, case: Case):
    _seed_chain(session, case)
    rows = session.execute(
        text("SELECT seq, prev_hash, hash FROM events WHERE case_id = :cid ORDER BY seq"),
        params={"cid": case.id},
    ).all()
    for previous, current in zip(rows, rows[1:]):
        assert current[1] == previous[2], f"seq {current[0]} does not link to seq {previous[0]}"


def test_tampering_with_one_row_reports_that_seq(session: Session, case: Case):
    """Edit event 3's payload in place: the chain must name seq 3."""
    _seed_chain(session, case)
    assert verify_chain(session, case.id)["ok"] is True

    session.execute(
        text(
            "UPDATE events SET payload_json = :payload "
            "WHERE case_id = :cid AND seq = 3"
        ),
        params={"payload": '{"kind":"RECOVERY"}', "cid": case.id},
    )
    session.flush()

    result = verify_chain(session, case.id)
    assert result["ok"] is False
    assert result["first_bad_seq"] == 3, f"expected seq 3, got {result}"
    assert result["checked"] == 2, "the two good events before the tamper must still count"


def test_rewriting_a_hash_also_breaks_the_chain(session: Session, case: Case):
    """A tamperer who fixes the payload still cannot leave a valid hash behind."""
    _seed_chain(session, case)
    session.execute(
        text("UPDATE events SET hash = :hash WHERE case_id = :cid AND seq = 2"),
        params={"hash": "f" * 64, "cid": case.id},
    )
    session.flush()
    result = verify_chain(session, case.id)
    assert result["ok"] is False
    assert result["first_bad_seq"] == 2


def test_a_dropped_event_breaks_the_chain_at_its_position(session: Session, case: Case):
    """Deleting a middle event leaves a gap the verifier must catch."""
    _seed_chain(session, case)
    session.execute(
        text("DELETE FROM events WHERE case_id = :cid AND seq = 2"), params={"cid": case.id}
    )
    session.flush()
    result = verify_chain(session, case.id)
    assert result["ok"] is False
    assert result["first_bad_seq"] == 2


def test_an_empty_case_has_a_valid_empty_chain(session: Session, case: Case):
    assert verify_chain(session, case.id) == {"ok": True, "first_bad_seq": None, "checked": 0}


def test_a_non_json_safe_payload_is_refused(session: Session, case: Case):
    """Money must arrive as a decimal string; a Decimal cannot be hashed stably."""
    from decimal import Decimal

    import pytest

    with pytest.raises(TypeError):
        append_event(
            session,
            case_id=case.id,
            type="financing.disbursed",
            payload={"net_amount": Decimal("1240530.82")},
            actor="SYSTEM",
        )


def test_two_cases_keep_independent_chains(session: Session, case: Case):
    other = Case(
        id="01JAV4E7K3M9Q2R5T8V0W1XCZE",
        supplier_ref="SUP-SYN-0002",
        invoice_no="INV-0043",
        invoice_date=case.invoice_date,
        accepted_amount=case.accepted_amount,
        input_json={},
    )
    session.add(other)
    session.flush()
    append_event(session, case_id=case.id, type="case.created", payload={}, actor="USER")
    append_event(session, case_id=other.id, type="case.created", payload={}, actor="USER")

    assert verify_chain(session, case.id)["checked"] == 1
    assert verify_chain(session, other.id)["checked"] == 1
    both = session.execute(text("SELECT COUNT(*) FROM events")).one()
    assert both[0] == 2
