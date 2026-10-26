"""Contract v1.2 — additive Pydantic models for the v5 Customer book.

Source: the v5 customer-book work (CB1-CB5) and `AGENTS.md` rules 22-27.

Rules this module follows:
- **Additive only.** Nothing here changes a v1.0 or v1.1 model.
  `CONTRACT_VERSION` stays "1.0" because it is echoed in v1.0 response bodies;
  v1.2 has its own constant and no v1 route returns it.
- **Additive, again.** CB3-CB5 added the customer-book routes, so the shapes
  below are now referenced by real operations. Every field published before
  those routes still exists with the same name and type; the new blocks sit
  beside them (`CustomerRow.stats` beside `outstanding_total`, and so on).
- Money, percentages and similarity ratios are `DecStr` (Decimal in Python,
  string in JSON). Never float in the contract.
- Customer statistics are **descriptive only**: no score, rating, rank or
  prediction field. The one estimate allowed (cash-in) says so in its name and
  carries a note. Every average is nullable and carries a `*_reason` plus
  `based_on` / `min_history`, so the UI can show "not enough history" instead of
  a number from one or two invoices.
- `BuyerCostSummary` carries **three separate lines** and no combined total
  (AGENTS.md rule 8).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import Field

from backend.app.schemas import ContractModel, DecStr
from backend.app.schemas_v4 import CaseSummary, Event

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


class CustomerSort(str, Enum):
    """The `sort` values `GET /api/v1/customers` accepts.

    Money and day sorts are largest-first; `name` is A-Z. A customer or group
    with no figure (an average held back for too little history) sorts last.
    """

    OUTSTANDING = "outstanding"
    OVERDUE = "overdue"
    AVG_DAYS = "avg_days"
    NAME = "name"


class CustomerEntryKind(str, Enum):
    """A list entry is either one customer or one owner-made group."""

    CUSTOMER = "CUSTOMER"
    GROUP = "GROUP"


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


class CustomerTrack(ContractModel):
    """One open v4 track on one of the customer's invoices.

    Descriptive state only: the state machine's own names, with no legal
    conclusion drawn from them.
    """

    case_id: str
    kind: str = Field(description="FINANCING or RECOVERY")
    state: str
    stage: int | None = Field(
        default=None, description="Recovery stage 1-4 when the state names one."
    )
    version: int = 1
    created_at: datetime


# ---------------------------------------------------------------- stats ----


class CustomerStats(ContractModel):
    """Descriptive payment history for one customer.

    `avg_days_to_pay` and `on_time_pct` are null when there is too little
    history; `*_reason` then says why, and `based_on` / `min_history` make the
    sample size explicit. Days are measured from the engine's day of acceptance
    to the payment date, never from the invoice date; "on time" means paid by
    the engine's legal due date.

    `paid_total` is the sum of the owner-recorded, non-voided payments for this
    customer's invoices. It is a record of money received, not a computed claim.
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
    # Additive: the figures the customer page shows beside the averages.
    interest_accrued_now: DecStr = Field(
        default=Decimal("0.00"),
        description="Sum of the engine's accrued interest across this customer's invoices.",
    )
    median_days_to_pay: DecStr | None = None
    worst_days_to_pay: DecStr | None = None
    on_time_count: int = 0
    paid_count: int = 0
    on_time_text: str | None = Field(
        default=None,
        description="Plain count, e.g. '3 of 5 on time'. A count, not an average.",
    )


class CustomerSeriesPoint(ContractModel):
    """One invoice of the customer's chart.

    `days_to_pay` is set only for a fully paid invoice; an open invoice carries
    `days_open_so_far`. `legal_due_days` is `due_date - acceptance_date` from the
    engine, never a recomputed statutory period.
    """

    case_id: str
    invoice_no: str
    accepted_on: date | None = None
    due_date: date | None = None
    legal_due_days: int | None = None
    days_to_pay: int | None = None
    days_open_so_far: int | None = None
    days_overdue: int | None = None
    status: str = Field(description="PAID, OVERDUE, NOT_DUE or NO_DUE_DATE")
    outstanding: DecStr
    on_time: bool | None = None
    based_on: int = 1


