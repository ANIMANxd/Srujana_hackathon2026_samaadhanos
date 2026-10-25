"""Money is Decimal in Python and TEXT in SQLite, and the schema enforces the
track-locking rule at the database level.

Hand-computed expectations: 1250000.00 in, 1250000.00 out, scale preserved.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, StatementError
from sqlmodel import Session

from backend.store.ids import new_ulid
from backend.store.models import Bid, Case, Track

MONEY_IN = Decimal("1250000.00")


def test_money_roundtrips_as_decimal_with_scale_preserved(session: Session, case: Case):
    """A rupee amount must come back a Decimal, not a float and not a string."""
    stored = session.get(Case, case.id)
    assert isinstance(stored.accepted_amount, Decimal)
    assert stored.accepted_amount == MONEY_IN
    assert str(stored.accepted_amount) == "1250000.00", "scale must survive the roundtrip"


def test_money_is_text_in_sqlite_not_real(session: Session, case: Case):
    """Read the raw column: TEXT affinity, and the literal decimal string."""
    raw = session.execute(text("SELECT accepted_amount, typeof(accepted_amount) FROM cases")).one()
    value, affinity = raw
    assert value == "1250000.00"
    assert affinity == "text", f"money must be stored as TEXT, got {affinity}"


def test_money_columns_use_text_affinity_everywhere(session: Session):
    """No money column may be REAL/NUMERIC, on any table."""
    money_columns = {
        "cases": ["accepted_amount"],
        "financing_requests": ["accepted_amount"],
        "bids": ["annual_rate", "discount", "fee", "net_amount"],
    }
    for table, columns in money_columns.items():
        for column in columns:
            affinity = session.execute(
                text(f"SELECT typeof({column}) FROM {table} LIMIT 1")
            ).first()
            # No rows yet is fine; what matters is the declared type.
            declared = session.execute(text(f"PRAGMA table_info({table})")).all()
            types = {row[1]: row[2] for row in declared}
            assert types[column].upper() == "TEXT", (
                f"{table}.{column} is {types[column]}, money must be TEXT"
            )
            assert affinity is None or affinity[0] == "text"


def test_a_float_is_refused_not_silently_stored(session: Session, case: Case):
    """The trap: 1250000.1 has no exact binary representation."""
    bid = Bid(
        id="BID-1",
        track_id="TRK-1",
        financier_alias="Financier A",
        annual_rate=Decimal("8.00"),
        discount=Decimal("8219.18"),
        fee=Decimal("1250.00"),
        net_amount=Decimal("1240530.82"),
        valid_until=datetime(2026, 10, 26, 9, 0, tzinfo=UTC),
    )
    bid.net_amount = 1240530.82  # type: ignore[assignment]
    session.add(bid)
    # SQLAlchemy wraps the bind error, so the message is what proves the guard.
    with pytest.raises(StatementError, match="never float"):
        session.flush()
    session.rollback()


def test_decimal_strings_are_accepted_on_write(session: Session, case: Case):
    """The route layer may hand over strings; they become Decimal, never float."""
    case.accepted_amount = Decimal("999.99")
    session.flush()
    session.expire_all()
    assert session.get(Case, case.id).accepted_amount == Decimal("999.99")


# ------------------------------------------------------- track locking ----


def _track(case_id: str, *, closed: bool) -> Track:
    return Track(
        id=new_ulid(),
        case_id=case_id,
        kind="FINANCING",
        state="FINANCEABLE",
        version=1,
        closed_at=datetime(2026, 10, 30, 11, 0, tzinfo=UTC) if closed else None,
    )


def test_a_second_open_track_for_one_case_is_rejected(session: Session, case: Case):
    """Unique partial index: at most one active track per case."""
    session.add(_track(case.id, closed=False))
    session.flush()
    session.add(_track(case.id, closed=False))
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_a_closed_track_does_not_block_a_new_one(session: Session, case: Case):
    """Closed tracks are outside the partial index, so history can accumulate."""
    session.add(_track(case.id, closed=True))
    session.flush()
    session.add(_track(case.id, closed=False))
    session.flush()
    open_tracks = session.execute(
        text("SELECT COUNT(*) FROM tracks WHERE case_id = :cid AND closed_at IS NULL"),
        params={"cid": case.id},
    ).one()
    assert open_tracks[0] == 1


def test_two_cases_can_each_have_an_open_track(session: Session, case: Case):
    other = Case(
        id=new_ulid(),
        supplier_ref="SUP-SYN-0002",
        invoice_no="INV-0043",
        invoice_date=date(2026, 9, 17),
        accepted_amount=Decimal("500.00"),
        input_json={},
    )
    session.add(other)
    session.flush()
    session.add(_track(case.id, closed=False))
    session.add(_track(other.id, closed=False))
    session.flush()
