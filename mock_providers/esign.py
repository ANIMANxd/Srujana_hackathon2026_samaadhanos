"""Mock eSign (architecture_v4 section 7.1).

`POST /esign/sessions` opens a session; `POST /esign/sessions/{id}/otp` completes it
with a test OTP. Three wrong attempts fail the session; ten minutes and it expires.
Both outcomes are announced by a signed webhook (`esign.completed` / `esign.failed`).

**There is no Aadhaar field anywhere in this module.** The request model does not
declare one, and a body that smuggles `aadhaar_number` is ignored rather than stored
(golden rule 18). The "signature" is a SHA-256 of the document bytes plus a
SIMULATED stamp: no real signature exists in this service.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, ConfigDict

from mock_providers import bank, signer
from mock_providers.delivery import service
from mock_providers.state import ESignSession, store

router = APIRouter(prefix="/esign", tags=["esign"])

OTP_ATTEMPTS = 3
SESSION_MINUTES = 10


def api_url() -> str:
    base = os.environ.get("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    return f"{base}/api/v1/webhooks/esign"


def _now() -> datetime:
    return datetime.now(UTC)


def _stamp(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


class CreateSession(BaseModel):
    """Signer details only. No Aadhaar number is accepted, asked for or stored."""

    # `extra="ignore"` is the point: a client sending an Aadhaar number must not have
    # it retained anywhere, and it must not be echoed back either.
    model_config = ConfigDict(extra="ignore")

    doc_id: str
    doc_sha256: str
    title: str
    signer_display: str = "Demo Signer"
    phone: str | None = None
    email: str | None = None
    case_id: str | None = None


class OtpIn(BaseModel):
    otp: str


def _otp() -> str:
    return os.environ.get("MOCK_ESIGN_OTP", "123456")


def _expired(session: ESignSession) -> bool:
    if session.status != "PENDING":
        return False
    try:
        expires = datetime.strptime(session.expires_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError:
        return False
    return _now() > expires


def _fail(session: ESignSession, background: BackgroundTasks, case_id: str | None) -> None:
    """Mark the session failed and tell the API, so the track can move on."""
    session.status = "FAILED"
    background.add_task(
        service.deliver,
        "esign.failed",
        {
            "case_id": case_id,
            "session_id": session.session_id,
            "reason": "otp_failed",
            "failed_at": _stamp(_now()),
        },
        api_url(),
        "esign",
    )


@router.post("/sessions")
def create_session(payload: CreateSession) -> dict:
    session_id = signer.new_id("ESIGN")
    session = ESignSession(
        session_id=session_id,
        status="PENDING",
        signing_url=f"/mock/esign/{session_id}",
        expires_at=_stamp(_now() + timedelta(minutes=SESSION_MINUTES)),
        case_id=payload.case_id,
        doc_sha256=payload.doc_sha256,
    )
    store.esign[session_id] = session
    return session.as_dict()


@router.get("/sessions/{session_id}")
def get_session(session_id: str) -> dict:
    session = store.esign.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Unknown eSign session")
    return session.as_dict()


@router.post("/sessions/{session_id}/otp")
def submit_otp(session_id: str, payload: OtpIn, background: BackgroundTasks):
    """Submit the test OTP.

    Order matters: expiry is checked before the OTP, so an expired session cannot be
    rescued by guessing correctly. Three failures fail the session, and a failure is
    announced (`esign.failed`) rather than left for the API to discover by polling.

    Failures return a response rather than raising, because Starlette does **not** run
    background tasks when a route raises - the announcement would be silently lost.
    """
    from fastapi.responses import JSONResponse

    session = store.esign.get(session_id)
    if session is None:
        return JSONResponse(status_code=404, content={"detail": "Unknown eSign session"})

    if _expired(session):
        session.status = "EXPIRED"
        background.add_task(
            service.deliver,
            "esign.failed",
            {
                "case_id": session.case_id,
                "session_id": session.session_id,
                "reason": "expired",
                "failed_at": _stamp(_now()),
            },
            api_url(),
            "esign",
        )
        return JSONResponse(status_code=410, content={"detail": "This signing session has expired"})

    if session.status != "PENDING":
        return JSONResponse(status_code=409, content={"detail": f"Session is {session.status}"})

    session.attempts += 1
    if payload.otp != _otp():
        remaining = OTP_ATTEMPTS - session.attempts
        if remaining <= 0:
            _fail(session, background, session.case_id)
            return JSONResponse(
                status_code=403, content={"detail": "Too many attempts; the session has failed"}
            )
        return JSONResponse(
            status_code=401, content={"detail": f"Wrong OTP. {remaining} attempt(s) left."}
        )

    signed_at = _stamp(_now())
    session.status = "SIGNED"
    session.signed_at = signed_at
    session.signer_display = "Demo Signer"
    # A simulated signature: the hash of the document bytes, nothing more.
    session.signed_doc_sha256 = session.doc_sha256 or ""

    payload_out = {
        "case_id": session.case_id,
        "session_id": session.session_id,
        "signed_doc_sha256": session.signed_doc_sha256,
        "signer_display": "Demo Signer",
        "signed_at": signed_at,
    }
    background.add_task(service.deliver, "esign.completed", payload_out, api_url(), "esign")

    # A payout is due only once the esign is known; the bid acceptance usually comes
    # first or second, and the bank waits for both (section 7.3).
    if session.case_id:
        bank.note_esign(session.case_id, background)

    return session.as_dict()


@router.post("/sessions/{session_id}/complete")
def complete_session_legacy(session_id: str, payload: OtpIn, background: BackgroundTasks) -> dict:
    """Deprecated alias for `/otp`, kept so an older client keeps working."""
    return submit_otp(session_id, payload, background)