class CustomerRow(ContractModel):
    """One row of the customer list. Descriptive totals, never a score.

    The flat fields predate the CB3-CB5 routes and are kept for compatibility;
    `customer`, `gstins`, `stats` and `active_tracks` carry the same facts in
    the nested shape the list screen reads.
    """

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
    # Additive (CB3-CB5).
    customer: Customer | None = None
    gstins: list[str] = Field(default_factory=list)
    stats: CustomerStats | None = None
    active_tracks: list[CustomerTrack] = Field(default_factory=list)


class CustomerInvoice(ContractModel):
    """One invoice on the customer page: the store's facts plus the engine's dates."""

    case_id: str
    invoice_no: str
    invoice_date: date
    accepted_amount: DecStr
    accepted_on: date | None = None
    due_date: date | None = None
    days_overdue: int | None = None
    days_to_pay: int | None = None
    days_open_so_far: int | None = None
    outstanding: DecStr
    status: str
    on_time: bool | None = None
    last_payment_on: date | None = None
    active_track: CustomerTrack | None = None


class CustomerGroupRow(ContractModel):
    """An owner-made link between different PANs. It is not a merge.

    `stats` holds summed totals. Money and counts sum correctly; an average of
    member averages would not, so `avg_days_to_pay` and `on_time_pct` stay null
    with `totals_note` saying why and the members carrying their own averages.
    """

    id: str
    label: str
    created_by: str
    created_at: datetime
    member_count: int
    members: list[CustomerRow] = Field(default_factory=list)
    # Additive (CB3-CB5).
    gstins: list[str] = Field(default_factory=list)
    stats: CustomerStats | None = None
    active_tracks: list[CustomerTrack] = Field(default_factory=list)
    totals_note: str | None = None


class CustomerListEntry(ContractModel):
    """One line of `GET /customers`: a customer, or a group that replaces its members."""

    kind: CustomerEntryKind
    id: str
    display_name: str
    customer: CustomerRow | None = None
    group: CustomerGroupRow | None = None


class CustomerListResponse(ContractModel):
    """`GET /api/v1/customers`: the owner's book, sorted the way they asked.

    Every row is descriptive. Nothing here ranks two buyers against each other,
    and nothing is shared with another owner.
    """

    as_of: date
    sort: CustomerSort
    grouped: bool = False
    entries: list[CustomerListEntry] = Field(default_factory=list)
    count: int = 0
    min_history: int = 3
    note: str


# ----------------------------------------------------------- buyer cost ----


class BuyerCostLine(ContractModel):
    """One of the three buyer-cost lines. It is never added to the others."""

    id: str = Field(description="PERMANENT_LOSS, DEFERRAL or DISCLOSURE")
    label: str
    amount: DecStr | None = Field(
        default=None, description="Null for the disclosure line, which is not money."
    )
    case_count: int = 0
    case_ids: list[str] = Field(default_factory=list)
    items: list[str] = Field(
        default_factory=list, description="Disclosure flags from the engine, as text."
    )
    note: str


class BuyerCostSummary(ContractModel):
    """The buyer's side of the delay, as three separate lines.

    AGENTS.md rule 8: the permanent loss, the deferral cost and the disclosure
    requirement are separate facts and are **never** combined into one total.
    """

    as_of: date
    lines: list[BuyerCostLine] = Field(
        default_factory=list, description="Exactly three lines, in a fixed order."
    )
    note: str


class SuggestedAction(ContractModel):
    """A next step for one open invoice, taken from the existing workflow guidance."""

    case_id: str
    invoice_no: str
    action: str = Field(description="An action code from the workflow transition table.")
    label: str
    reason: str
    source: str = Field(
        description="WORKFLOW: the action comes from the case's workflow transition table."
    )


# --------------------------------------------------------------- series ----


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


# ----------------------------------------------------------- suggestions ----


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


class SuggestionListResponse(ContractModel):
    """`GET /api/v1/customers/suggestions`: owner actions the book could use.

    Nothing is applied. The threshold is the configured product setting (not
    law), shown so the owner can see why a pair was suggested.
    """

    suggestions: list[Suggestion] = Field(default_factory=list)
    count: int = 0
    threshold: DecStr
    min_history: int = 3
    note: str


