"""Mock eSign: a session, an OTP, and a signed webhook.

There is **no Aadhaar field** in the request model and no code path that could store
one. The OTP is a fixed test value (`MOCK_ESIGN_OTP`, default `123456`), three
attempts are allowed, and the "signed" document is stamped SIMULATED — no real
signature exists anywhere in this service.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from mock_providers import signer
from mock_providers.delivery import service
from mock_providers.state import ESignSession, store

router = APIRouter(prefix="/esign", tags=["esign"])

OTP_ATTEMPTS = 3
SESSION_MINUTES = 10


def api_url() -> str:
    base = os.environ.get("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    return f"{base}/api/v1/webhooks/esign"


class CreateSession(BaseModel):
    """Signer details only. No Aadhaar number is accepted, asked for or stored."""

    doc_id: str
    doc_sha256: str
    title: str
    signer_display: str = "Demo Signer"
    phone: str | None = None
    email: str | None = None


class CompleteSession(BaseModel):
    otp: str


def _otp() -> str:
    return os.environ.get("MOCK_ESIGN_OTP", "123456")


@router.post("/sessions")
def create_session(payload: CreateSession) -> dict:
    session_id = signer.new_id("ESIGN")
    expires = datetime.now(UTC) + timedelta(minutes=SESSION_MINUTES)
    session = ESignSession(
        session_id=session_id,
        status="PENDING",
        signing_url=f"/mock/esign/{session_id}",
        expires_at=expires.strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    store.esign[session_id] = session
    return session.as_dict()


@router.get("/sessions/{session_id}")
def get_session(session_id: str) -> dict:
    session = store.esign.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Unknown eSign session")
    return session.as_dict()


@router.post("/sessions/{session_id}/complete")
def complete_session(
    session_id: str, payload: CompleteSession, background: BackgroundTasks
) -> dict:
    """The signing page's only job: a test OTP, then a signed webhook.

    Three attempts, then the session fails. Nothing here produces a real signature.
    """
    session = store.esign.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Unknown eSign session")
    if session.status != "PENDING":
        raise HTTPException(status_code=409, detail=f"Session is {session.status}")

    session.attempts += 1
    if session.attempts > OTP_ATTEMPTS:
        session.status = "FAILED"
        raise HTTPException(status_code=409, detail="Too many attempts; the session has failed")

    if payload.otp != _otp():
        remaining = OTP_ATTEMPTS - session.attempts
        if remaining == 0:
            session.status = "FAILED"
        raise HTTPException(
            status_code=401, detail=f"Wrong OTP. {max(0, remaining)} attempt(s) left."
        )

    signed_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    session.status = "SIGNED"
    session.signed_at = signed_at
    session.signer_display = "Demo Signer"
    session.signed_doc_sha256 = session.signed_doc_sha256 or ""

    event_payload = {
        "case_id": os.environ.get("MOCK_LAST_CASE_ID"),
        "session_id": session.session_id,
        "signed_at": signed_at,
        "signer_display": session.signer_display,
        "signed_doc_sha256": session.signed_doc_sha256,
    }
    background.add_task(
        service.deliver, "esign.completed", event_payload, api_url(), "esign"
    )
    return session.as_dict()
