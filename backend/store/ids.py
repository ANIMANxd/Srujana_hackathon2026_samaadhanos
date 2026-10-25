"""ULID generation (Crockford base32, 26 chars, lexicographically sortable).

Case, evaluation and track identifiers are ULIDs issued by the server *after*
approval, never by the client (architecture_v4 sections 4 and 9). Seeded demo
cases use `deterministic_ulid` so `make db-reset` is reproducible.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime

ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"  # Crockford: no I, L, O or U


def _encode(value: int, length: int) -> str:
    out = []
    for _ in range(length):
        out.append(ALPHABET[value & 31])
        value >>= 5
    return "".join(reversed(out))


def new_ulid(at: datetime | None = None) -> str:
    """A ULID for `at` (default now) with 80 bits of cryptographic randomness."""
    moment = at or datetime.now(UTC)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    timestamp_ms = int(moment.timestamp() * 1000)
    randomness = int.from_bytes(secrets.token_bytes(10), "big")
    return _encode(timestamp_ms, 10) + _encode(randomness, 16)


def deterministic_ulid(seed: str, at: datetime) -> str:
    """A reproducible ULID for demo seeds: real timestamp, seeded randomness.

    Same `seed` and `at` always give the same id, so re-seeding produces ids that
    demo links and fixtures can rely on.
    """
    if at.tzinfo is None:
        at = at.replace(tzinfo=UTC)
    timestamp_ms = int(at.timestamp() * 1000)
    randomness = int.from_bytes(hashlib.sha256(seed.encode("utf-8")).digest()[:10], "big")
    return _encode(timestamp_ms, 10) + _encode(randomness, 16)


def is_ulid(value: str) -> bool:
    return len(value) == 26 and all(char in ALPHABET for char in value.upper())
