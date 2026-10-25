"""Idempotent mutations (architecture_v4 section 8).

An `Idempotency-Key` header is required on every mutating POST. The rules:

- the same key + the same request body returns the **stored** response, with no
  second write (`replayed=True`, `conflict=False`);
- the same key + a **different** body is a conflict (`conflict=True`), which the
  route turns into a `409` â€” never a silent second write;
- a new key stores the response (`replayed=False`).

The response is stored as JSON, so callers pass a JSON-safe dict (money as
decimal strings).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlmodel import select
from sqlalchemy.orm import Session

from backend.store.models import IdempotencyKey, canonical_json


@dataclass(frozen=True)
class IdempotentResult:
    """What `get_or_store` decided, plus the body to return."""

    response: dict[str, Any]
    replayed: bool
    conflict: bool
    request_hash: str

    @property
    def status_code(self) -> int:
        """`409` on a replay whose body changed, `200` otherwise."""
        return 409 if self.conflict else 200


def hash_request(payload: Any) -> str:
    """Canonical hash of a request body, so key+body can be compared exactly."""
    import hashlib

    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def lookup(session: Session, *, key: str, route: str) -> IdempotencyKey | None:
    """The recorded row for this key+route, if any.

    Routes call this *before* doing any work, so a replay never re-applies a
    transition, and again nothing on the happy path.
    """
    return session.exec(
        select(IdempotencyKey).where(IdempotencyKey.key == key, IdempotencyKey.route == route)
    ).first()


def store(
    session: Session,
    *,
    key: str,
    route: str,
    request_hash: str,
    response: dict[str, Any],
) -> IdempotencyKey:
    """Record the response for this key+route. Caller commits."""
    row = IdempotencyKey(key=key, route=route, request_hash=request_hash, response_json=response)
    session.add(row)
    session.flush()
    return row


def get_or_store(
    session: Session,
    *,
    key: str,
    route: str,
    request_hash: str,
    response: dict[str, Any],
) -> IdempotentResult:
    """Return the recorded response for this key, or store this one.

    Flushes but does not commit: the caller's transaction must also contain the
    mutation the response describes, or a crash could record a response for work
    that rolled back.
    """
    existing = session.exec(
        select(IdempotencyKey).where(IdempotencyKey.key == key, IdempotencyKey.route == route)
    ).first()

    if existing is not None:
        if existing.request_hash == request_hash:
            return IdempotentResult(
                response=existing.response_json,
                replayed=True,
                conflict=False,
                request_hash=request_hash,
            )
        return IdempotentResult(
            response={
                "error": {
                    "code": "IDEMPOTENCY_CONFLICT",
                    "message": (
                        "This Idempotency-Key was already used for a different request body. "
                        "Use a new key for a new request."
                    ),
                    "details": {
                        "key": key,
                        "route": route,
                        "stored_request_hash": existing.request_hash,
                        "sent_request_hash": request_hash,
                    },
                }
            },
            replayed=True,
            conflict=True,
            request_hash=request_hash,
        )

    session.add(
        IdempotencyKey(key=key, route=route, request_hash=request_hash, response_json=response)
    )
    session.flush()
    return IdempotentResult(response=response, replayed=False, conflict=False, request_hash=request_hash)


def purge_expired(session: Session, *, older_than_seconds: int = 86_400) -> int:
    """Drop old keys. Not wired to a schedule yet; the demo keeps everything."""
    from datetime import timedelta

    from backend.store.models import utc_now

    cutoff = utc_now() - timedelta(seconds=older_than_seconds)
    rows = session.exec(select(IdempotencyKey).where(IdempotencyKey.created_at < cutoff)).all()
    for row in rows:
        session.delete(row)
    session.flush()
    return len(rows)
