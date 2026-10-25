"""Mock provider adapters: HTTP to the separate mock service on :8100.

These are **simulations**, permanently labelled:
`simulated = True` on every class, `X-Simulation: true` on every call, and
`MOCK`-prefixed identifiers coming back. `backend/app/deps.py` refuses to start
with any of these when `APP_ENV=production` (golden rule 16).

The mock service only picks rates and moves statuses. It never computes a rupee:
discount, fee and net come from `backend/finance/`.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from backend.adapters.mock.client import MockHttpClient
from backend.app.schemas_v4 import Bid, ESignSession, PayoutStatus
from backend.ports.esign import SignableDoc, SignerRef
from backend.ports.marketplace import (
    AcceptanceRequest,
    AcceptanceStatus,
    BidAcceptance,
    FactoringUnitIn,
    FactoringUnitRef,
)


class MockESignProvider:
    """`POST /esign/sessions`, `GET /esign/sessions/{id}` on the mock service."""

    simulated = True

    def __init__(self, client: MockHttpClient) -> None:
        self._client = client

    def create_session(
        self,
        doc: SignableDoc,
        signer: SignerRef,
        idem_key: str,
        *,
        correlation_id: str | None = None,
    ) -> ESignSession:
        payload = {
            "doc_id": doc.doc_id,
            "doc_sha256": doc.doc_sha256,
            "title": doc.title,
            "signer_display": signer.display_name,
            # Contact details are optional and never include an Aadhaar number.
            "phone": signer.phone,
            "email": signer.email,
        }
        data = self._client.request(
            "POST", "/esign/sessions", json_body=payload, correlation_id=correlation_id, idempotency_key=idem_key
        )
        return ESignSession.model_validate(data)

    def get_session(self, session_id: str, *, correlation_id: str | None = None) -> ESignSession:
        data = self._client.request(
            "GET", f"/esign/sessions/{session_id}", correlation_id=correlation_id
        )
        return ESignSession.model_validate(data)


class MockFinancingMarketplace:
    """TReDS-style endpoints on the mock service (architecture_v4 section 7.2)."""

    simulated = True

    def __init__(self, client: MockHttpClient) -> None:
        self._client = client

    def register_invoice(
        self, inv: FactoringUnitIn, idem_key: str, *, correlation_id: str | None = None
    ) -> FactoringUnitRef:
        data = self._client.request(
            "POST",
            "/marketplace/factoring-units",
            json_body={
                "invoice_no": inv.invoice_no,
                "buyer_gstin": inv.buyer_gstin,
                "amount": format(inv.amount, "f"),
                "currency": inv.currency,
                "due_date": inv.due_date.isoformat(),
            },
            correlation_id=correlation_id,
            idempotency_key=idem_key,
        )
        return FactoringUnitRef(unit_id=str(data["unit_id"]))

    def request_buyer_acceptance(
        self, ref: FactoringUnitRef, *, correlation_id: str | None = None
    ) -> AcceptanceRequest:
        data = self._client.request(
            "POST",
            f"/marketplace/factoring-units/{ref.unit_id}/acceptance-request",
            correlation_id=correlation_id,
        )
        from datetime import datetime

        return AcceptanceRequest(
            unit_id=str(data.get("unit_id", ref.unit_id)),
            requested_at=datetime.fromisoformat(data["requested_at"]),
        )

    def get_acceptance(
        self, ref: FactoringUnitRef, *, correlation_id: str | None = None
    ) -> AcceptanceStatus:
        data = self._client.request(
            "GET", f"/marketplace/factoring-units/{ref.unit_id}/acceptance", correlation_id=correlation_id
        )
        decided = data.get("decided_at")
        from datetime import datetime

        return AcceptanceStatus(
            unit_id=str(data.get("unit_id", ref.unit_id)),
            status=str(data["status"]),
            decided_at=datetime.fromisoformat(decided) if decided else None,
        )

    def open_bidding(
        self, ref: FactoringUnitRef, window: timedelta, *, correlation_id: str | None = None
    ) -> None:
        self._client.request(
            "POST",
            f"/marketplace/factoring-units/{ref.unit_id}/bidding",
            json_body={"window_seconds": int(window.total_seconds())},
            correlation_id=correlation_id,
        )

    def list_bids(self, ref: FactoringUnitRef, *, correlation_id: str | None = None) -> list[Bid]:
        data = self._client.request(
            "GET", f"/marketplace/factoring-units/{ref.unit_id}/bids", correlation_id=correlation_id
        )
        raw: Any = data.get("bids", data)
        # The mock ships `annual_rate_pct` (docs/webhooks.md); the contract model calls
        # it `annual_rate`. Map at the boundary rather than reshaping the contract.
        return [
            Bid.model_validate(
                {**item, "annual_rate": item.get("annual_rate_pct", item.get("annual_rate"))}
            )
            for item in raw
        ]

    def accept_bid(
        self, ref: FactoringUnitRef, bid_id: str, idem_key: str, *, correlation_id: str | None = None
    ) -> BidAcceptance:
        data = self._client.request(
            "POST",
            f"/marketplace/bids/{bid_id}/accept",
            json_body={"unit_id": ref.unit_id},
            correlation_id=correlation_id,
            idempotency_key=idem_key,
        )
        from datetime import datetime

        return BidAcceptance(
            unit_id=str(data.get("unit_id", ref.unit_id)),
            bid_id=str(data.get("bid_id", bid_id)),
            accepted_at=datetime.fromisoformat(data["accepted_at"]),
        )


class MockDisbursementRail:
    """`GET /payouts/{ref}` on the mock service (architecture_v4 section 7.3)."""

    simulated = True

    def __init__(self, client: MockHttpClient) -> None:
        self._client = client

    def get_payout(self, payout_ref: str, *, correlation_id: str | None = None) -> PayoutStatus:
        data = self._client.request(
            "GET", f"/payouts/{payout_ref}", correlation_id=correlation_id
        )
        return PayoutStatus.model_validate(data)
