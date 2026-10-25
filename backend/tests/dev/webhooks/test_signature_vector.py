"""The API verifies the exact signature the mock providers create.

`docs/webhooks.md` publishes one fixed vector. `mock_providers/tests/test_signer.py`
asserts that the producer signs it; this file asserts that the **consumer** verifies
it, without either side importing the other's code.
"""

from __future__ import annotations

from backend.app import security

SECRET = "vector-secret-do-not-use"
TIMESTAMP = "1793000000"
BODY = (
    b'{"event_id":"MOCK_EVT_01JAV4E7K3M9Q2R5T8V0W1XCZD","type":"esign.completed",'
    b'"created_at":"2026-10-25T09:18:12Z","data":{"session_id":"MOCK_ESIGN_01JAV4E7K3M9Q2R5T8V0W1XCZD"}}'
)
SIGNATURE = "v1=89992520a190b25823e1c050c28b441e07d2cce49b1449286d6167ef1d88cbe9"


def test_the_published_vector_is_the_one_the_mock_signs():
    assert len(BODY) == 173, "the vector body is fixed; a change must update docs/webhooks.md"
    assert security.signature_for(BODY, TIMESTAMP, SECRET) == SIGNATURE


def test_the_api_verifies_the_published_vector():
    assert security.verify_signature(BODY, TIMESTAMP, SIGNATURE, SECRET) is True


def test_the_api_rejects_a_tampered_vector():
    tampered = BODY.replace(b"esign.completed", b"esign.forged")
    assert security.verify_signature(tampered, TIMESTAMP, SIGNATURE, SECRET) is False


def test_the_api_rejects_a_replayed_timestamp():
    """Same body and signature, but the timestamp is outside the 300 s window."""
    assert security.timestamp_is_fresh(TIMESTAMP, now=float(TIMESTAMP)) is True
    assert security.timestamp_is_fresh(TIMESTAMP, now=float(TIMESTAMP) + 301) is False