class SuggestionDismissRequest(ContractModel):
    """`POST /customers/suggestions/dismiss`: the owner says "not the same buyer"."""

    a: str
    b: str
    reason: str | None = None


class SuggestionDismissResponse(ContractModel):
    """A dismissed pair is excluded from later suggestions and stays dismissible."""

    a: str
    b: str
    dismissed: bool
    dismissed_at: datetime | None = None
    note: str


# ------------------------------------------------------ attach / detach ----


class CustomerAttachRequest(ContractModel):
    """`POST /customers/{provisional_id}/attach`: fold a provisional into a customer."""

    target_customer_id: str
    note: str | None = None


class CustomerAttachResponse(ContractModel):
    """What moved, and how to undo it (`POST /customers/{id}/detach`)."""

    provisional: Customer
    target: Customer
    case_ids: list[str] = Field(default_factory=list)
    gstins: list[str] = Field(default_factory=list)
    audited_case_ids: list[str] = Field(default_factory=list)
    detach_with: str
    note: str


class CustomerDetachRequest(ContractModel):
    """`POST /customers/{id}/detach`: separate invoices or a GSTIN from a customer.

    Name `case_ids`, a `gstin`, or both. A detach that reverses an attach puts
    things back where they were; any other detach moves the invoices to their own
    provisional customer.
    """

    case_ids: list[str] = Field(default_factory=list)
    gstin: str | None = None
    reason: str | None = None


class CustomerDetachResponse(ContractModel):
    """What moved away and where it went. Every entry is audited on its case."""

    customer: Customer
    case_ids: list[str] = Field(default_factory=list)
    gstins: list[str] = Field(default_factory=list)
    moved_to: list[str] = Field(default_factory=list)
    audited_case_ids: list[str] = Field(default_factory=list)
    note: str


class CustomerGroupCreateRequest(ContractModel):
    """`POST /customer-groups`: link customers that are not the same PAN."""

    label: str
    customer_ids: list[str] = Field(default_factory=list)


class CustomerGroupMemberRequest(ContractModel):
    """`POST /customer-groups/{id}/members`: add one customer to a group."""

    customer_id: str


class CustomerGroupMembershipResponse(ContractModel):
    """The group after a membership change, plus whether anything changed."""

    group: CustomerGroupRow
    customer_id: str
    changed: bool
    note: str


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


class ImportCustomerMatch(ContractModel):
    """The customer the row would land on, decided by the CB1 resolver (read only)."""

    customer_id: str | None = None
    display_name: str | None = None
    matched_on: str = Field(description="GSTIN, PAN, NAME or NEW")
    would_create: bool = False
    warnings: list[str] = Field(default_factory=list)


class ImportParsedRow(ContractModel):
    """One CSV row after parsing. Money and dates are typed, never floats."""

    invoice_no: str
    invoice_date: date
    delivery_date: date
    amount: DecStr
    buyer_name: str
    buyer_gstin: str | None = None
    agreed_credit_days: int | None = None
    paid_on: date | None = None
    paid_amount: DecStr | None = None
    notes: str | None = None


class ImportRowResult(ContractModel):
    """One row's verdict: what was read, which customer, and what is wrong with it."""

    row_no: int = Field(description="The CSV line number; the header is row 1.")
    status: str = Field(
        description="VALID, INVALID, DUPLICATE for a preview; CREATED, SKIPPED or FAILED for a commit."
    )
    parsed: ImportParsedRow | None = None
    customer_match: ImportCustomerMatch | None = None
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    case_id: str | None = None
    payment_id: str | None = None


class ImportSummary(ContractModel):
    """Counts for the whole file, so a screen can say what happened in one line."""

    total_rows: int
    valid_rows: int = 0
    invalid_rows: int = 0
    duplicate_rows: int = 0
    created_rows: int = 0
    skipped_rows: int = 0
    failed_rows: int = 0
    payments_created: int = 0
    date_format: str = Field(description="The one date format detected for the whole file.")
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ImportPreviewResponse(ContractModel):
    """`POST /api/v1/import/invoices?mode=preview`: parse and check, store nothing."""

    mode: str = "preview"
    as_of: date
    filename: str
    import_token: str
    expires_at: datetime
    rows: list[ImportRowResult] = Field(default_factory=list)
    summary: ImportSummary
    note: str


