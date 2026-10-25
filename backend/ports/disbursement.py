"""Disbursement rail port (architecture_v4 section 6).

Payout status arrives as a **signed webhook** to `POST /api/v1/webhooks/disbursement`.
`get_payout` is for reconciliation and the UI, not for waiting on money.

`PayoutStatus.utr` is `MOCK`-prefixed in mock mode, so a simulated reference can
never be mistaken for a real bank one (golden rule 16).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from backend.app.schemas_v4 import PayoutStatus


@runtime_checkable
class DisbursementRail(Protocol):
    """A payout rail (the financier's bank, via the platform), or a simulation."""

    simulated: bool

    def get_payout(self, payout_ref: str) -> PayoutStatus:
        """Read the current status of a payout."""
        ...
