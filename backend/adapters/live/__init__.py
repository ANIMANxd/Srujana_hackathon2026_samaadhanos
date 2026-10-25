"""Live provider adapters: stubs that refuse to pretend.

Nothing here is integrated. Every method raises
`NotImplementedError("live provider not integrated")`, which is the honest state and
the one the pitch must describe: *"would integrate with"*, never *"integrated with"*.

`simulated = False` matters: it is what lets `backend/app/deps.py` start in
production while the mock adapters are refused.
"""

from __future__ import annotations

from datetime import timedelta

from backend.ports.esign import SignableDoc, SignerRef
from backend.ports.marketplace import (
    AcceptanceRequest,
    AcceptanceStatus,
    BidAcceptance,
    FactoringUnitIn,
    FactoringUnitRef,
)

NOT_INTEGRATED = "live provider not integrated"


class LiveESignProvider:
    """A licensed eSign service provider. Not integrated."""

    simulated = False

    def create_session(
        self, doc: SignableDoc, signer: SignerRef, idem_key: str, **_: object
    ) -> object:
        raise NotImplementedError(NOT_INTEGRATED)

    def get_session(self, session_id: str, **_: object) -> object:
        raise NotImplementedError(NOT_INTEGRATED)


class LiveFinancingMarketplace:
    """An RBI-authorised TReDS platform. Not integrated."""

    simulated = False

    def register_invoice(self, inv: FactoringUnitIn, idem_key: str, **_: object) -> object:
        raise NotImplementedError(NOT_INTEGRATED)

    def request_buyer_acceptance(self, ref: FactoringUnitRef, **_: object) -> AcceptanceRequest:
        raise NotImplementedError(NOT_INTEGRATED)

    def get_acceptance(self, ref: FactoringUnitRef, **_: object) -> AcceptanceStatus:
        raise NotImplementedError(NOT_INTEGRATED)

    def open_bidding(self, ref: FactoringUnitRef, window: timedelta, **_: object) -> None:
        raise NotImplementedError(NOT_INTEGRATED)

    def list_bids(self, ref: FactoringUnitRef, **_: object) -> object:
        raise NotImplementedError(NOT_INTEGRATED)

    def accept_bid(self, ref: FactoringUnitRef, bid_id: str, idem_key: str, **_: object) -> BidAcceptance:
        raise NotImplementedError(NOT_INTEGRATED)


class LiveDisbursementRail:
    """The financier's bank / the platform's settlement files. Not integrated."""

    simulated = False

    def get_payout(self, payout_ref: str, **_: object) -> object:
        raise NotImplementedError(NOT_INTEGRATED)
