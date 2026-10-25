"""Idempotency: a replay returns the first response, a changed body is a conflict."""

from __future__ import annotations

from sqlalchemy import text
from sqlmodel import Session

from backend.store.idempotency import get_or_store, hash_request

ROUTE = "/api/v1/cases/01JAV4E7K3M9Q2R5T8V0W1XCZD/financing"
BODY = {"tenor_days": 30, "accepted_amount": "1250000.00"}


def test_a_new_key_stores_the_response(session: Session):
    result = get_or_store(
        session,
        key="key-1",
        route=ROUTE,
        request_hash=hash_request(BODY),
        response={"track_id": "TRK-FIN-0001", "state": "FINANCEABLE"},
    )
    assert result.replayed is False
    assert result.conflict is False
    assert result.status_code == 200
    assert result.response["track_id"] == "TRK-FIN-0001"


def test_the_same_key_and_body_replays_the_stored_response(session: Session):
    """The second call must not write anything and must return the first answer."""
    first = get_or_store(
        session,
        key="key-2",
        route=ROUTE,
        request_hash=hash_request(BODY),
        response={"track_id": "TRK-FIN-0001", "state": "FINANCEABLE"},
    )
    replay = get_or_store(
        session,
        key="key-2",
        route=ROUTE,
        request_hash=hash_request(BODY),
        response={"track_id": "TRK-DIFFERENT", "state": "DISBURSED"},
    )

    assert replay.replayed is True
    assert replay.conflict is False
    assert replay.response == first.response, "the replay must return the first body, not the new one"
    assert replay.status_code == 200

    rows = session.execute(text("SELECT COUNT(*) FROM idempotency_keys WHERE key = 'key-2'")).one()
    assert rows[0] == 1, "a replay must not insert a second row"


def test_the_same_key_with_a_different_body_is_a_conflict(session: Session):
    get_or_store(
        session,
        key="key-3",
        route=ROUTE,
        request_hash=hash_request(BODY),
        response={"track_id": "TRK-FIN-0001"},
    )
    changed = {**BODY, "tenor_days": 45}
    conflict = get_or_store(
        session,
        key="key-3",
        route=ROUTE,
        request_hash=hash_request(changed),
        response={"track_id": "TRK-SHOULD-NOT-EXIST"},
    )

    assert conflict.conflict is True
    assert conflict.replayed is True
    assert conflict.status_code == 409
    assert conflict.response["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    details = conflict.response["error"]["details"]
    assert details["sent_request_hash"] == hash_request(changed)
    assert details["stored_request_hash"] == hash_request(BODY)


def test_a_conflict_does_not_overwrite_the_stored_response(session: Session):
    get_or_store(
        session,
        key="key-4",
        route=ROUTE,
        request_hash=hash_request(BODY),
        response={"track_id": "TRK-FIRST"},
    )
    get_or_store(
        session,
        key="key-4",
        route=ROUTE,
        request_hash=hash_request({**BODY, "tenor_days": 45}),
        response={"track_id": "TRK-SECOND"},
    )
    stored = session.execute(
        text("SELECT response_json FROM idempotency_keys WHERE key = 'key-4'")
    ).one()
    assert "TRK-FIRST" in stored[0]
    assert "TRK-SECOND" not in stored[0]


def test_the_same_key_on_a_different_route_is_independent(session: Session):
    """A key scopes to (key, route), so two routes cannot block each other."""
    money = get_or_store(
        session,
        key="key-5",
        route="/api/v1/recovery",
        request_hash=hash_request(BODY),
        response={"track_id": "TRK-REC"},
    )
    financing = get_or_store(
        session,
        key="key-5",
        route=ROUTE,
        request_hash=hash_request(BODY),
        response={"track_id": "TRK-FIN"},
    )
    assert money.replayed is False
    assert financing.replayed is False
    assert financing.response["track_id"] == "TRK-FIN"


def test_the_request_hash_is_key_order_independent(session: Session):
    """Same body, different key order, must replay rather than conflict."""
    get_or_store(
        session,
        key="key-6",
        route=ROUTE,
        request_hash=hash_request({"tenor_days": 30, "accepted_amount": "1250000.00"}),
        response={"track_id": "TRK-FIN-0001"},
    )
    replay = get_or_store(
        session,
        key="key-6",
        route=ROUTE,
        request_hash=hash_request({"accepted_amount": "1250000.00", "tenor_days": 30}),
        response={"track_id": "IGNORED"},
    )
    assert replay.replayed is True
    assert replay.conflict is False
