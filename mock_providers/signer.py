"""Signing and identifiers for the mock provider service.

**Standard library only.** This module must not import anything from `backend/`, so
the mock can be run as a standalone process and can never accidentally share a
config object, a database handle or a legal rule with the API.

The signature algorithm is the same one `docs/webhooks.md` publishes and the API
verifies:

    X-Mock-Signature: v1=<hex hmac_sha256(secret, timestamp + "." + raw_body)>

`docs/webhooks.md` carries a fixed test vector so the two implementations can be
proved to agree without sharing code.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time

# Crockford base32: no I, L, O or U, so an id cannot be misread.
ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

MOCK_PREFIX = "MOCK"


def _encode(value: int, length: int) -> str:
    out = []
    for _ in range(length):
        out.append(ALPHABET[value & 31])
        value >>= 5
    return "".join(reversed(out))


def new_ulid(at: float | None = None) -> str:
    """A ULID: 48-bit millisecond timestamp plus 80 bits of randomness."""
    moment = time.time() if at is None else at
    timestamp_ms = int(moment * 1000)
    randomness = int.from_bytes(secrets.token_bytes(10), "big")
    return _encode(timestamp_ms, 10) + _encode(randomness, 16)


def new_id(prefix: str) -> str:
    """Every identifier this service issues carries the `MOCK` prefix.

    That is what stops a screenshot of the demo being mistaken for a real reference
    (`MOCKUTR…`, `MOCK_EVT_…`, `MOCK-BID-…`).
    """
    if prefix.upper().startswith("MOCK"):
        return f"{prefix}{new_ulid()}"
    return f"{MOCK_PREFIX}_{prefix.upper()}_{new_ulid()}"


def sign(raw_body: bytes, timestamp: str, secret: str) -> str:
    """`v1=<hex>` over `timestamp + "." + raw_body`.

    The timestamp is inside the signed payload so it cannot be moved to escape the
    API's freshness check.
    """
    message = timestamp.encode("utf-8") + b"." + raw_body
    digest = hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
    return f"v1={digest}"


def verify(raw_body: bytes, timestamp: str, signature: str, secret: str) -> bool:
    """Constant-time check. Exists so the mock's own tests can prove the algorithm."""
    expected = sign(raw_body, timestamp, secret)
    return hmac.compare_digest(expected, signature)


def secret_for(provider: str) -> str:
    """The same env var names the API reads: `WEBHOOK_SECRET_<PROVIDER>`."""
    import os

    default = f"dev-only-secret-{provider.lower()}"
    return os.environ.get(f"WEBHOOK_SECRET_{provider.upper()}", default)
