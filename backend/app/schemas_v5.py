"""Contract v1.2 — additive Pydantic models for the v5 Customer book.

Source: the v5 customer-book work (CB3-CB5) and `AGENTS.md` rules 22-27.

Rules this module follows:
- **Additive only.** Nothing here changes a v1.0 or v1.1 model.
  `CONTRACT_VERSION` stays "1.0" because it is echoed in v1.0 response bodies;
  v1.2 has its own constant and no v1 route returns it.
- **Components before routes.** CB2-CB6 do not exist yet, so these models are
  published as unreferenced components, exactly as v1.1 shipped its shapes.
  The v1.2 test suite asserts no path moved.
- Money, percentages and similarity ratios are `DecStr` (Decimal in Python,
  string in JSON). Never float in the contract.
- Customer statistics are **descriptive only**: no score, rating, rank or
  prediction field. The one estimate allowed (cash-in) says so in its name and
  carries a note. Every average is nullable and carries a `*_reason` plus
  `based_on` / `min_history`, so the UI can show "not enough history" instead of
  a number from one or two invoices.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any

from pydantic import Field

from backend.app.schemas import ContractModel, DecStr
from backend.app.schemas_v4 import CaseSummary

# The v5 contract number. Deliberately NOT the app-wide CONTRACT_VERSION: v1.0
# responses must stay byte-identical and keep reporting "1.0".
CONTRACT_VERSION_V1_2 = "1.2"


# ----------------------------------------------------------------- enums ----


class CustomerKind(str, Enum):
    """A customer identified by a PAN, or provisional until a PAN is known."""

    PAN = "PAN"
    PROVISIONAL = "PROVISIONAL"


class PaymentMethod(str, Enum):
    """How the buyer paid. Matches `backend/store/models.py` Payment.method."""

    BANK = "bank"
    UPI = "upi"
    CHEQUE = "cheque"
    CASH = "cash"
    OTHER = "other"


class SuggestionKind(str, Enum):
    """Owner actions only. Nothing here merges automatically."""

    ATTACH = "ATTACH"
    LINK_AS_GROUP = "LINK_AS_GROUP"


# -------------------------------------------------------------- identity ----


class Customer(ContractModel):
    """A buyer in the owner's book, as stored in `customers`.

    `kind="PAN"` means the legal identity is known. `kind="PROVISIONAL"` means
    the owner has not confirmed a PAN yet; the record is grouped by GSTIN or by
    normalised name, and any match is a suggestion, never an automatic merge.
    """

    id: str
    kind: CustomerKind
    pan: str | None = None
    display_name: str
    gstins: list[str] = Field(
        default_factory=list,
        description="GSTINs seen for this customer, including invalid demo values.",
    )
    created_at: datetime


class CustomerRow(ContractModel):
    """One row of the customer list. Descriptive totals, never a score."""

    id: str
    display_name: str
    kind: CustomerKind
    pan: str | None = None
    gstin_count: int = 0
    group_id: str | None = None
    group_label: str | None = None
    invoice_count: int = 0
    outstanding_total: DecStr
    overdue_total: DecStr
    oldest_overdue_days: int | None = None
    last_payment_on: date | None = None
    suggestion_count: int = 0


class CustomerGroupRow(ContractModel):
    """An owner-made link between different PANs. It is not a merge."""

    id: str
    label: str
    created_by: str
    created_at: datetime
    member_count: int
    members: list[CustomerRow] = Field(default_factory=list)


# ---------------------------------------------------------------- stats ----


class CustomerStats(ContractModel):
    """Descriptive payment history for one customer.

    `avg_days_to_pay` and `on_time_pct` are null when there is too little
    history; `*_reason` then says why, and `based_on` / `min_history` make the
    sample size explicit. Days are measured from the engine's day of acceptance
    to the payment date, never from the invoice date; "on time" means paid by
    the engine's legal due date.
    """

    as_of: date
    invoice_count: int = 0
    paid_invoice_count: int = 0
    based_on: int = 0
    min_history: int = 3
    avg_days_to_pay: DecStr | None = None
    avg_days_to_pay_reason: str | None = None
    on_time_pct: DecStr | None = Field(
        default=None,
        description="Percentage of fully paid invoices paid by the engine's legal due date.",
    )
    on_time_pct_reason: str | None = None
    outstanding_total: DecStr
    overdue_total: DecStr
    paid_total: DecStr
    oldest_overdue_days: int | None = None
    last_payment_on: date | None = None
    cash_in_estimate: DecStr | None = Field(
        default=None,
        description="An estimate, not a promise; see cash_in_estimate_note.",
    )
    cash_in_estimate_note: str | None = None


class ChartSeriesPoint(ContractModel):
    """One point in a chart series. `value` is a decimal string, never a float."""

    label: str
    value: DecStr
    count: int | None = None
    period_start: date | None = None
    period_end: date | None = None


# --------------------------------------------------------------- ledger ----


class Payment(ContractModel):
    """One payment the owner recorded. A voided payment stays in the history."""

    id: str
    case_id: str
    amount: DecStr
    paid_on: date
    method: PaymentMethod
    note: str | None = None
    created_at: datetime
    voided_at: datetime | None = None


class PaymentCreateRequest(ContractModel):
    """`POST /cases/{id}/payments`: one payment the owner received."""

    amount: DecStr = Field(gt=0, description="Must be greater than zero.")
    paid_on: date
    method: PaymentMethod
    note: str | None = None


class PaymentListResponse(ContractModel):
    """`GET /cases/{id}/payments`: the case's payment history, including voided rows."""

    case_id: str
    payments: list[Payment] = Field(default_factory=list)
    count: int


