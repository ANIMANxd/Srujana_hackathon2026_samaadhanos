"""Signed provider webhooks (architecture_v4 section 8, `docs/webhooks.md`).

The order of operations is the whole point, and it is fixed here:

1. read the **raw bytes**;
2. verify HMAC-SHA256 over `timestamp + "." + raw_body` with
   `WEBHOOK_SECRET_<PROVIDER>`, constant-time;
3. check the timestamp is within 300 s -> else **401**;
4. only then parse -> malformed is **422**;
5. insert into `webhook_inbox` keyed by `provider_event_id`; a duplicate returns
   `200 {"duplicate": true}` with **no side effects**;
6. apply the transition **in the same transaction** as the inbox insert;
7. if the event is not valid for the current state, **park** it (outcome `parked`)
   and retry parked events after every later transition on that track.

Bids arrive as rates and validity only: `discount`, `fee` and `net_amount` are
computed by `backend/finance` here, so a provider cannot introduce a money bug.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlmodel import select

from backend.app import deps, security
from backend.app.schemas_v4 import TrackState
from backend.finance import FinanceConfig, bid_quote, finance_config
from backend.store import audit
from backend.store.db import session_scope
from backend.store.models import Bid as BidRow
from backend.store.models import Track, WebhookInbox
from backend.workflow import financing_sm, tracks

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])

PROVIDERS = ("esign", "marketplace", "disbursement")

# Provider event -> financing-track event. `bid.accepted` is absent on purpose: a bid
# is accepted by the supplier through a route, not announced by the marketplace.
EVENT_MAP: dict[str, dict[str, str]] = {
    "esign": {"esign.completed": "esign_completed"},
    "marketplace": {
        "fu.accepted": "buyer_accepted",
        "bids.available": "bids_received",
        "fu.rejected": "buyer_rejected",
    },
    "disbursement": {
        "payout.processed": "payout_processed",
        "payout.failed": "payout_failed",
    },
}


def _ok(payload: dict[str, Any], status: int = 200) -> JSONResponse:
    return JSONResponse(status_code=status, content=payload)


def _fail(status: int, code: str, message: str, details: dict[str, Any] | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status, content={"error": {"code": code, "message": message, "details": details}}
    )


# ---------------------------------------------------------------- handling ----


def _store_bids(session, *, case_id: str, track_id: str, payload: dict[str, Any], cfg: FinanceConfig) -> int:
    """Persist the provider's rates, with the money computed by `backend/finance`.

    The payload carries `annual_rate` and `valid_until` only (section 7.2): the mock
    is not allowed to send a discount, because a mock that computes money is a mock
    that can be wrong about money.
    """
    unit_amount = Decimal(str(payload.get("accepted_amount", "0")))
    tenor_days = int(payload.get("tenor_days", 0))
    rows = payload.get("bids") or []
    stored = 0
    for item in rows:
        bid_id = str(item["bid_id"])
        rate = Decimal(str(item["annual_rate"]))
        quote = bid_quote(unit_amount, rate, tenor_days, cfg)
        existing = session.get(BidRow, bid_id)
        if existing is not None:
            continue
        session.add(
            BidRow(
                id=bid_id,
                track_id=track_id,
                financier_alias=str(item.get("financier_alias", "Financier A")),
                annual_rate=rate,
                discount=quote["discount"],
                fee=quote["fee"],
                net_amount=quote["net_amount"],
                valid_until=datetime.fromisoformat(str(item["valid_until"])),
                status="AVAILABLE",
            )
        )
        stored += 1
    session.flush()
    return stored


def _apply_event(
    session, *, provider: str, payload: dict[str, Any], case_id: str | None
) -> tuple[str, str | None, str | None]:
    """Try to apply one event. Returns (outcome, track_id, reason).

    `PARKED` means the event is valid but the track is not in a state that accepts it
    yet - an out-of-order delivery. It is stored, not applied, and not dropped.
    """
    event_type = str(payload.get("type") or payload.get("event") or "")
    mapped = EVENT_MAP.get(provider, {}).get(event_type)
    if mapped is None:
        return "REJECTED", None, f"unknown event type {event_type!r} for provider {provider!r}"

    if case_id is None:
        case_id = payload.get("case_id")
    if not case_id:
        return "REJECTED", None, "the payload carries no case_id"

    track_row = tracks.active_track(session, case_id)
    if track_row is None:
        return "PARKED", None, "this case has no open track yet"

    if provider == "marketplace" and event_type == "bids.available":
        cfg = finance_config(__import__("backend.app.config_loader", fromlist=["load_config"]).load_config())
        _store_bids(session, case_id=case_id, track_id=track_row.id, payload=payload, cfg=cfg)

    try:
        track_row = tracks.apply_transition(
            session,
            track_row,
            event=mapped,
            expected_version=track_row.version,
            actor="PROVIDER_MOCK",
            payload={"provider_event": payload.get("event_id"), "provider": provider},
        )
    except (tracks.InvalidStep, financing_sm.InvalidTransition):
        return "PARKED", track_row.id, f"{mapped} is not valid while the track is {track_row.state}"
    except tracks.TrackError as exc:  # stale version, or a closed track
        return "PARKED", track_row.id, str(exc)

    return "APPLIED", track_row.id, None


def _retry_parked(session, *, track_id: str, now: datetime) -> int:
    """Re-try every parked event for this track, oldest first.

    Called after each successful transition, so an event that arrived too early is
    applied as soon as its turn comes rather than being lost.
    """
    parked = session.exec(
        select(WebhookInbox)
        .where(WebhookInbox.track_id == track_id, WebhookInbox.outcome == "PARKED")
        .order_by(WebhookInbox.received_at.asc())
    ).all()

    applied = 0
    for row in parked:
        outcome, _, reason = _apply_event(
            session, provider=row.provider, payload=row.payload_json, case_id=row.case_id
        )
        if outcome == "APPLIED":
            row.outcome = "APPLIED"
            row.processed_at = now
            applied += 1
        elif outcome == "REJECTED":
            row.outcome = "REJECTED"
        # PARKED stays parked: still waiting for its turn.
        _ = reason
    session.flush()
    return applied



def handle_with_body(provider: str, raw: bytes, headers: Any) -> JSONResponse:
    """Verify, dedupe, apply. Synchronous on purpose: the transaction must be one unit."""
    timestamp = headers.get(security.TIMESTAMP_HEADER)
    signature = headers.get(security.SIGNATURE_HEADER)
    event_id = headers.get(security.EVENT_ID_HEADER)

    secret = security.secret_for(provider)
    if not secret:
        return _fail(
            500,
            "WEBHOOK_SECRET_MISSING",
            f"WEBHOOK_SECRET_{provider.upper()} is not configured, so no delivery can be verified.",
        )
    if not security.verify_signature(raw, timestamp, signature, secret):
        # 401 before anything is parsed or stored.
        return _fail(401, "BAD_SIGNATURE", "The signature does not match this body.")
    if not security.timestamp_is_fresh(timestamp):
        return _fail(401, "STALE_WEBHOOK", "This delivery is outside the 300 second window.")

    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _fail(422, "MALFORMED_WEBHOOK", "The body is not valid JSON.")
    if not isinstance(payload, dict):
        return _fail(422, "MALFORMED_WEBHOOK", "The body must be a JSON object.")

    provider_event_id = event_id or payload.get("event_id")
    if not provider_event_id:
        return _fail(422, "MALFORMED_WEBHOOK", f"A {security.EVENT_ID_HEADER} header is required.")

    now = datetime.now(UTC)
    with session_scope() as session:
        if session.get(WebhookInbox, provider_event_id) is not None:
            return _ok({"duplicate": True, "provider_event_id": provider_event_id})

        case_id = payload.get("case_id")
        inbox = WebhookInbox(
            provider_event_id=str(provider_event_id),
            provider=provider,
            case_id=case_id,
            payload_json=payload,
            received_at=now,
            signature_ok=True,
            outcome="PENDING",
        )
        session.add(inbox)
        session.flush()

        outcome, track_id, reason = _apply_event(
            session, provider=provider, payload=payload, case_id=case_id
        )
        inbox.outcome = outcome
        inbox.track_id = track_id
        inbox.processed_at = now if outcome == "APPLIED" else None

        retried = 0
        if outcome == "APPLIED" and track_id is not None:
            # A transition may have unlocked an event that arrived too early.
            retried = _retry_parked(session, track_id=track_id, now=now)

        if outcome == "APPLIED":
            # Announce the committed transition to any open SSE stream.
            _publish(track_id, session)
    return _ok(
        {
            "duplicate": False,
            "outcome": outcome,
            "provider_event_id": str(provider_event_id),
            "retried_parked": retried,
            "reason": reason,
        }
    )


# ---------------------------------------------------------------- SSE bus ----
# A tiny in-process broker: `GET /cases/{id}/stream` subscribes, and a committed
# transition publishes. It is enough for one process, which is what the demo is.
# A multi-worker deployment would need a real bus (documented, not pretended).




def _publish(track_id: str, session) -> None:
    from backend.app.routes.events import publish_transition

    track_row = session.get(Track, track_id)
    if track_row is None:
        return
    publish_transition(
        track_row.case_id,
        {
            "type": "track.transition",
            "track_state": track_row.state,
            "version": track_row.version,
        },
    )


# ------------------------------------------------------------------ routes ----


@router.post("/esign")
async def esign_webhook(request: Request) -> JSONResponse:
    return handle_with_body("esign", await request.body(), request.headers)


@router.post("/marketplace")
async def marketplace_webhook(request: Request) -> JSONResponse:
    return handle_with_body("marketplace", await request.body(), request.headers)


@router.post("/disbursement")
async def disbursement_webhook(request: Request) -> JSONResponse:
    return handle_with_body("disbursement", await request.body(), request.headers)
