"""Append-only, hash-chained audit trail (architecture_v4 section 4).

    hash = sha256(prev_hash || canonical_json(type, payload, actor, created_at))

The chain is **tamper-evident, not tamper-proof**: anyone with write access to the
database can rewrite the whole chain, but they cannot change one row without
`verify_chain` naming the sequence number that stopped verifying. Say it that way
in the pitch.

`append_event` never commits. The caller owns the transaction, because the
transition and the event that records it must land together (a webhook that
applies a transition without recording it would be unauditable).
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

from sqlalchemy import func
from sqlmodel import select
from sqlalchemy.orm import Session

from backend.store.models import (
    GENESIS_HASH,
    Event,
    canonical_json,
    iso_utc,
    utc_now,
)


def event_hash(prev_hash: str, *, type: str, payload: dict[str, Any], actor: str, created_at: str) -> str:
    """The documented chain hash for one event."""
    body = {"type": type, "payload": payload, "actor": actor, "created_at": created_at}
    return hashlib.sha256((prev_hash + canonical_json(body)).encode("utf-8")).hexdigest()


def _last_event(session: Session, case_id: str) -> Event | None:
    return session.exec(
        select(Event).where(Event.case_id == case_id).order_by(Event.seq.desc()).limit(1)
    ).first()


def append_event(
    session: Session,
    *,
    case_id: str,
    type: str,
    payload: dict[str, Any] | None = None,
    actor: str,
    track_id: str | None = None,
    created_at: datetime | None = None,
) -> Event:
    """Append one event to a case's chain and flush it (no commit).

    `seq` is per case and contiguous from 1. `actor` is USER, SYSTEM or
    PROVIDER_MOCK. `payload` must be JSON-safe: money goes in as a decimal
    *string*, never a Decimal or a float.
    """
    body = payload or {}
    # Fail fast on a non-JSON-safe payload rather than storing something that can
    # never be re-verified.
    canonical_json(body)

    previous = _last_event(session, case_id)
    prev_hash = previous.hash if previous else GENESIS_HASH
    next_seq = (previous.seq if previous else 0) + 1
    stamp = iso_utc(created_at or utc_now())

    event = Event(
        case_id=case_id,
        seq=next_seq,
        track_id=track_id,
        type=type,
        payload_json=body,
        actor=actor,
        created_at=stamp,
        prev_hash=prev_hash,
        hash=event_hash(prev_hash, type=type, payload=body, actor=actor, created_at=stamp),
    )
    session.add(event)
    session.flush()
    return event


def verify_chain(session: Session, case_id: str) -> dict[str, Any]:
    """Recompute a case's chain and report the first sequence that fails.

    Returns `{"ok": bool, "first_bad_seq": int | None, "checked": int}`.
    `first_bad_seq` is the 1-based sequence number of the first bad row, so a
    broken link names itself.
    """
    events = session.exec(
        select(Event).where(Event.case_id == case_id).order_by(Event.seq.asc())
    ).all()

    prev_hash = GENESIS_HASH
    checked = 0
    for expected_seq, event in enumerate(events, start=1):
        if event.seq != expected_seq:
            return {"ok": False, "first_bad_seq": expected_seq, "checked": checked}
        if event.prev_hash != prev_hash:
            return {"ok": False, "first_bad_seq": event.seq, "checked": checked}
        recomputed = event_hash(
            prev_hash,
            type=event.type,
            payload=event.payload_json,
            actor=event.actor,
            created_at=event.created_at,
        )
        if recomputed != event.hash:
            return {"ok": False, "first_bad_seq": event.seq, "checked": checked}
        prev_hash = event.hash
        checked += 1

    return {"ok": True, "first_bad_seq": None, "checked": checked}


def event_count(session: Session, case_id: str) -> int:
    """How many events a case has; used by the seed and by tests."""
    return session.exec(select(func.count()).select_from(Event).where(Event.case_id == case_id)).one()
