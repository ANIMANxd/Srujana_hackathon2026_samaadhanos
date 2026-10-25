"""Clocks for the workflow (architecture_v4 section 6).

`SystemClock` is the default. `OffsetClock` exists so the judge console can "jump to
day 46" and show the switch from Option 1 to Option 2 without waiting three weeks;
it is only ever installed when `MOCK_CLOCK` is enabled **and** the app is not in
production, because moving time in a production system would be a lie.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta


class SystemClock:
    """The real clock, in UTC."""

    simulated = False

    def now(self) -> datetime:
        return datetime.now(UTC)


class OffsetClock:
    """A clock that runs offset from a base clock, and can be jumped forward.

    Kept as a thin wrapper rather than a frozen timestamp so "advance 10 days" moves
    the whole workflow while the base keeps ticking normally.
    """

    simulated = True

    def __init__(self, base, offset: timedelta = timedelta(0)) -> None:
        self._base = base
        self._offset = offset

    def now(self) -> datetime:
        return self._base.now() + self._offset

    def advance(self, delta: timedelta) -> datetime:
        """Jump the simulated clock forward and return the new `now`."""
        if delta < timedelta(0):
            raise ValueError("the simulated clock can only move forward")
        self._offset += delta
        return self.now()

    @property
    def offset(self) -> timedelta:
        return self._offset
