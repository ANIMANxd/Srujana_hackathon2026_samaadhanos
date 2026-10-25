"""Every section 7.4 scenario, run **end to end against the live API**.

This is the acceptance test for the scenario work: two real uvicorn processes (the API
and this mock service), real signed webhooks over HTTP, and one assertion per scenario
on the track state that architecture_v4 section 5.1 predicts.

It is deliberately slow-ish (two subprocesses) and deliberately not a unit test: a
scenario that only works because a fake skipped the network has not been tested.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
API_PORT = 8021
MOCK_PORT = 8121
API = f"http://127.0.0.1:{API_PORT}"
MOCK = f"http://127.0.0.1:{MOCK_PORT}"

SECRETS = {
    "WEBHOOK_SECRET_ESIGN": "e2e-esign",
    "WEBHOOK_SECRET_MARKETPLACE": "e2e-marketplace",
    "WEBHOOK_SECRET_DISBURSEMENT": "e2e-disbursement",
}

# Not yet due, so Option 1 is financeable. Delivery 2026-09-14 + 45 days = 2026-10-29.
PRESET = json.loads((ROOT / "contracts" / "fixtures" / "case_01.request.json").read_text())
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


# ------------------------------------------------------------------ helpers ----


def _call(method: str, url: str, body: dict | None = None, headers: dict | None = None):
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json", **(headers or {})}, method=method
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()
            return response.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        return exc.code, (json.loads(raw) if raw else {})


def api(method: str, path: str, body: dict | None = None, headers: dict | None = None):
    return _call(method, f"{API}{path}", body, headers)


def mock(method: str, path: str, body: dict | None = None):
    return _call(method, f"{MOCK}{path}", body)


def _wait_for(url: str, attempts: int = 120) -> None:
    for _ in range(attempts):
        try:
            status, _body = _call("GET", url)
            if status == 200:
                return
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            pass
        time.sleep(0.25)
    raise RuntimeError(f"{url} never became ready")


def _state(case_id: str) -> str:
    """The track's current state, including terminal ones.

    `CaseDetail.active_track` is null once a track closes, so a terminal state
    (BUYER_DECLINED, NO_BIDS, ...) is read from the last transition event instead.
    """
    _status, detail = api("GET", f"/api/v1/cases/{case_id}")
    track = detail.get("active_track")
    if track:
        return track["state"]

    _status, events = api("GET", f"/api/v1/cases/{case_id}/events")
    for event in reversed(events):
        if event["type"].startswith(("financing.", "recovery.")):
            target = (event.get("payload_json") or {}).get("to")
            if target:
                return target
    return "NEW"


def wait_for_state(case_id: str, expected: set[str], *, timeout: float = 25.0) -> str:
    deadline = time.time() + timeout
    last = "?"
    while time.time() < deadline:
        last = _state(case_id)
        if last in expected:
            return last
        time.sleep(0.3)
    raise AssertionError(f"expected one of {sorted(expected)}, stayed at {last}")


# --------------------------------------------------------------- fixtures ----


@pytest.fixture(scope="module")
def stack() -> Iterator[dict]:
    database = f"sqlite:///{tempfile.mkdtemp()}/e2e.db"
    common = dict(os.environ)
    common.update({"PYTHONPATH": str(ROOT), **SECRETS, "APP_ENV": "development"})

    api_env = dict(common)
    api_env.update(
        {
            "DATABASE_URL": database,
            "PROVIDER_MODE": "mock",
            "MOCK_PROVIDERS_URL": MOCK,
            "MOCK_CLOCK": "1",
        }
    )
    mock_env = dict(common)
    mock_env.update(
        {
            "API_BASE_URL": API,
            "MOCK_BUYER_ACCEPT_DELAY_S": "0",
            "MOCK_BID_DELAY_S": "0",
            "MOCK_PAYOUT_DELAY_S": "0",
            "MOCK_DELAYED_S": "0.4",
            "MOCK_EXPIRE_DELAY_S": "0.2",
            "MOCK_RETRY_DELAY_S": "0.2",
            "MOCK_DEFAULT_DELAY_S": "1.0",
        }
    )

    log_dir = Path(tempfile.mkdtemp(prefix="e2e-logs-"))
    api_log = open(log_dir / "api.log", "w", encoding="utf-8")  # noqa: SIM115
    mock_log = open(log_dir / "mock.log", "w", encoding="utf-8")  # noqa: SIM115

    processes = [
        subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "backend.app.main:app", "--port", str(API_PORT), "--log-level", "warning"],
            env=api_env,
            cwd=str(ROOT),
            stdout=api_log,
            stderr=api_log,
        ),
        subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "mock_providers.app:app", "--port", str(MOCK_PORT), "--log-level", "error"],
            env=mock_env,
            cwd=str(ROOT),
            stdout=mock_log,
            stderr=mock_log,
        ),
    ]
    try:
        _wait_for(f"{API}/api/v1/health")
        _wait_for(f"{MOCK}/health")
        yield {"api": API, "mock": MOCK, "logs": log_dir}
    finally:
        for process in processes:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()


@pytest.fixture()
def run(stack) -> Iterator[dict]:
    """A clean simulation for one scenario."""
    mock("POST", "/mock/reset")
    yield stack


# ------------------------------------------------------------- the drivers ----


def _start(stack) -> str:
    status, created = api("POST", "/api/v1/cases", OPEN_PRESET)
    assert status == 201, created
    case_id = created["case"]["id"]
    status, started = api(
        "POST", f"/api/v1/cases/{case_id}/financing", {}, {"Idempotency-Key": f"start-{case_id}", "If-Match": "0"}
    )
    assert status == 200, started
    assert started["track"]["state"] == "FINANCEABLE"
    return case_id


def _buyer_accepts(stack, case_id: str) -> None:
    _status, detail = api("GET", f"/api/v1/cases/{case_id}")
    version = detail["active_track"]["version"]
    status, body = api(
        "POST",
        f"/api/v1/cases/{case_id}/financing/buyer-acceptance",
        {},
        {"Idempotency-Key": f"accept-{case_id}", "If-Match": str(version)},
    )
    assert status == 200, body


def _open_bidding(stack, case_id: str, *, expect_bids: bool = True) -> None:
    """The API registered the unit; this opens the window on the mock directly.

    A real deployment would have the API call this after the buyer accepts; here the
    harness plays that part so the scenario is deterministic rather than a race with
    the mock's accept delay.
    """
    _status, units = mock("GET", "/marketplace/factoring-units")
    unit = next(item for item in units["units"] if item["acceptance"] == "ACCEPTED")
    status, body = mock("POST", f"/marketplace/factoring-units/{unit['unit_id']}/bidding", {"window_seconds": 60})
    assert status == 200, f"bidding was refused: {body}"
    _status, listed = mock("GET", f"/marketplace/factoring-units/{unit['unit_id']}/bids")
    if expect_bids:
        assert listed["bids"], "the mock opened bidding but produced no bids"


def _to_bids_available(case_id: str, *, expect_bids: bool = True) -> None:
    """Drive to BIDS_AVAILABLE, tolerating the accept-poll race.

    The API polls the buyer decision once per request; if the mock's settle task has
    not run yet the route stays at AWAITING. Re-posting the acceptance re-polls with
    the current version, which is exactly what a client would do.
    """
    for _ in range(8):
        state = _state(case_id)
        if state == "BIDS_AVAILABLE":
            return
        if state == "AWAITING_BUYER_ACCEPTANCE":
            _buyer_accepts(None, case_id)
        elif state == "BIDDING_OPEN":
            _open_bidding(None, case_id)
        else:
            return
        time.sleep(0.4)
    wait_for_state(case_id, {"BIDS_AVAILABLE"})


def _select_bid(case_id: str) -> str:
    _status, detail = api("GET", f"/api/v1/cases/{case_id}")
    version = detail["active_track"]["version"]
    _status, bids = api("GET", f"/api/v1/cases/{case_id}/financing/bids")
    bid = bids["bids"][0]  # the contract model calls the field `id`
    status, body = api(
        "POST",
        f"/api/v1/cases/{case_id}/financing/bids/{bid['id']}/select",
        {},
        {"Idempotency-Key": f"select-{case_id}", "If-Match": str(version)},
    )
    assert status == 200, body
    session = body.get("esign_session")
    assert session, "the select route must create a signing session"
    return session["session_id"]


def _otp(session_id: str, code: str):
    return mock("POST", f"/esign/sessions/{session_id}/otp", {"otp": code})


# ------------------------------------------------------------------ the table ----
# name -> (driver, set of acceptable end states). Section 5.1 is the source of truth.
EXPECTED: dict[str, set[str]] = {
    "happy_path": {"DISBURSED"},
    "buyer_rejects": {"BUYER_DECLINED"},
    "buyer_window_expires": {"BUYER_DECLINED"},
    "no_bids": {"NO_BIDS"},
    "bids_expire": {"BIDDING_OPEN"},
    "esign_wrong_otp": {"BIDS_AVAILABLE"},
    "esign_expires": {"BIDS_AVAILABLE"},
    "webhook_duplicate": {"AWAITING_DISBURSEMENT", "DISBURSED"},
    "webhook_out_of_order": {"DISBURSED"},
    "webhook_bad_signature": {"AWAITING_ESIGN"},
    "webhook_delayed": {"AWAITING_DISBURSEMENT", "DISBURSED"},
    "payout_failed_then_succeeds": {"DISBURSED"},
    "buyer_defaults_after_disbursal": {"SETTLED_WITHOUT_RECOURSE"},
}


def _drive(scenario: str, stack) -> str:
    """Run one scenario and return the case id once it has been driven."""
    case_id = _start(stack)
    mock("POST", "/mock/scenarios", {"case_id": case_id, "scenario": scenario})

    if scenario in {"buyer_rejects", "buyer_window_expires"}:
        _buyer_accepts(None, case_id)
        return case_id

    _buyer_accepts(None, case_id)

    if scenario == "no_bids":
        # No bids by design: open the window and expect NO_BIDS, not BIDS_AVAILABLE.
        wait_for_state(case_id, {"BIDDING_OPEN"})
        _open_bidding(None, case_id, expect_bids=False)
        return case_id

    if scenario == "bids_expire":
        _to_bids_available(case_id)
        return case_id

    # Everything else needs a selected bid and a signature.
    _to_bids_available(case_id)
    session_id = _select_bid(case_id)

    if scenario == "esign_wrong_otp":
        for _ in range(3):
            _otp(session_id, "000000")
        return case_id

    if scenario == "esign_expires":
        _otp(session_id, "123456")
        return case_id

    if scenario == "webhook_bad_signature":
        _otp(session_id, "123456")
        return case_id

    _otp(session_id, "123456")
    return case_id


@pytest.mark.parametrize("scenario", sorted(EXPECTED))
def test_scenario_ends_in_the_state_section_5_1_predicts(scenario, run):
    case_id = _drive(scenario, run)
    ended = wait_for_state(case_id, EXPECTED[scenario])
    assert ended in EXPECTED[scenario]


def test_the_scenario_is_recorded_per_case(run):
    case_id = _start(run)
    mock("POST", "/mock/scenarios", {"case_id": case_id, "scenario": "no_bids"})
    _status, body = mock("GET", f"/mock/scenarios/{case_id}")
    assert body["scenario"] == "no_bids"
    assert body["active"] is True
    assert body["note"]


def test_an_unknown_case_reports_the_default(run):
    _status, body = mock("GET", "/mock/scenarios/01NOTAREALCASE")
    assert body["scenario"] == "happy_path"
    assert body["active"] is False


def test_deliveries_are_listed_newest_first_with_a_status(run):
    case_id = _start(run)
    # The scenario call is also what records the active case, which is how the mock
    # routes its webhooks when the API adapter sends no case id of its own.
    mock("POST", "/mock/scenarios", {"case_id": case_id, "scenario": "happy_path"})
    _buyer_accepts(None, case_id)
    wait_for_state(case_id, {"BIDDING_OPEN", "BIDS_AVAILABLE", "BUYER_DECLINED"})

    _status, body = mock("GET", "/mock/deliveries")
    assert body["deliveries"], "the fu.accepted delivery must be recorded"
    first = body["deliveries"][0]
    assert first["status"] in {"DELIVERED", "DEAD_LETTER", "PENDING"}
    assert first["attempt_count"] >= 1
    assert len(body["deliveries"]) <= 50
