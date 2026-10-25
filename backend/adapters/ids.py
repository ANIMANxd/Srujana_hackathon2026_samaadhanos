"""Sortable, server-issued identifiers.

`UlidIdGenerator` is the production default; a `SeededIdGenerator` gives tests and
fixtures a deterministic stream without touching the real one.
"""

from __future__ import annotations

import itertools

from backend.store.ids import new_ulid


class UlidIdGenerator:
    """ULIDs, prefixed for readability in logs and payloads."""

    simulated = False

    def new_id(self, prefix: str) -> str:
        return f"{prefix}-{new_ulid()}"


class SeededIdGenerator:
    """Deterministic ids for tests and the demo: `PREFIX-0001`, `PREFIX-0002`, ..."""

    simulated = True

    def __init__(self) -> None:
        self._counters: dict[str, itertools.count] = {}

    def new_id(self, prefix: str) -> str:
        counter = self._counters.setdefault(prefix, itertools.count(1))
        return f"{prefix}-{next(counter):04d}"
