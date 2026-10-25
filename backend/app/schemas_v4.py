"""Contract v1.1 — additive Pydantic models for the v4 two-option model.

Source: `docs/architecture_v4_two_options.md` sections 4, 5 and 9.

Rules this module follows:
- **Additive only.** Nothing here changes a v1.0 model. `CONTRACT_VERSION` stays
  "1.0" because it is echoed in v1.0 response bodies (`/config`,
  `simulate-settlement`, `generate-artifact`, `extract-evidence`); v1.1 is a
  separate constant and no v1 route returns it.
- Money and rates are `DecStr` (Decimal in Python, string in JSON), exactly as
  in `schemas.py`. Never float.
- `OptionsResponse.recommendation` is typed `None`. It exists so that nobody
  "helpfully" adds a recommendation later (architecture_v4 section 9).
- The two state machines live in one `TrackState` enum because `tracks.state` is
  a single column (architecture_v4 section 4). The transition tables and the
  track-locking rules are in `docs/state-machines.md`.
"""

from datetime import date, datetime
from enum import Enum
from typing import Any

from pydantic import Field

from backend.app.schemas import CaseEvaluationResponse, ContractModel, DecStr

# The v4 contract number. Deliberately NOT the app-wide CONTRACT_VERSION: v1.0
# responses must stay byte-identical, so they keep reporting "1.0".
CONTRACT_VERSION_V1_1 = "1.1"


# ----------------------------------------------------------------- enums ----


class TrackKind(str, Enum):
    FINANCING = "FINANCING"
    RECOVERY = "RECOVERY"


class TrackState(str, Enum):
    """Every state of both machines (architecture_v4 section 5).

    Financing (Option 1): NEW, FINANCEABLE, NOT_FINANCEABLE,
    AWAITING_BUYER_ACCEPTANCE, BIDDING_OPEN, BIDS_AVAILABLE, NO_BIDS,
    AWAITING_ESIGN, AWAITING_DISBURSEMENT, DISBURSED, DISBURSEMENT_FAILED,
    SETTLED, SETTLED_WITHOUT_RECOURSE, BUYER_DECLINED, CANCELLED.

    Recovery (Option 2): NEW, STAGE_1_PREPARED, STAGE_1_SENT_BY_OWNER,
    STAGE_2_PREPARED, STAGE_2_SENT_BY_OWNER, STAGE_3_PREPARED,
    STAGE_3_SENT_BY_OWNER, STAGE_4_PACK_READY, ODR_FILED_BY_OWNER, PAID,
    SETTLED, CLOSED.
    """

    # shared
    NEW = "NEW"
    # financing
    FINANCEABLE = "FINANCEABLE"
    NOT_FINANCEABLE = "NOT_FINANCEABLE"
    AWAITING_BUYER_ACCEPTANCE = "AWAITING_BUYER_ACCEPTANCE"
    BIDDING_OPEN = "BIDDING_OPEN"
    BIDS_AVAILABLE = "BIDS_AVAILABLE"
    NO_BIDS = "NO_BIDS"
    AWAITING_ESIGN = "AWAITING_ESIGN"
    AWAITING_DISBURSEMENT = "AWAITING_DISBURSEMENT"
    DISBURSED = "DISBURSED"
    DISBURSEMENT_FAILED = "DISBURSEMENT_FAILED"
    SETTLED_WITHOUT_RECOURSE = "SETTLED_WITHOUT_RECOURSE"
    BUYER_DECLINED = "BUYER_DECLINED"
    CANCELLED = "CANCELLED"
    # recovery
    STAGE_1_PREPARED = "STAGE_1_PREPARED"
    STAGE_1_SENT_BY_OWNER = "STAGE_1_SENT_BY_OWNER"
    STAGE_2_PREPARED = "STAGE_2_PREPARED"
    STAGE_2_SENT_BY_OWNER = "STAGE_2_SENT_BY_OWNER"
    STAGE_3_PREPARED = "STAGE_3_PREPARED"
    STAGE_3_SENT_BY_OWNER = "STAGE_3_SENT_BY_OWNER"
    STAGE_4_PACK_READY = "STAGE_4_PACK_READY"
    ODR_FILED_BY_OWNER = "ODR_FILED_BY_OWNER"
    # terminal for both
    SETTLED = "SETTLED"
    PAID = "PAID"
    CLOSED = "CLOSED"


