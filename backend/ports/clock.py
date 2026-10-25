"""Time and identity ports (architecture_v4 section 6).

Every workflow function takes a `Clock` instead of reading the wall clock, so the
judge console can "jump to day 46" and show the switch from Option 1 to Option 2
without waiting, and so tests are deterministic.

`IdGenerator` exists for the same reason: ids are issued by the server, never by a
client, and a fake generator makes fixtures stable.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol, runtime_checkable


@runtime_checkable
class Clock(Protocol):
    """A source of "now", always timezone-aware."""

    simulated: bool

    def now(self) -> datetime: ...


@runtime_checkable
class IdGenerator(Protocol):
    """Server-issued identifiers."""

    def new_id(self, prefix: str) -> str: ...


class SystemClock:
    """The real clock, in UTC. The production default."""

    simulated = False

    def now(self) -> datetime:
        return datetime.now(UTC)


__all__ = ["Clock", "IdGenerator", "SystemClock"]