class ImportCommitResponse(ContractModel):
    """`POST /api/v1/import/invoices?mode=commit`: the cases and payments it created."""

    mode: str = "commit"
    as_of: date
    filename: str
    import_token: str
    rows: list[ImportRowResult] = Field(default_factory=list)
    summary: ImportSummary
    created_case_ids: list[str] = Field(default_factory=list)
    payment_ids: list[str] = Field(default_factory=list)
    skipped: list[str] = Field(default_factory=list)
    note: str


# ------------------------------------------------------------- portfolio ----


class BeforeMarchHint(ContractModel):
    """An open overdue invoice and the next 31 March its buyer's tax timing meets."""

    customer_id: str
    customer_name: str
    case_id: str
    invoice_no: str
    outstanding: DecStr
    next_march: date
    note: str
    based_on: int = 1


class TermsFlagHint(ContractModel):
    """A customer whose observed payment timing exceeds the engine's credit cap."""

    customer_id: str
    customer_name: str
    avg_days_to_pay: DecStr
    credit_cap_days: int
    text: str
    based_on: int = 0


class CashInWeekHint(ContractModel):
    """One ISO week of the labelled cash-in estimate (a forecast, not a promise)."""

    iso_week: str
    week_start: date
    amount: DecStr
    invoice_count: int
    based_on: int = 0
    label: str


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
    # Additive (CB2 wiring).
    interest_accrued_now: DecStr = Decimal("0.00")
    paid_count: int = 0
    median_days_to_pay: DecStr | None = None
    worst_days_to_pay: DecStr | None = None
    on_time_count: int = 0
    on_time_text: str | None = None
    history_reason: str | None = None
    concentration_flag: bool = False
    concentration_reason: str | None = None
    before_march: list[BeforeMarchHint] = Field(default_factory=list)
    terms_flags: list[TermsFlagHint] = Field(default_factory=list)
    cash_in_weeks: list[CashInWeekHint] = Field(default_factory=list)
    cash_in_reason: str | None = None
    assumptions: list[str] = Field(default_factory=list)


class CustomerProfile(ContractModel):
    """The customer page: identity, group, descriptive stats, payments and cases."""

    customer: Customer
    group: CustomerGroupRow | None = None
    stats: CustomerStats
    payments: list[Payment] = Field(default_factory=list)
    suggestions: list[Suggestion] = Field(default_factory=list)
    cases: list[CaseSummary] = Field(default_factory=list)
    # Additive (CB3-CB5).
    gstins: list[str] = Field(default_factory=list)
    series: list[CustomerSeriesPoint] = Field(default_factory=list)
    invoices: list[CustomerInvoice] = Field(default_factory=list)
    timeline: list[Event] = Field(
        default_factory=list, description="Audit events for this customer's cases, newest first."
    )
    buyer_cost_summary: BuyerCostSummary | None = None
    suggested_next_actions: list[SuggestedAction] = Field(default_factory=list)


# --------------------------------------------------- openapi integration ----
V1_2_MODELS: tuple[type[ContractModel], ...] = (
    Customer,
    CustomerTrack,
    CustomerRow,
    CustomerGroupRow,
    CustomerProfile,
    CustomerStats,
    CustomerSeriesPoint,
    CustomerInvoice,
    CustomerListEntry,
    CustomerListResponse,
    BuyerCostLine,
    BuyerCostSummary,
    SuggestedAction,
    ChartSeriesPoint,
    Payment,
    PaymentCreateRequest,
    PaymentListResponse,
    Suggestion,
    SuggestionListResponse,
    SuggestionDismissRequest,
    SuggestionDismissResponse,
    CustomerAttachRequest,
    CustomerAttachResponse,
    CustomerDetachRequest,
    CustomerDetachResponse,
    CustomerGroupCreateRequest,
    CustomerGroupMemberRequest,
    CustomerGroupMembershipResponse,
    ImportPreview,
    ImportResult,
    ImportCustomerMatch,
    ImportParsedRow,
    ImportRowResult,
    ImportSummary,
    ImportPreviewResponse,
    ImportCommitResponse,
    BeforeMarchHint,
    TermsFlagHint,
    CashInWeekHint,
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
