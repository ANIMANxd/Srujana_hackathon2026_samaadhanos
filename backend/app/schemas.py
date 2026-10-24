"""Contract v1.0 — Pydantic v2 models for architecture.md section 8.

Frozen: after the contract-v1 tag the contract is additive-only (section 9).
No field exists here that is not in the document. Money, rates and
percentages are Decimal serialized as strings; dates are ISO YYYY-MM-DD.
"""

from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer, WithJsonSchema

# The kind list lives with the templates so the route and the templates read one
# source; schemas re-exports it as part of the contract (section 8.1).
from backend.artifacts.kinds import ArtifactKind

# Same idea for extraction: source kinds, message tags and methods are defined
# beside the pipeline and re-exported here for the contract.
from backend.extraction.tags import ExtractionMethod, MessageTag, SourceKind

CONTRACT_VERSION = "1.0"

# Decimal in Python, string in JSON and in the OpenAPI schema.
DecStr = Annotated[
    Decimal,
    PlainSerializer(
        lambda v: format(v, "f") if v is not None else None,
        return_type=str,
        when_used="json",
    ),
    WithJsonSchema({"type": "string"}),
]


class ContractModel(BaseModel):
    """Base: allow `from_` mapped to the JSON key "from"."""

    model_config = ConfigDict(populate_by_name=True)


# ---------------------------------------------------------------- enums ----


class EnterpriseClass(str, Enum):
    MICRO = "MICRO"
    SMALL = "SMALL"
    MEDIUM = "MEDIUM"
    UNKNOWN = "UNKNOWN"


class Activity(str, Enum):
    MANUFACTURING = "MANUFACTURING"
    SERVICES = "SERVICES"
    TRADING = "TRADING"


class SilpiTestDate(str, Enum):
    CONTRACT = "CONTRACT"
    SUPPLY = "SUPPLY"


class RateMode(str, Enum):
    FLOATING = "FLOATING"
    FROZEN_AT_APPOINTED_DAY = "FROZEN_AT_APPOINTED_DAY"


class AppropriationMode(str, Enum):
    INTEREST_FIRST = "INTEREST_FIRST"
    PRINCIPAL_FIRST = "PRINCIPAL_FIRST"


class PaymentBoundaryConvention(str, Enum):
    PAYMENT_DATE_IS_REST_BOUNDARY = "PAYMENT_DATE_IS_REST_BOUNDARY"


