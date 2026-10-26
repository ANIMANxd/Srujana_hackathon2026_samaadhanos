"""Recovery routes: the v3 ladder wired to the state machine, and the lock.

The artifact content is not under test here (the v1.0 artifact suite covers it);
what is under test is *when* a draft may be prepared, what the track does, and that
the server never claims to have sent anything.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import select

from backend.app.schemas_v4 import TrackState
from backend.store import db as store_db
from backend.store.models import Track

ROOT = Path(__file__).resolve().parents[4]
PRESET = json.loads((ROOT / "contracts" / "fixtures" / "case_01.request.json").read_text())

# Not yet due, so Option 1 is financeable and the pause path can be exercised.
OPEN_PRESET = {
    **PRESET,
    "transaction": {
        **PRESET["transaction"],
        "contract_date": "2026-08-01",
        "supply_date": "2026-09-14",
        "delivery_date": "2026-09-14",
        "invoice_date": "2026-09-16",
        "calculation_date": "2026-10-25",
    },
}

RECOVERY = "/api/v1/cases/{case_id}/recovery"
MARK_SENT = "/api/v1/cases/{case_id}/recovery/mark-sent"
ODR_FILED = "/api/v1/cases/{case_id}/recovery/odr-filed"
FINANCING = "/api/v1/cases/{case_id}/financing"


def _headers(version: int, key: str) -> dict[str, str]:
    return {"Idempotency-Key": key, "If-Match": str(version)}


def _create(client: TestClient, payload: dict = PRESET) -> str:
    response = client.post("/api/v1/cases", json=payload)
    assert response.status_code == 201, response.text[:400]
    return response.json()["case"]["id"]


def _prepare(client: TestClient, case_id: str, stage: int, version: int, key: str) -> dict:
    response = client.post(RECOVERY.format(case_id=case_id), json={"stage": stage}, headers=_headers(version, key))
    assert response.status_code == 200, response.text[:500]
    return response.json()


# ------------------------------------------------------------------ ladder ----


def test_prepare_mark_sent_then_next_stage(client):
    """prepare -> mark sent -> prepare the next stage, each with its own event."""
    case_id = _create(client)

    first = _prepare(client, case_id, 1, 0, "p1")
    assert first["track"]["kind"] == "RECOVERY"
    assert first["track"]["state"] == "STAGE_1_PREPARED"
    assert first["stage"] == 1
    assert first["draft"]["kind"] == "STAGE1_BALANCE_CONFIRMATION"
    assert first["draft"]["markdown"].startswith("# DRAFT"), "the existing draft banner survives"
    assert first["draft"]["pdf_base64"], "the existing PDF rail is reused"

    sent = client.post(
        MARK_SENT.format(case_id=case_id),
        json={"stage": 1, "channel": "whatsapp"},
        headers=_headers(first["track"]["version"], "s1"),
    )
    assert sent.status_code == 200, sent.text[:400]
    assert sent.json()["track"]["state"] == "STAGE_1_SENT_BY_OWNER"
    assert sent.json()["channel"] == "whatsapp"
    assert sent.json()["draft"] is None, "marking sent produces no new draft"

    second = _prepare(client, case_id, 2, sent.json()["track"]["version"], "p2")
    assert second["track"]["state"] == "STAGE_2_PREPARED"
    assert second["draft"]["kind"] == "STAGE2_CFO_MEMO"

    types = [event["type"] for event in client.get(f"/api/v1/cases/{case_id}/events").json()]
    assert types == [
        "case.created",
        "customer.created",
        "customer.attached",
        "track.created",
        "recovery.prepare",
        "recovery.mark_sent",
        "recovery.prepare",
    ]


def test_mark_sent_records_the_channel_and_the_owner(client):
    """Nothing is sent by the server; the event records a claim about the owner."""
    case_id = _create(client)
    first = _prepare(client, case_id, 1, 0, "p1")
    client.post(
        MARK_SENT.format(case_id=case_id),
        json={"stage": 1, "channel": "email"},
        headers=_headers(first["track"]["version"], "s1"),
    )
    events = client.get(f"/api/v1/cases/{case_id}/events").json()
    sent = next(event for event in events if event["type"] == "recovery.mark_sent")
    assert sent["actor"] == "USER"
    assert sent["payload_json"]["channel"] == "email"
    assert sent["payload_json"]["sent_by"] == "owner"


def test_each_sent_channel_is_accepted(client):
    for index, channel in enumerate(("whatsapp", "email", "other")):
        case_id = _create(client)
        first = _prepare(client, case_id, 1, 0, f"p{index}")
        response = client.post(
            MARK_SENT.format(case_id=case_id),
            json={"stage": 1, "channel": channel},
            headers=_headers(first["track"]["version"], f"s{index}"),
        )
        assert response.status_code == 200, response.text[:300]


def test_marking_a_stage_sent_before_preparing_it_is_409(client):
    case_id = _create(client)
    _prepare(client, case_id, 1, 0, "p1")
    response = client.post(
        MARK_SENT.format(case_id=case_id),
        json={"stage": 3, "channel": "email"},
        headers=_headers(2, "s-bad"),
    )
    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "INVALID_TRANSITION"
    assert error["details"]["state"] == "STAGE_1_PREPARED"


def test_the_ladder_does_not_go_backwards(client):
    case_id = _create(client)
    second = _prepare(client, case_id, 2, 0, "p2")
    assert second["track"]["state"] == "STAGE_2_PREPARED"

    back = client.post(
        RECOVERY.format(case_id=case_id),
        json={"stage": 1},
        headers=_headers(second["track"]["version"], "p1-again"),
    )
    assert back.status_code == 409
    assert back.json()["error"]["code"] == "INVALID_TRANSITION"
    assert "backwards" in back.json()["error"]["message"]


def test_stage_four_reaches_pack_ready_and_needs_an_explicit_filing(client):
    """ODR_FILED_BY_OWNER is recorded only when the owner says they filed."""
    case_id = _create(client)
    pack = _prepare(client, case_id, 4, 0, "p4")
    assert pack["track"]["state"] == "STAGE_4_PACK_READY"
    assert pack["draft"]["kind"] == "STAGE4_EVIDENCE_PACK"

    premature = client.post(
        ODR_FILED.format(case_id=case_id),
        headers=_headers(pack["track"]["version"], "filed-early"),
    )
    assert premature.status_code == 200, "the state machine allows it from PACK_READY"

    filed = client.post(
        ODR_FILED.format(case_id=case_id),
        headers=_headers(premature.json()["track"]["version"], "filed-again"),
    )
    assert filed.status_code == 409, "filing twice is not a transition"
    assert filed.json()["error"]["code"] == "INVALID_TRANSITION"


def test_odr_filed_is_only_reachable_from_pack_ready(client):
    case_id = _create(client)
    _prepare(client, case_id, 1, 0, "p1")
    response = client.post(
        ODR_FILED.format(case_id=case_id), headers=_headers(2, "filed-too-soon")
    )
    assert response.status_code == 409
    assert response.json()["error"]["details"]["state"] == "STAGE_1_PREPARED"


# -------------------------------------------------------------------- lock ----


@pytest.mark.parametrize(
    "state",
    [
        TrackState.AWAITING_ESIGN,
        TrackState.AWAITING_DISBURSEMENT,
        TrackState.DISBURSED,
    ],
)
def test_recovery_is_locked_once_the_invoice_is_financed(client, state):
    """Section 5.3: after signature the receivable belongs to the financier."""
    case_id = _create(client)
    with store_db.session_scope() as session:
        session.add(
            Track(
                id="TRK-FIN-LOCK",
                case_id=case_id,
                kind="FINANCING",
                state=state.value,
                version=4,
            )
        )

    for method, path, body in (
        ("post", RECOVERY.format(case_id=case_id), {"stage": 1}),
        ("post", MARK_SENT.format(case_id=case_id), {"stage": 1, "channel": "email"}),
    ):
        response = getattr(client, method)(path, json=body, headers=_headers(0, f"lock-{state.value}"))
        assert response.status_code == 409, f"{path} must be locked"
        error = response.json()["error"]
        assert error["code"] == "RECOVERY_LOCKED"
        assert error["message"] == "This invoice is financed; recovery actions are locked."


def test_financing_is_refused_when_recovery_is_past_stage_three(client):
    """The other side of the same table row."""
    case_id = _create(client, OPEN_PRESET)
    pack = _prepare(client, case_id, 4, 0, "p4")
    assert pack["track"]["state"] == "STAGE_4_PACK_READY"

    response = client.post(FINANCING.format(case_id=case_id), headers=_headers(0, "fin-after-stage4"))
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "RECOVERY_STAGE_LOCKED"


# ------------------------------------------------------------------ pause ----


def test_starting_financing_pauses_recovery_before_stage_three(client):
    """Paused, not deleted: the stage survives and a later recovery resumes it."""
    case_id = _create(client, OPEN_PRESET)

    first = _prepare(client, case_id, 1, 0, "p1")
    assert first["track"]["state"] == "STAGE_1_PREPARED"
    stage_before = first["track"]["state"]

    financed = client.post(FINANCING.format(case_id=case_id), headers=_headers(0, "fin-pause"))
    assert financed.status_code == 200, financed.text[:400]
    assert financed.json()["track"]["kind"] == "FINANCING"

    events = client.get(f"/api/v1/cases/{case_id}/events").json()
    paused = [event for event in events if event["type"] == "recovery.paused"]
    assert len(paused) == 1, "the pause must be in the audit trail"
    assert paused[0]["payload_json"]["from_state"] == stage_before
    assert paused[0]["payload_json"]["reason"] == "financing_started"

    with store_db.session_scope() as session:
        rows = session.exec(select(Track).where(Track.case_id == case_id)).all()
        recovery = next(row for row in rows if row.kind == "RECOVERY")
        financing = next(row for row in rows if row.kind == "FINANCING")
    assert recovery.closed_at is not None, "the recovery row is closed, so one track stays active"
    assert financing.closed_at is None
    assert recovery.state == stage_before, "the stage is preserved for a resume"


def test_a_paused_recovery_resumes_at_its_stage(client):
    """Cancel the financing, then recovery picks up where it left off."""
    case_id = _create(client, OPEN_PRESET)
    _prepare(client, case_id, 2, 0, "p2")

    financed = client.post(FINANCING.format(case_id=case_id), headers=_headers(0, "fin-pause"))
    version = financed.json()["track"]["version"]

    with store_db.session_scope() as session:
        row = session.exec(
            select(Track).where(Track.case_id == case_id, Track.kind == "FINANCING")
        ).first()
        assert row is not None
        row.closed_at = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)
        state = row.state

    resumed = client.post(RECOVERY.format(case_id=case_id), json={"stage": 2}, headers=_headers(0, "p2-resume"))
    assert resumed.status_code == 200, resumed.text[:500]
    assert resumed.json()["track"]["state"] == "STAGE_2_PREPARED", (
        f"resumed from the preserved stage, not from NEW (financing was {state})"
    )
    assert resumed.json()["track"]["version"] == 1, "one track.created, no transition needed"


def test_pausing_is_not_reachable_without_a_financeable_verdict(client):
    """An overdue case cannot absorb the recovery track into a financing attempt."""
    case_id = _create(client)  # the shipped preset: 200+ days overdue
    _prepare(client, case_id, 1, 0, "p1")

    response = client.post(FINANCING.format(case_id=case_id), headers=_headers(0, "fin-overdue"))
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "TRACK_ALREADY_ACTIVE", (
        "the recovery track stays open because financing never started"
    )
