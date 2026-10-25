"""Store, secrets and signed-delivery helpers for the webhook tests."""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.app import deps, security
from backend.app.main import app
from backend.app.schemas_v4 import TrackState
from backend.store import db as store_db
from backend.store.ids import new_ulid
from backend.store.models import Track

ROOT = Path(__file__).resolve().parents[4]
PRESET = json.loads((ROOT / "contracts" / "fixtures" / "case_01.request.json").read_text())

SECRETS = {
    "esign": "test-secret-esign",
    "marketplace": "test-secret-marketplace",
    "disbursement": "test-secret-disbursement",
}


@pytest.fixture()
def database_url(tmp_path) -> str:
    return f"sqlite:///{tmp_path / 'webhooks.db'}"


@pytest.fixture()
def client(database_url, monkeypatch) -> Iterator[TestClient]:
    monkeypatch.setenv("DATABASE_URL", database_url)
    for provider, secret in SECRETS.items():
        monkeypatch.setenv(f"WEBHOOK_SECRET_{provider.upper()}", secret)
    store_db.dispose()
    store_db.init_db(database_url)
    with TestClient(app) as active:
        yield active
    store_db.dispose()


@pytest.fixture()
def case_id(client: TestClient) -> str:
    response = client.post("/api/v1/cases", json=PRESET)
    assert response.status_code == 201, response.text[:400]
    return response.json()["case"]["id"]


def open_track(case_id: str, state: TrackState, *, kind: str = "FINANCING") -> str:
    """Put a case into a given track state directly, for a focused webhook test."""
    with store_db.session_scope() as session:
        row = Track(
            id=new_ulid(),
            case_id=case_id,
            kind=kind,
            state=state.value,
            version=3,
        )
        session.add(row)
        session.flush()
        return row.id


def signed(provider: str, body: dict[str, Any], *, timestamp: int | None = None) -> tuple[bytes, dict[str, str]]:
    """Serialise and sign a delivery exactly as the mock provider would."""
    raw = json.dumps(body, separators=(",", ":")).encode("utf-8")
    stamp = str(int(time.time()) if timestamp is None else timestamp)
    return raw, {
        security.TIMESTAMP_HEADER: stamp,
        security.SIGNATURE_HEADER: security.signature_for(raw, stamp, SECRETS[provider]),
        security.EVENT_ID_HEADER: str(body["event_id"]),
        "Content-Type": "application/json",
    }


def deliver(client: TestClient, provider: str, body: dict[str, Any], **kwargs) -> Any:
    raw, headers = signed(provider, body, **kwargs)
    return client.post(f"/api/v1/webhooks/{provider}", content=raw, headers=headers)


def esign_body(case_id: str, event_id: str = "MOCK-EVT-ESIGN-1") -> dict[str, Any]:
    return {"case_id": case_id, "event_id": event_id, "type": "esign.completed"}


def payout_body(case_id: str, event_id: str = "MOCK-EVT-PAYOUT-1") -> dict[str, Any]:
    return {"case_id": case_id, "event_id": event_id, "type": "payout.processed", "payout_ref": "MOCK-PAYOUT-1"}


def bids_body(case_id: str, event_id: str = "MOCK-EVT-BIDS-1") -> dict[str, Any]:
    """Rates and validity only: no discount, fee or net from the provider."""
    return {
        "case_id": case_id,
        "event_id": event_id,
        "type": "bids.available",
        "accepted_amount": "1250000.00",
        "tenor_days": 4,
        "bids": [
            {
                "bid_id": "MOCK-BID-A",
                "financier_alias": "Financier A",
                "annual_rate": "12.00",
                "valid_until": "2026-10-26T09:00:00+00:00",
                # A hostile provider shipping its own money must be ignored.
                "discount": "999999.99",
                "net_amount": "1.00",
            },
            {
                "bid_id": "MOCK-BID-B",
                "financier_alias": "Financier B",
                "annual_rate": "8.00",
                "valid_until": "2026-10-26T09:00:00+00:00",
            },
        ],
    }


def track_state(case_id: str) -> str | None:
    with store_db.session_scope() as session:
        from sqlmodel import select

        row = session.exec(
            select(Track).where(Track.case_id == case_id, Track.closed_at.is_(None))
        ).first()
        return row.state if row else None


def inbox_outcome(provider_event_id: str) -> str | None:
    from backend.store.models import WebhookInbox

    with store_db.session_scope() as session:
        row = session.get(WebhookInbox, provider_event_id)
        return row.outcome if row else None


def event_types(case_id: str) -> list[str]:
    from sqlmodel import select

    from backend.store.models import Event

    with store_db.session_scope() as session:
        rows = session.exec(
            select(Event).where(Event.case_id == case_id).order_by(Event.seq.asc())
        ).all()
        return [row.type for row in rows]


def _now() -> datetime:
    return datetime.now(UTC)