class JurisdictionStatus(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    BARRED_SILPI = "BARRED_SILPI"
    EXCLUDED_TRADER = "EXCLUDED_TRADER"
    EXCLUDED_MEDIUM = "EXCLUDED_MEDIUM"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class ObjectionStatus(str, Enum):
    DEEMED_ACCEPTANCE = "DEEMED_ACCEPTANCE"
    PENDING_RESOLUTION = "PENDING_RESOLUTION"
    RESOLVED = "RESOLVED"
    NO_DELIVERY_PROOF = "NO_DELIVERY_PROOF"


class LedgerKind(str, Enum):
    REST = "REST"
    PAYMENT = "PAYMENT"
    STUB = "STUB"


class LimitationStatus(str, Enum):
    OK = "OK"
    WARN_12M = "WARN_12M"
    WARN_6M = "WARN_6M"
    EXPIRED = "EXPIRED"
    UNKNOWN = "UNKNOWN"


class AcknowledgmentKind(str, Enum):
    SIGNED_BALANCE_CONFIRMATION = "SIGNED_BALANCE_CONFIRMATION"
    PART_PAYMENT = "PART_PAYMENT"
    WHATSAPP_PROMISE = "WHATSAPP_PROMISE"


class EvidenceKind(str, Enum):
    PO = "PO"
    INVOICE = "INVOICE"
    DELIVERY_PROOF = "DELIVERY_PROOF"
    WHATSAPP = "WHATSAPP"
    UDYAM = "UDYAM"
    GST_RETURN = "GST_RETURN"


class DefenseStatus(str, Enum):
    STRONG = "STRONG"
    AT_RISK = "AT_RISK"
    OPEN_QUESTION = "OPEN_QUESTION"


class ReadinessBand(str, Enum):
    # COURT_READY is the name the frozen contract v1.0 shipped with. The spec
    # renamed it EVIDENCE_COMPLETE (CR-3): "court-ready" is a legal-conclusion
    # claim. The new member is added additively so the engine's output validates;
    # retiring the old one is a rename and needs both humans (architecture 9.3).
    COURT_READY = "COURT_READY"
    EVIDENCE_COMPLETE = "EVIDENCE_COMPLETE"
    ACTION_NEEDED = "ACTION_NEEDED"
    BLOCKED = "BLOCKED"


class WarningSeverity(str, Enum):
    INFO = "INFO"
    WARN = "WARN"
    BLOCK = "BLOCK"


# ---------------------------------------------------------- 8.2 request ----


class Supplier(ContractModel):
    name: str
    udyam_number: str | None = None
    enterprise_class: EnterpriseClass
    activity: Activity
    nic_codes: list[str]
    udyam_registration_date: date | None = None
    investment_cr: DecStr | None = None
    turnover_cr: DecStr | None = None


class Buyer(ContractModel):
    name: str
    gstin: str | None = None
    tax_rate_pct: DecStr
    cost_of_capital_pct: DecStr


class Transaction(ContractModel):
    contract_date: date | None = None
    supply_date: date | None = None
    invoice_date: date
    delivery_date: date | None = None
    principal: DecStr
    written_credit_days: int | None = None
    calculation_date: date
    years_deferred: DecStr | None = None


class Objection(ContractModel):
    raised_date: date
    is_written: bool
    description: str | None = None
    resolved_date: date | None = None


class PartPayment(ContractModel):
    date: date
    amount: DecStr
    reference: str | None = None


class Acknowledgment(ContractModel):
    date: date
    kind: AcknowledgmentKind
    is_signed: bool
    source_ref: str | None = None


class EvidenceItem(ContractModel):
    kind: EvidenceKind
    present: bool
    ref: str | None = None


class Evidence(ContractModel):
    items: list[EvidenceItem]


class ConfigOverrides(ContractModel):
    bank_rate_pct: DecStr | None = None
    objection_window_days: int | None = None
    rate_mode: RateMode | None = None
    appropriation_mode: AppropriationMode | None = None
    silpi_test_date: SilpiTestDate | None = None


class CaseEvaluationRequest(ContractModel):
    contract_version: str = CONTRACT_VERSION
    case_id: str
    supplier: Supplier
    buyer: Buyer
    transaction: Transaction
    objections: list[Objection] = Field(default_factory=list)
    part_payments: list[PartPayment] = Field(default_factory=list)
    acknowledgments: list[Acknowledgment] = Field(default_factory=list)
    evidence: Evidence
    config_overrides: ConfigOverrides | None = None


# --------------------------------------------------------- 8.3 response ----


class JurisdictionCheck(ContractModel):
    id: str
    passed: bool | None
    detail: str
    rule_ref: str


class Jurisdiction(ContractModel):
    status: JurisdictionStatus
    eligible: bool
    checks: list[JurisdictionCheck]
    alternative_remedy: str | None = None


class LateComplaint(ContractModel):
    date: date
    description: str | None = None
    reason: str


class Timeline(ContractModel):
    delivery_date: date | None
    objection_window_end: date | None
    objection_status: ObjectionStatus
    acceptance_date: date | None
    agreed_days: int | None
    applied_days: int | None
    clamped: bool
    due_date: date | None
    appointed_day: date | None
    days_overdue: int | None
    late_complaints: list[LateComplaint]


class RateSegment(ContractModel):
    from_: date = Field(alias="from")
    to: date
    bank_rate_pct: DecStr
    statutory_rate_pct: DecStr


class LedgerRow(ContractModel):
    kind: LedgerKind
    from_: date = Field(alias="from")
    to: date
    opening: DecStr
    interest: DecStr
    payment: DecStr
    closing: DecStr
    rate_pct: DecStr
    note: str | None = None


class Financials(ContractModel):
    rate_mode: RateMode
    appropriation_mode: AppropriationMode
    payment_boundary_convention: PaymentBoundaryConvention
    rate_segments: list[RateSegment]
    ledger: list[LedgerRow]
    interest_total: DecStr
    principal_outstanding: DecStr
    interest_outstanding: DecStr
    total_claim: DecStr
    daily_accrual: DecStr


class PermanentLoss(ContractModel):
    interest_non_deductible: DecStr
    pretax_equivalent_rate_pct: DecStr


class DeferralCheckpoint(ContractModel):
    fy_end: date
    unpaid_principal: DecStr
    tax_timing_effect: DecStr


class DeferralInputs(ContractModel):
    cost_of_capital_pct: DecStr
    years_deferred: DecStr


class Deferral(ContractModel):
    applies: bool
    checkpoints: list[DeferralCheckpoint]
    deferral_cost: DecStr | None
    inputs: DeferralInputs


class DisclosureFlag(ContractModel):
    id: str
    text: str
    verified: bool


class OtherPressurePoint(ContractModel):
    id: str
    text: str


class BuyerCost(ContractModel):
    permanent_loss: PermanentLoss
    deferral: Deferral
    disclosure_flags: list[DisclosureFlag]
    other_pressure_points: list[OtherPressurePoint]


class LimitationEvent(ContractModel):
    date: date
    kind: AcknowledgmentKind
    restarts_clock: bool


class Limitation(ContractModel):
    expiry: date | None
    status: LimitationStatus
    events: list[LimitationEvent]


class Defense(ContractModel):
    id: str
    buyer_says: str
    rule_ref: str
    status: DefenseStatus
    evidence_have: list[str]
    evidence_missing: list[str]


class ReadinessReason(ContractModel):
    code: str
    delta: int
    text: str


class EvidenceReadiness(ContractModel):
    score: int
    band: ReadinessBand
    reasons: list[ReadinessReason]
    missing: list[str]
    blocked_stages: list[int]
    recommended_stage: int


class Citation(ContractModel):
    id: str
    rule: str
    statute_ref: str
    config_key: str | None = None
    verified: bool


class Warning(ContractModel):
    code: str
    severity: WarningSeverity
    text: str


class CaseEvaluationResponse(ContractModel):
    contract_version: str = CONTRACT_VERSION
    case_id: str
    calculation_date: date
    jurisdiction: Jurisdiction
    timeline: Timeline | None
    financials: Financials | None
    buyer_cost: BuyerCost | None
    limitation: Limitation
    defenses: list[Defense]
    evidence_readiness: EvidenceReadiness
    citations: list[Citation]
    assumptions: list[str]
    warnings: list[Warning]


# --------------------------------------------- 8.1 simulate-settlement ----
# Section 8.1 lists the endpoint but 8.3 defined no schema for it (CQ-18), so
# these are the additive models the API layer needs. No shipped field changed.


class SettlementPaymentKind(str, Enum):
    UPFRONT = "UPFRONT"
    SECOND = "SECOND"


class SettlementPayment(ContractModel):
    kind: SettlementPaymentKind
    days_from_now: int
    amount: DecStr


class SettlementSimulationRequest(ContractModel):
    """What the negotiator is proposing, plus the case to price it against."""

    request: CaseEvaluationRequest
    upfront_pct: DecStr
    waiver_pct: DecStr
    days_to_second_payment: int


class SettlementSimulationResponse(ContractModel):
    contract_version: str = CONTRACT_VERSION
    total_claim: DecStr
    interest_waived: DecStr
    interest_paid: DecStr
    principal_paid: DecStr
    total_payable: DecStr
    payments: list[SettlementPayment]
    net_recovery: DecStr
    upfront_pct: DecStr
    waiver_pct: DecStr
    days_to_second_payment: int
    assumptions: list[str]


# --------------------------------------------- 8.1 generate-artifact ----
# Section 8.1 gives this endpoint's shapes as one-liners (`{kind, request}` in,
# `{filename, markdown, pdf_base64?}` out). These are the additive models behind
# them: no shipped field changed, so the contract stays 1.0 (CQ-35's reading of
# section 9). `settlement` is optional and only Stage 3 reads it; when it is
# absent, the draft states the neutral starting terms it was made with.


class SettlementTerms(ContractModel):
    """The offer a Stage 3 term sheet prices: what the negotiator is proposing."""

    upfront_pct: DecStr
    waiver_pct: DecStr
    days_to_second_payment: int


class ArtifactGenerationRequest(ContractModel):
    kind: ArtifactKind
    request: CaseEvaluationRequest
    settlement: SettlementTerms | None = None


class ArtifactResponse(ContractModel):
    contract_version: str = CONTRACT_VERSION
    kind: ArtifactKind
    filename: str
    markdown: str
    # Present only when the PDF rendered; markdown is always present, so a PDF
    # failure degrades to text plus a `warnings[]` entry rather than an error.
    pdf_base64: str | None = None
    pdf_filename: str | None = None
    warnings: list[Warning] = Field(default_factory=list)


# --------------------------------------------- 8.1 extract-evidence ----
# Section 8.1 lists the path but defines no body (CR-4 is still open). The
# shape below mirrors what the frontend already expects - `{value, source_text,
# page, method, confidence}` per key, plus the top-level `supplier_name` - and
# adds what task B9 requires: line citations, the chat-message candidates, the
# confirm schema, and a machine-suggested flag on every candidate.
#
# Two deliberate notes: `method` stays lowercase (`regex`/`llm`/`missing`)
# because CR-4 and the shipped sample JSON use those strings; and `page` is
# always null here, because this pipeline reads text - `line` is the citation.


class ConfirmKind(str, Enum):
    FIELD = "FIELD"
    MESSAGE = "MESSAGE"


class ConfirmFieldType(str, Enum):
    DATE = "DATE"
    MONEY = "MONEY"
    INT = "INT"
    STRING = "STRING"
    ROW = "ROW"


class ExtractedField(ContractModel):
    """One machine-suggested candidate value with its line citation."""

    value: str | None
    source_text: str | None
    page: int | None = None
    line: int | None = None
    method: ExtractionMethod
    confidence: float = Field(ge=0.0, le=1.0)
    machine_suggested: bool = True


class ExtractedMessage(ContractModel):
    """One parsed chat message: where it is, what it says, what it reads like."""

    line: int
    sender: str
    sent: date | None
    text: str
    tags: list[MessageTag]
    days_after_delivery: int | None = None
    within_objection_window: bool | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    machine_suggested: bool = True


class ConfirmEntry(ContractModel):
    """Where one candidate would go in a CaseEvaluationRequest, and what to check."""

    key: str
    path: str | None
    kind: ConfirmKind
    type: ConfirmFieldType
    required: bool
    note: str


class ExtractionResponse(ContractModel):
    contract_version: str = CONTRACT_VERSION
    kind: SourceKind
    fields: dict[str, ExtractedField]
    supplier_name: str | None = None
    messages: list[ExtractedMessage] = Field(default_factory=list)
    confirm_schema: list[ConfirmEntry] = Field(default_factory=list)
    cache_hit: bool = False
    warnings: list[Warning] = Field(default_factory=list)


# ----------------------------------------------------------- error model ----


class ErrorDetail(ContractModel):
    code: str
    message: str
    field: str | None = None


class ErrorResponse(ContractModel):
    error: ErrorDetail
