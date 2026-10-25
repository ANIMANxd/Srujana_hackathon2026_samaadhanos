"""Provider interfaces (architecture_v4 section 6).

`Protocol` classes only — no implementation, no I/O. The mock and live adapters in
`backend/adapters/` implement these, and `backend/app/deps.py` chooses one from
`PROVIDER_MODE`.

Return types reuse the contract models in `backend/app/schemas_v4.py`
(`ESignSession`, `Bid`, `PayoutStatus`) so an adapter cannot drift from a shape the
API promises.
"""

from backend.ports.clock import Clock, IdGenerator, SystemClock
from backend.ports.disbursement import DisbursementRail
from backend.ports.errors import ProviderError, ProviderUnavailable
from backend.ports.esign import ESignProvider, SignableDoc, SignerRef
from backend.ports.marketplace import (
    AcceptanceRequest,
    AcceptanceStatus,
    BidAcceptance,
    FactoringUnitIn,
    FactoringUnitRef,
    FinancingMarketplace,
)

__all__ = [
    "AcceptanceRequest",
    "AcceptanceStatus",
    "BidAcceptance",
    "Clock",
    "DisbursementRail",
    "ESignProvider",
    "FactoringUnitIn",
    "FactoringUnitRef",
    "FinancingMarketplace",
    "IdGenerator",
    "ProviderError",
    "ProviderUnavailable",
    "SignableDoc",
    "SignerRef",
    "SystemClock",
]
