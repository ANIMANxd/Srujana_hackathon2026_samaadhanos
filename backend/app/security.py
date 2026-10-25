"""Webhook security primitives (architecture_v4 section 8, `docs/webhooks.md`).

The order here is the security property:

    raw bytes -> verify -> constant-time compare -> timestamp window -> parse

Parsing before verifying is a listed trap in `AGENTS.md` section 7: a parser is
attacker-reachable code, and a signature computed over a re-serialised body is not
the signature the provider sent.

These functions are deliberately pure: they take bytes and strings and return
booleans. Nothing here logs a secret or a signature.
"""

from __future__ import annotations

import hashlib
import hmac
import time

SIGNATURE_HEADER = "X-Mock-Signature"
TIMESTAMP_HEADER = "X-Mock-Timestamp"
EVENT_ID_HEADER = "X-Mock-Event-Id"

# 300 s tolerance (section 8). A wider window makes replay cheaper; a narrower one
# breaks on ordinary clock drift.
TIMESTAMP_TOLERANCE_SECONDS = 300


def signature_for(raw_body: bytes, timestamp: str, secret: str) -> str:
    """`v1=<hex>` — HMAC-SHA256 over `timestamp + "." + raw_body`.

    The timestamp is inside the signed payload, so an attacker cannot move it to
    escape the freshness check.
    """
    message = timestamp.encode("utf-8") + b"." + raw_body
    digest = hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
    return f"v1={digest}"


def verify_signature(raw_body: bytes, timestamp: str | None, header: str | None, secret: str) -> bool:
    """Constant-time check of the signature header. Never raises on bad input."""
    if not timestamp or not header or not secret:
        return False
    expected = signature_for(raw_body, timestamp, secret)
    return hmac.compare_digest(expected, header)


def timestamp_is_fresh(timestamp: str | None, *, now: float | None = None, tolerance: int = TIMESTAMP_TOLERANCE_SECONDS) -> bool:
    """Whether the timestamp is within `tolerance` seconds of now (either direction).

    Both directions matter: a far-future timestamp would otherwise extend a
    signature's usefulness indefinitely.
    """
    if not timestamp:
        return False
    try:
        sent = int(timestamp)
    except ValueError:
        return False
    current = time.time() if now is None else now
    return abs(current - sent) <= tolerance


def secret_for(provider: str) -> str:
    """`WEBHOOK_SECRET_<PROVIDER>`, upper-cased. Empty when not configured."""
    import os

    return os.environ.get(f"WEBHOOK_SECRET_{provider.upper()}", "")
