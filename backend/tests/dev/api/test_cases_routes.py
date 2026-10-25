"""The v1.1 case routes: create, list, detail, events.

The v1.0 contract is the thing at risk here, so several tests exist only to prove
`POST /api/v1/evaluate-case` still behaves exactly as it did and still creates no
state.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, time
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from backend.app import deps
from backend.store import db as store_db
from backend.store.models import Track
from backend.store.ids import new_ulid
from backend.workflow.transitions import available_actions

ROOT = Path(__file__).resolve().parents[4]
PRESET = json.loads((ROOT / "contracts" / "fixtures" / "case_01.request.json").read_text())


def _create(client: TestClient, **overrides) -> dict:
    response = client.post("/api/v1/cases", json={**PRESET, **overrides})
    assert response.status_code == 201, response.text[:400]
    return response.json()


class FixedClock:
    """A clock pinned to one moment, so "the day changed" is testable."""

    simulated = True

    def __init__(self, moment: datetime) -> None:
        self._moment = moment

    def now(self) -> datetime:
        return self._moment


def _pin_clock(monkeypatch, day: date) -> None:
    moment = datetime.combine(day, time(12, 0), tzinfo=UTC)
    monkeypatch.setattr(deps, "get_adapters", lambda: SimpleNamespace(clock=FixedClock(moment)))


# ----------------------------------------------------------------- create ----


def test_create_from_a_preset_returns_case_detail(client):
    body = _create(client)
    assert body["case"]["id"], "the server must issue an id"
    assert len(body["case"]["id"]) == 26, "a ULID, not a client string"
    assert body["case"]["invoice_no"] == "synthetic-INV-001"
    assert body["case"]["accepted_amount"] == "1250000.00"
    assert body["latest_evaluation"]["case_id"] == body["case"]["id"], (
        "the stored evaluation must belong to the stored case"
    )
    assert body["active_track"] is None, "a new case has no track"
    assert body["available_actions"] == available_actions(None)


def test_the_client_cannot_choose_the_case_id(client):
    """An id a client can pick is an id a client can collide with or forge."""
    body = _create(client, case_id="case_01")
    assert body["case"]["id"] != "case_01"
    assert body["latest_evaluation"]["case_id"] == body["case"]["id"]


def test_create_records_a_case_created_event(client):
    body = _create(client)
    events = client.get(f"/api/v1/cases/{body['case']['id']}/events").json()
    assert [event["type"] for event in events] == ["case.created"]
    assert events[0]["seq"] == 1
    assert events[0]["actor"] == "USER"
    assert events[0]["prev_hash"] == "0" * 64


def test_create_returns_a_location_header(client):
    response = client.post("/api/v1/cases", json=PRESET)
    assert response.status_code == 201
    assert response.headers["Location"] == f"/api/v1/cases/{response.json()['case']['id']}"


def test_buyer_contact_is_not_persisted(client):
    """Personal data is accepted for the invite draft and must not be stored."""
    phone = "+91 90000 00042"
    email = "buyer.contact@example.test"
    body = _create(client, buyer_contact={"name": "Buyer Ops", "phone": phone, "email": email})
    case_id = body["case"]["id"]

    with store_db.session_scope() as session:
        tables = [
            row[0]
            for row in session.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            ).all()
        ]
        for table in tables:
            rows = session.execute(text(f"SELECT * FROM {table}")).all()
            for row in rows:
                blob = " ".join(str(value) for value in row)
                assert phone not in blob, f"phone number leaked into {table}"
                assert email not in blob, f"email leaked into {table}"

    # And it is not echoed back either.
    detail = client.get(f"/api/v1/cases/{case_id}").json()
    assert "buyer_contact" not in json.dumps(detail)


# ------------------------------------------------------------------- list ----


def test_list_returns_the_created_case(client):
    body = _create(client)
    listed = client.get("/api/v1/cases").json()

    assert listed["count"] == 1
    row = listed["cases"][0]
    assert row["id"] == body["case"]["id"]
    assert row["invoice_no"] == "synthetic-INV-001"
    assert row["accepted_amount"] == "1250000.00"
    assert isinstance(row["days_overdue"], int)
    assert row["state"] == "NEW"
    assert row["stage"] is not None
    assert row["available_actions"] == available_actions(None)


def test_list_is_empty_before_anything_is_created(client):
    listed = client.get("/api/v1/cases").json()
    assert listed == {"cases": [], "count": 0}


# ----------------------------------------------------------------- detail ----


def test_detail_includes_available_actions(client):
    body = _create(client)
    detail = client.get(f"/api/v1/cases/{body['case']['id']}").json()
    assert detail["available_actions"] == ["check_financeability", "start_recovery"]


def test_available_actions_follow_the_track_state(client):
    """Once a bid is signed the receivable is assigned, so recovery is locked."""
    body = _create(client)
    case_id = body["case"]["id"]

    with store_db.session_scope() as session:
        session.add(
            Track(
                id=new_ulid(),
                case_id=case_id,
                kind="FINANCING",
                state="AWAITING_ESIGN",
                version=1,
            )
        )

    detail = client.get(f"/api/v1/cases/{case_id}").json()
    assert detail["active_track"]["state"] == "AWAITING_ESIGN"
    assert "switch_to_recovery" not in detail["available_actions"], (
        "after signature, recovery actions must not be offered"
    )
    assert detail["available_actions"] == ["complete_esign", "cancel_financing"]


def test_a_missing_case_is_404(client):
    response = client.get("/api/v1/cases/DOESNOTEXIST0000000000000")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_missing_case_events_is_404(client):
    assert client.get("/api/v1/cases/NOPE/events").status_code == 404
    assert client.get("/api/v1/cases/NOPE/events/verify").status_code == 404


# ----------------------------------------------------------------- events ----


def test_the_chain_verifies(client):
    body = _create(client)
    case_id = body["case"]["id"]
    result = client.get(f"/api/v1/cases/{case_id}/events/verify").json()
    assert result == {"valid": True, "checked": 1, "first_bad_seq": None}


def test_tampering_is_reported_by_the_verify_route(client):
    body = _create(client)
    case_id = body["case"]["id"]

    with store_db.session_scope() as session:
        session.execute(
            text("UPDATE events SET payload_json = :p WHERE case_id = :c AND seq = 1"),
            {"p": '{"tampered":true}', "c": case_id},
        )

    result = client.get(f"/api/v1/cases/{case_id}/events/verify").json()
    assert result["valid"] is False
    assert result["first_bad_seq"] == 1


# ------------------------------------------------------- re-evaluation ----


def test_the_case_is_re_evaluated_when_the_day_changes(client, monkeypatch):
    """s.16 interest accrues daily; a stale snapshot would show yesterday's money."""
    body = _create(client)
    case_id = body["case"]["id"]
    first_calculation = body["latest_evaluation"]["calculation_date"]
    first_interest = body["latest_evaluation"]["financials"]["interest_total"]

    _pin_clock(monkeypatch, date.fromisoformat(first_calculation))
    same_day = client.get(f"/api/v1/cases/{case_id}").json()
    assert same_day["latest_evaluation"]["calculation_date"] == first_calculation

    with store_db.session_scope() as session:
        count_before = session.execute(
            text("SELECT COUNT(*) FROM evaluations WHERE case_id = :c"), {"c": case_id}
        ).one()[0]

    later = date.fromisoformat(first_calculation).replace(day=28)
    _pin_clock(monkeypatch, later)
    refreshed = client.get(f"/api/v1/cases/{case_id}").json()
    assert refreshed["latest_evaluation"]["calculation_date"] == later.isoformat()
    assert refreshed["latest_evaluation"]["financials"]["interest_total"] != first_interest

    with store_db.session_scope() as session:
        count_after = session.execute(
            text("SELECT COUNT(*) FROM evaluations WHERE case_id = :c"), {"c": case_id}
        ).one()[0]
    assert count_after == count_before + 1, "the new snapshot must be stored, not replaced"
    assert refreshed["latest_evaluation"]["case_id"] == case_id


