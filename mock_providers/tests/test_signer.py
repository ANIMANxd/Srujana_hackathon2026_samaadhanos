"""The signature must match the API's, byte for byte, without sharing code.

`docs/webhooks.md` publishes one fixed vector. The mock signs it here; a backend test
verifies the same vector with `backend.app.security`. If either algorithm drifts, both
suites fail on the same numbers.
"""

from __future__ import annotations

import json

from mock_providers import signer

# The published vector (docs/webhooks.md). Kept literal on purpose: if the algorithm
# changes, these constants must change in the document too.
VECTOR_SECRET = "vector-secret-do-not-use"
VECTOR_TIMESTAMP = "1793000000"
VECTOR_BODY = b'{"event_id":"MOCK_EVT_01JAV4E7K3M9Q2R5T8V0W1XCZD","type":"esign.completed","created_at":"2026-10-25T09:18:12Z","data":{"session_id":"MOCK_ESIGN_01JAV4E7K3M9Q2R5T8V0W1XCZD"}}'
VECTOR_SIGNATURE = "v1=89992520a190b25823e1c050c28b441e07d2cce49b1449286d6167ef1d88cbe9"


def test_the_published_vector_signs_as_documented():
    assert len(VECTOR_BODY) == 173, "the vector body is fixed; a change invalidates the doc"
    assert signer.sign(VECTOR_BODY, VECTOR_TIMESTAMP, VECTOR_SECRET) == VECTOR_SIGNATURE


def test_the_vector_verifies():
    assert signer.verify(VECTOR_BODY, VECTOR_TIMESTAMP, VECTOR_SIGNATURE, VECTOR_SECRET)


def test_a_changed_body_fails_verification():
    tampered = VECTOR_BODY.replace(b"esign.completed", b"esign.forged")
    assert not signer.verify(tampered, VECTOR_TIMESTAMP, VECTOR_SIGNATURE, VECTOR_SECRET)


def test_a_changed_timestamp_fails_verification():
    assert not signer.verify(VECTOR_BODY, "1793000001", VECTOR_SIGNATURE, VECTOR_SECRET)


def test_a_wrong_secret_fails_verification():
    assert not signer.verify(VECTOR_BODY, VECTOR_TIMESTAMP, VECTOR_SIGNATURE, "wrong-secret")


def test_the_signature_covers_the_timestamp():
    """The timestamp is inside the signed message, so it cannot be moved."""
    first = signer.sign(VECTOR_BODY, "1000", VECTOR_SECRET)
    second = signer.sign(VECTOR_BODY, "2000", VECTOR_SECRET)
    assert first != second


def test_every_id_is_mock_prefixed():
    assert signer.new_id("EVT").startswith("MOCK_EVT_")
    assert signer.new_id("BID").startswith("MOCK_BID_")
    assert signer.new_id("MOCKUTR").startswith("MOCKUTR")
    assert len({signer.new_id("EVT") for _ in range(50)}) == 50


def test_ulids_are_sortable_by_time():
    early = signer.new_ulid(at=1_700_000_000)
    late = signer.new_ulid(at=1_800_000_000)
    assert early < late
    assert len(early) == 26
