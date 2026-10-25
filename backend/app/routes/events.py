"""Server-sent events for a case (`GET /api/v1/cases/{id}/stream`).

Emits `{type, track_state, version}` after each **committed** transition, plus a
comment heartbeat every 15 s so a proxy does not drop an idle connection.

The broker is in-process. That is honest for a single-worker demo and wrong for a
multi-worker deployment, which would need a real bus (Redis, Postgres NOTIFY, or a
poll of the `events` table). Say that out loud rather than implying it scales.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from backend.store.db import session_scope
from backend.store.models import Case as CaseRow

router = APIRouter(prefix="/api/v1", tags=["events"])

HEARTBEAT_SECONDS = 15.0

# case_id -> set of asyncio.Queue. Fans a committed transition out to every open stream.
_subscribers: dict[str, set[asyncio.Queue]] = {}


def publish_transition(case_id: str, message: dict[str, Any]) -> None:
    """Push one message to every stream watching this case. Safe with no subscribers."""
    for queue in list(_subscribers.get(case_id, ())):
        try:
            queue.put_nowait(message)
        except asyncio.QueueFull:  # pragma: no cover - a client that stopped reading
            pass


def _subscribe(case_id: str) -> asyncio.Queue:
    queue: asyncio.Queue = asyncio.Queue(maxsize=64)
    _subscribers.setdefault(case_id, set()).add(queue)
    return queue


def _unsubscribe(case_id: str, queue: asyncio.Queue) -> None:
    subscribers = _subscribers.get(case_id)
    if not subscribers:
        return
    subscribers.discard(queue)
    if not subscribers:
        _subscribers.pop(case_id, None)


def sse_message(payload: dict[str, Any]) -> str:
    """The wire format: one `data:` line and a blank line."""
    return f"data: {json.dumps(payload, separators=(',', ':'))}\n\n"


def heartbeat_message() -> str:
    """A comment line: ignored by EventSource, but it keeps the socket warm."""
    return ": heartbeat\n\n"


async def event_stream(
    case_id: str,
    *,
    heartbeat_seconds: float = HEARTBEAT_SECONDS,
    poll_seconds: float = 0.5,
) -> AsyncIterator[str]:
    """Yield events until the client disconnects.

    The heartbeat is time-based rather than count-based so an idle stream stays alive
    even when nothing happens, which is the normal state of a demo between actions.
    """
    queue = _subscribe(case_id)
    try:
        yield sse_message({"type": "stream.open", "track_state": "NEW", "version": 0})
        while True:
            try:
                message = await asyncio.wait_for(queue.get(), timeout=heartbeat_seconds)
            except TimeoutError:
                yield heartbeat_message()
                continue
            yield sse_message(message)
    except asyncio.CancelledError:  # pragma: no cover - client went away
        raise
    finally:
        _unsubscribe(case_id, queue)


@router.get("/cases/{case_id}/stream")
async def stream_case(case_id: str, request: Request) -> StreamingResponse:
    """Live track updates for one case. 404 for an unknown case, like the other reads."""
    with session_scope() as session:
        if session.get(CaseRow, case_id) is None:
            from backend.app.routes import cases as case_routes

            raise case_routes._not_found(case_id)

    return StreamingResponse(
        event_stream(case_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # nginx buffers text/event-stream unless told not to.
            "X-Accel-Buffering": "no",
        },
    )