def test_the_same_day_does_not_create_a_second_evaluation(client, monkeypatch):
    body = _create(client)
    case_id = body["case"]["id"]
    _pin_clock(monkeypatch, date.fromisoformat(body["latest_evaluation"]["calculation_date"]))

    client.get(f"/api/v1/cases/{case_id}")
    client.get(f"/api/v1/cases/{case_id}")
    client.get("/api/v1/cases")

    with store_db.session_scope() as session:
        count = session.execute(
            text("SELECT COUNT(*) FROM evaluations WHERE case_id = :c"), {"c": case_id}
        ).one()[0]
    assert count == 1, "reading on the same day must not add a snapshot"


# ------------------------------------------------------ the v1 contract ----


def test_evaluate_case_is_unchanged_and_creates_no_state(client):
    """The stateless endpoint stays stateless: that is the constraint."""
    before = client.get("/api/v1/cases").json()["count"]
    response = client.post("/api/v1/evaluate-case", json=PRESET)
    assert response.status_code == 200

    body = response.json()
    assert body["contract_version"] == "1.0"
    assert body["case_id"] == PRESET["case_id"], "the client's case_id is echoedback"
    assert set(body) == {
        "contract_version",
        "case_id",
        "calculation_date",
        "jurisdiction",
        "timeline",
        "financials",
        "buyer_cost",
        "limitation",
        "defenses",
        "evidence_readiness",
        "citations",
        "assumptions",
        "warnings",
    }
    assert client.get("/api/v1/cases").json()["count"] == before, (
        "evaluate-case must not create a case"
    )


def test_both_entry_points_agree_on_the_numbers(client):
    """The stateful route wraps the same engine, so the money must match exactly."""
    stateless = client.post("/api/v1/evaluate-case", json=PRESET).json()
    created = _create(client)

    assert created["latest_evaluation"]["financials"] == stateless["financials"]
    assert created["latest_evaluation"]["timeline"] == stateless["timeline"]


def test_the_simulation_header_is_on_the_new_routes(client):
    response = client.post("/api/v1/cases", json=PRESET)
    assert response.headers.get("X-Simulation") == "true"
