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
    COURT_READY = "COURT_READY"
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


# ----------------------------------------------------------- error model ----


class ErrorDetail(ContractModel):
    code: str
    message: str
    field: str | None = None


class ErrorResponse(ContractModel):
    error: ErrorDetail