class BuyerAcceptanceStatus(str, Enum):
    NOT_REQUESTED = "NOT_REQUESTED"
    AWAITING = "AWAITING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class BidStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    SELECTED = "SELECTED"
    EXPIRED = "EXPIRED"
    WITHDRAWN = "WITHDRAWN"


class ESignStatus(str, Enum):
    PENDING = "PENDING"
    SIGNED = "SIGNED"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"


class PayoutState(str, Enum):
    PENDING = "PENDING"
    PROCESSED = "PROCESSED"
    FAILED = "FAILED"


class WebhookOutcome(str, Enum):
    APPLIED = "APPLIED"
    DUPLICATE = "DUPLICATE"
    PARKED = "PARKED"
    REJECTED = "REJECTED"


class EventActor(str, Enum):
    USER = "USER"
    SYSTEM = "SYSTEM"
    PROVIDER_MOCK = "PROVIDER_MOCK"


# ------------------------------------------------------------ supporting ----


class OptionCitation(ContractModel):
    """A citation on the options card (architecture_v4 section 9).

    Distinct from v1's `Citation`, which carries an engine rule id, statute ref
    and verified flag. This one is the short `{source, ref}` pair the options
    payload shows. Kept separate so v1's `Citation` stays byte-identical.
    """

    source: str
    ref: str


class RateBand(ContractModel):
    low: DecStr
    high: DecStr
    label: str = Field(description='Always "illustrative" until real market data exists.')


class NetReceivableRange(ContractModel):
    low: DecStr
    high: DecStr


class IndicativeFinancing(ContractModel):
    """The indicative numbers on the Option 1 column.

    Until `backend/finance/` exists these are placeholders and every fixture
    carries `_fixture.placeholder: true` (golden rule 7).
    """

    accepted_amount: DecStr
    tenor_days: int
    rate_band_pct: RateBand
    platform_fee_pct: DecStr
    net_receivable_range: NetReceivableRange
    settlement: str


class GetPaidEarlyOption(ContractModel):
    available: bool
    unavailable_reasons: list[str] = Field(default_factory=list)
    indicative: IndicativeFinancing | None = None
    notes: list[str] = Field(default_factory=list)
    citations: list[OptionCitation] = Field(default_factory=list)


class RecoverWithLawOption(ContractModel):
    available: bool
    expected_payment_date: date | None = None
    principal: DecStr | None = None
    interest_to_expected_date: DecStr | None = None
    total_if_paid: DecStr | None = None
    current_stage: str | None = None
    notes: list[str] = Field(default_factory=list)
    citations: list[OptionCitation] = Field(default_factory=list)


class ErrorEnvelopeDetail(ContractModel):
    """v1.1 error detail (architecture_v4 section 8).

    v1.0 keeps `ErrorResponse` (`code`, `message`, `field`) untouched; v1.1 adds
    `details` for structured validation output. Two shapes coexist on purpose and
    should be reconciled before any v1.1 route ships.
    """

    code: str
    message: str
    details: dict[str, Any] | None = None


# ----------------------------------------------------------- v1.1 models ----


class Case(ContractModel):
    """A stored case (architecture_v4 section 4, `cases` table)."""

    id: str = Field(description="ULID issued by the server, never by the client.")
    supplier_ref: str
    buyer_gstin: str | None = None
    invoice_no: str
    invoice_date: date
    accepted_amount: DecStr
    delivery_date: date | None = None
    input_json: dict[str, Any] = Field(
        description="The CaseEvaluationRequest stored verbatim, so results are reproducible."
    )
    engine_version: str
    config_version: str
    created_at: datetime


class Track(ContractModel):
    """One active track per case (architecture_v4 section 4, `tracks` table)."""

    id: str
    case_id: str
    kind: TrackKind
    state: TrackState
    version: int = Field(description="Optimistic lock; clients send If-Match: <version>.")
    created_at: datetime
    closed_at: datetime | None = None


class CaseDetail(ContractModel):
    """`GET /api/v1/cases/{id}` (architecture_v4 section 9)."""

    case: Case
    latest_evaluation: CaseEvaluationResponse | None = None
    active_track: Track | None = None
    available_actions: list[str] = Field(
        default_factory=list,
        description="Action codes the workflow allows from the current state.",
    )


class OptionsResponse(ContractModel):
    """`GET /api/v1/cases/{id}/options` — the two-option comparison.

    `recommendation` is always null and must stay that way (golden rule 20,
    architecture_v4 section 9). A test asserts it.
    """

    case_id: str
    as_of: date
    simulation: bool
    get_paid_early: GetPaidEarlyOption
    recover_with_law: RecoverWithLawOption
    recommendation: None = None


