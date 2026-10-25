"""The mock's webhooks must carry the case id, or the API cannot route them.

The API's marketplace adapter does not send a case id today, so this module keeps the
case id on the unit and falls back to `MOCK_LAST_CASE_ID` for a one-case demo. Both
paths are explicit rather than a hidden environment lookup at send time.
"""

from __future__ import annotations

import os


def remember_case(unit, case_id: str | None) -> None:
    """Attach the case id to a unit when the caller supplies one."""
    if case_id:
        unit.case_id = case_id


def case_id_for(*, unit=None, explicit: str | None = None) -> str | None:
    """The most specific case id available, or None.

    Order: the caller's explicit value, then the unit's remembered value, then the
    `MOCK_LAST_CASE_ID` escape hatch used by the single-case demo.
    """
    if explicit:
        return explicit
    remembered = getattr(unit, "case_id", None) if unit is not None else None
    if remembered:
        return remembered
    return os.environ.get("MOCK_LAST_CASE_ID") or None