class Suggestion(ContractModel):
    """A name-match suggestion. It is never applied automatically.

    `ATTACH`: `a` is a PROVISIONAL customer that could be attached to the PAN
    customer `b`. `LINK_AS_GROUP`: `a` and `b` are different PANs that the owner
    may link as a group; they are never merged.
    """

    a: str
    b: str
    kind: SuggestionKind
    similarity: DecStr = Field(
        description="Normalised-name similarity between 0 and 1, as a decimal string."
    )
    reason: str


# -------------------------------------------------------------- imports ----


class ImportPreview(ContractModel):
    """A dry-run view of a CSV import. Nothing is written until the owner confirms."""

    preview_id: str
    filename: str
    total_rows: int
    valid_rows: int
    invalid_rows: int
    columns: list[str] = Field(default_factory=list)
    sample_rows: list[dict[str, str]] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    requires_confirmation: bool = True


class ImportResult(ContractModel):
    """The outcome of an owner-confirmed CSV import."""

    preview_id: str
    imported: int
    skipped: int
    failed: int
    customers_created: int = 0
    customers_matched: int = 0
    gstins_attached: int = 0
    case_ids: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


# ------------------------------------------------------------- portfolio ----


class PortfolioInsights(ContractModel):
    """Descriptive portfolio totals for the owner's own book.

    There is no buyer score, ranking or prediction. `cash_in_estimate` is the
    single estimate and is labelled as one. `top_customer_share_pct` and
    `concentration_note` describe concentration from the owner's data; they do
    not label a buyer as risky.
    """

    as_of: date
    customer_count: int = 0
    invoice_count: int = 0
    outstanding_total: DecStr
    overdue_total: DecStr
    paid_total: DecStr
    based_on: int = 0
    min_history: int = 3
    avg_days_to_pay: DecStr | None = None
    avg_days_to_pay_reason: str | None = None
    on_time_pct: DecStr | None = None
    on_time_pct_reason: str | None = None
    cash_in_estimate: DecStr | None = None
    cash_in_estimate_note: str | None = None
    top_customer_share_pct: DecStr | None = None
    top_customer_id: str | None = None
    concentration_note: str | None = None
    outstanding_by_customer: list[ChartSeriesPoint] = Field(default_factory=list)
    collections_by_month: list[ChartSeriesPoint] = Field(default_factory=list)


class CustomerProfile(ContractModel):
    """The customer page: identity, group, descriptive stats, payments and cases."""

    customer: Customer
    group: CustomerGroupRow | None = None
    stats: CustomerStats
    payments: list[Payment] = Field(default_factory=list)
    suggestions: list[Suggestion] = Field(default_factory=list)
    cases: list[CaseSummary] = Field(default_factory=list)


# --------------------------------------------------- openapi integration ----
V1_2_MODELS: tuple[type[ContractModel], ...] = (
    Customer,
    CustomerRow,
    CustomerGroupRow,
    CustomerProfile,
    CustomerStats,
    ChartSeriesPoint,
    Payment,
    PaymentCreateRequest,
    PaymentListResponse,
    Suggestion,
    ImportPreview,
    ImportResult,
    PortfolioInsights,
)


def component_schemas() -> tuple[dict[str, dict[str, Any]], frozenset[str]]:
    """Every v1.2 model as `{component name: JSON schema}`, plus authored names.

    Same contract as `schemas_v4.component_schemas`: Pydantic's `$defs` are
    hoisted so the emitted document has no dangling `#/$defs/` references, and
    transitive v1.0/v1.1 models (for example `CaseSummary` inside
    `CustomerProfile`) are returned under their existing component names so the
    injector can keep the frozen definition untouched.
    """
    out: dict[str, dict[str, Any]] = {}
    for model in V1_2_MODELS:
        schema = model.model_json_schema(ref_template="#/components/schemas/{model}")
        for name, sub in schema.pop("$defs", {}).items():
            out.setdefault(name, sub)
        out.setdefault(model.__name__, schema)
    authored = frozenset(m.__name__ for m in V1_2_MODELS)
    return out, authored