class FinancingRequest(ContractModel):
    """`financing_requests` row (architecture_v4 section 4)."""

    track_id: str
    accepted_amount: DecStr
    tenor_days: int
    due_date: date
    buyer_acceptance_status: BuyerAcceptanceStatus = BuyerAcceptanceStatus.NOT_REQUESTED
    selected_bid_id: str | None = None
    esign_session_id: str | None = None
    disbursement_ref: str | None = None


class Bid(ContractModel):
    """`bids` row. Financier aliases are fictional only (golden rule 17).

    Discount, fee and net_amount are computed by `backend/finance/`, never by the
    mock provider, so a mock cannot introduce maths bugs.
    """

    id: str
    track_id: str
    financier_alias: str
    annual_rate: DecStr
    discount: DecStr
    fee: DecStr
    net_amount: DecStr
    valid_until: datetime
    status: BidStatus = BidStatus.AVAILABLE


class ESignSession(ContractModel):
    """Mock eSign session (architecture_v4 section 7.1).

    There is no Aadhaar field and there never will be (golden rule 18).
    """

    session_id: str
    status: ESignStatus = ESignStatus.PENDING
    signing_url: str
    expires_at: datetime
    signed_doc_sha256: str | None = None
    signer_display: str | None = None
    signed_at: datetime | None = None


class PayoutStatus(ContractModel):
    """Disbursement status (architecture_v4 section 7.3). `utr` is MOCK-prefixed."""

    payout_ref: str
    status: PayoutState = PayoutState.PENDING
    amount: DecStr
    currency: str = "INR"
    utr: str | None = None
    settled_at: datetime | None = None


class Event(ContractModel):
    """Append-only, hash-chained audit event (architecture_v4 section 4).

    `hash = sha256(prev_hash || canonical_json(type, payload, actor, created_at))`.
    Tamper-evident, not tamper-proof.
    """

    seq: int
    case_id: str
    track_id: str | None = None
    type: str
    payload_json: dict[str, Any] = Field(default_factory=dict)
    actor: EventActor
    created_at: datetime
    prev_hash: str
    hash: str


class ChainVerifyResult(ContractModel):
    """`GET /api/v1/cases/{id}/events/verify`."""

    valid: bool
    checked: int
    first_bad_seq: int | None = None


class WebhookDelivery(ContractModel):
    """`webhook_inbox` row (architecture_v4 section 8, `docs/webhooks.md`)."""

    provider_event_id: str
    provider: str
    received_at: datetime
    signature_ok: bool
    processed_at: datetime | None = None
    outcome: WebhookOutcome


class ErrorEnvelope(ContractModel):
    """v1.1 error envelope: `{"error": {"code", "message", "details"}}`."""

    error: ErrorEnvelopeDetail


# --------------------------------------------------- openapi integration ----

V1_1_MODELS: tuple[type[ContractModel], ...] = (
    Case,
    CaseDetail,
    Track,
    OptionsResponse,
    FinancingRequest,
    Bid,
    ESignSession,
    PayoutStatus,
    Event,
    ChainVerifyResult,
    WebhookDelivery,
    ErrorEnvelope,
)


def component_schemas() -> tuple[dict[str, dict[str, Any]], frozenset[str]]:
    """Every v1.1 model as `{component name: JSON schema}`, plus the authored names.

    Pydantic puts nested models under `$defs`; they are hoisted into the
    components map here so the emitted document has no dangling `#/$defs/` refs.

    Two kinds of name come back:
    - **authored** (`V1_1_MODELS`): must not exist in v1.0 at all. A clash is a
      real error, because it would silently redefine a frozen schema.
    - **transitive**: v1.0 models pulled in by reference (`CaseDetail` embeds
      `CaseEvaluationResponse`). These are expected to already exist and the v1.0
      definition must win untouched.

    No v1.1 endpoint is declared yet, so these components are unreferenced by
    `paths` on purpose: the contract ships the shapes first (architecture_v4
    section 9), the routes follow.
    """
    out: dict[str, dict[str, Any]] = {}
    for model in V1_1_MODELS:
        schema = model.model_json_schema(ref_template="#/components/schemas/{model}")
        for name, sub in schema.pop("$defs", {}).items():
            out.setdefault(name, sub)
        out.setdefault(model.__name__, schema)
    authored = frozenset(m.__name__ for m in V1_1_MODELS)
    return out, authored
