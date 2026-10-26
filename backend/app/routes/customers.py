"""The v5 Customer book routes (contract v1.2): read model, owner actions, insights.

The read side is a **presentation** layer. Every number it shows is produced by
`backend/insights/` from the stored engine evaluations; this module builds the
inputs (`CaseSnapshot`, `PaymentRecord`) and maps the results to contract models.
It never recomputes interest, a due date or a day count. The one thing a read may
write is the engine snapshot itself: a case with no evaluation, or one whose
latest snapshot is from an earlier day, is evaluated here first, exactly as
`GET /api/v1/cases/{id}` already does. A seeded case therefore shows real figures
the first time the book is opened, and s.16 interest on screen is today's.

The only arithmetic in this module is display aggregation of figures that
`backend/insights/` already produced: a group total is the sum of its members'
figures, `paid_total` is the sum of the owner's recorded payments, and the
portfolio cash-in figure is the sum of the weekly estimate. Averages are never
averaged; a group shows totals and lets each member carry its own average and
sample size (AGENTS.md rule 25).

Writes are owner actions, and each one is reversible and audited:

- `attach` folds a PROVISIONAL customer into a target customer. Different PANs
  are refused (rule 23): those are a group, never a merge. The provisional row
  is kept, so `detach` can put the invoices back exactly where they were.
- `detach` restores what a matching `attach` moved, or gives the invoice its own
  provisional customer when there is nothing to restore.
- `customer-groups` and `suggestions/dismiss` use the store's own audited
  functions; nothing is merged and nothing is applied automatically.

Every mutation requires an `Idempotency-Key` header and is recorded with the
existing idempotency helper, so a retry cannot apply it twice.
"""

from __future__ import annotations

import calendar
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query
from sqlmodel import select

from backend.app import deps
from backend.app.config_loader import identity_settings, insights_config, load_config
from backend.app.routes import cases as case_routes
from backend.app.schemas import CaseEvaluationResponse, LimitationStatus
from backend.app.schemas_v4 import Event as ContractEvent
from backend.app.schemas_v4 import CaseSummary, TrackState
from backend.app.schemas_v5 import (
    BeforeMarchHint,
    BuyerCostLine,
    BuyerCostSummary,
    CashInWeekHint,
    ChartSeriesPoint,
    Customer,
    CustomerAttachRequest,
    CustomerAttachResponse,
    CustomerDetachRequest,
    CustomerDetachResponse,
    CustomerEntryKind,
    CustomerGroupCreateRequest,
    CustomerGroupMemberRequest,
    CustomerGroupMembershipResponse,
    CustomerGroupRow,
    CustomerInvoice,
    CustomerKind,
    CustomerListEntry,
    CustomerListResponse,
    CustomerProfile,
    CustomerRow,
    CustomerSeriesPoint,
    CustomerSort,
    CustomerStats,
    CustomerTrack,
    Payment,
    PortfolioInsights,
    SuggestedAction,
    Suggestion,
    SuggestionDismissRequest,
    SuggestionDismissResponse,
    SuggestionKind,
    SuggestionListResponse,
    TermsFlagHint,
)
from backend.insights.insights import (
    CASH_IN_LABEL,
    CASH_IN_NO_HISTORY,
    CONCENTRATION_BELOW_THRESHOLD,
    CONCENTRATION_NO_OUTSTANDING,
    BEFORE_MARCH_NOTE,
    PortfolioInsightsResult,
    portfolio_insights,
)
from backend.insights.stats import (
    STATUS_OVERDUE,
    CaseSnapshot,
    CustomerStatsResult,
    InsightsConfig,
    PaymentRecord,
    TrackSummary,
    customer_stats,
    q2,
)
from backend.store import audit, idempotency
from backend.store import customers as customer_book
from backend.store.db import session_scope
from backend.store.models import Case as CaseRow
from backend.store.models import Customer as CustomerRowModel
from backend.store.models import CustomerGstin, CustomerGroup, CustomerGroupMember
from backend.store.models import Evaluation as EvaluationRow
from backend.store.models import Event as EventRow
from backend.store.models import Payment as PaymentRow
from backend.store.models import Track as TrackRow
from backend.workflow.transitions import available_actions

router = APIRouter(prefix="/api/v1", tags=["customers"])

# Idempotency scopes. The body carries the ids, so the same key used for a
# different target is a conflict rather than a replay.
ROUTE_ATTACH = "POST /api/v1/customers/{id}/attach"
ROUTE_DETACH = "POST /api/v1/customers/{id}/detach"
ROUTE_GROUP_CREATE = "POST /api/v1/customer-groups"
ROUTE_GROUP_ADD = "POST /api/v1/customer-groups/{id}/members"
ROUTE_GROUP_REMOVE = "DELETE /api/v1/customer-groups/{id}/members/{customer_id}"
ROUTE_DISMISS = "POST /api/v1/customers/suggestions/dismiss"

# Event types this module writes. The store owns its own (`customer.created`,
# `customer.group_created`, `customer.merge_dismissed`, ...).
CUSTOMER_ATTACH = "customer.attach"
CUSTOMER_DETACH = "customer.detach"

HISTORY_NOTE = (
    "Descriptive only, from the invoices you entered. A customer is a grouping of "
    "your own invoices, not a rating, and nothing is shared with another owner."
)

GROUP_AVERAGE_NOTE = (
    "Totals only: money and counts add up, averages do not. Expand the group to "
    "see each member's average and the number of invoices behind it."
)

PAID_TOTAL_NOTE = (
    "paid_total is the sum of the payments you recorded and have not voided; "
    "it is not a computed claim."
)

BUYER_COST_NOTE = (
    "Three separate lines about the buyer's position. They are never added "
    "together (AGENTS.md rule 8)."
)

# Plain-English labels for the workflow's own action codes. No legal claim is
# made by any of them; the action list comes from the transition table.
ACTION_LABELS: dict[str, str] = {
    "check_financeability": "Check whether this invoice can be paid early",
    "request_buyer_acceptance": "Ask the buyer to accept the invoice (early payment)",
    "start_recovery": "Start the recovery ladder",
    "switch_to_recovery": "Switch to the recovery ladder",
    "wait_for_buyer": "Wait for the buyer's answer",
    "wait_for_bids": "Wait for financier bids",
    "select_bid": "Choose a financier bid",
    "complete_esign": "Complete the demo e-sign",
    "wait_for_payout": "Wait for the payout",
    "retry_payout": "Retry the payout",
    "cancel_financing": "Cancel the early-payment request",
    "prepare_next_stage": "Prepare the next recovery stage",
    "mark_sent": "Record that you sent this stage",
    "mark_odr_filed": "Record that you filed on the ODR portal",
    "mark_paid": "Record the payment you received",
    "mark_settled": "Record the settlement",
    "view_events": "Review the audit trail",
    "download_pack": "Download the evidence pack",
}

MAX_ACTIONS_PER_CASE = 2
MAX_ACTIONS = 6
MAX_TIMELINE = 100


# --------------------------------------------------------------- helpers ----


def _now() -> datetime:
    return deps.get_adapters().clock.now()


def _today() -> date:
    return _now().date()


def _aware(value: datetime | None) -> datetime | None:
    """Treat a naive SQLite timestamp as UTC rather than as local time."""
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def _similarity(value: float | str | Decimal) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), ROUND_HALF_UP)


def _not_found(what: str, value: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"No {what} with id {value!r}")


def _require_key(key: str | None) -> str:
    value = (key or "").strip()
    if not value:
        raise HTTPException(
            status_code=400,
            detail=(
                "This action needs an Idempotency-Key header so a retry cannot "
                "apply it twice."
            ),
        )
    return value


def _dedup(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _stage_from_state(state: TrackState) -> int | None:
    if state.value.startswith("STAGE_"):
        head = state.value.split("_")[1]
        return int(head) if head.isdigit() else None
    return None


def _track_summary(row: TrackRow | None) -> TrackSummary | None:
    if row is None:
        return None
    return TrackSummary(
        kind=row.kind, state=row.state, version=row.version, created_at=_aware(row.created_at)
    )


def _track_contract(case_id: str, row: TrackRow | None) -> CustomerTrack | None:
    if row is None:
        return None
    state = TrackState(row.state)
    return CustomerTrack(
        case_id=case_id,
        kind=row.kind,
        state=row.state,
        stage=_stage_from_state(state),
        version=row.version,
        created_at=_aware(row.created_at) or _now(),
    )


# ----------------------------------------------------------- the read book ----


@dataclass
class Book:
    """Everything one customer-book read needs, loaded once.

    `stats` and `portfolio` come from `backend/insights/`; nothing here is a
    legal figure computed in this module.
    """

    as_of: date
    config: InsightsConfig
    customers: dict[str, CustomerRowModel] = field(default_factory=dict)
    gstins: dict[str, list[str]] = field(default_factory=dict)
    groups: dict[str, CustomerGroup] = field(default_factory=dict)
    group_members: dict[str, list[str]] = field(default_factory=dict)
    group_of: dict[str, str] = field(default_factory=dict)
    case_rows: dict[str, CaseRow] = field(default_factory=dict)
    cases_by_customer: dict[str, list[str]] = field(default_factory=dict)
    evaluations: dict[str, EvaluationRow] = field(default_factory=dict)
    tracks: dict[str, TrackRow] = field(default_factory=dict)
    payment_rows: list[PaymentRow] = field(default_factory=list)
    suggestions: list[dict[str, Any]] = field(default_factory=list)
    portfolio: PortfolioInsightsResult | None = None
    stats: dict[str, CustomerStatsResult] = field(default_factory=dict)

    def case_ids(self, customer_id: str) -> list[str]:
        return self.cases_by_customer.get(customer_id, [])

    def visible_customers(self) -> list[str]:
        """Customers with at least one invoice. An empty row is not a customer yet."""
        return sorted(
            (customer_id for customer_id, case_ids in self.cases_by_customer.items() if case_ids),
            key=lambda customer_id: (
                self.customers[customer_id].display_name.casefold(),
                customer_id,
            ),
        )


def _load_book(session, *, with_suggestions: bool = False) -> Book:
    """Load the book and let `backend/insights/` compute every statistic."""
    as_of = _today()
    config = insights_config(load_config())
    book = Book(as_of=as_of, config=config)

    for row in session.exec(select(CustomerRowModel)).all():
        book.customers[row.id] = row

    for link in session.exec(select(CustomerGstin).order_by(CustomerGstin.gstin)).all():
        book.gstins.setdefault(link.customer_id, []).append(link.gstin)

    for group in session.exec(select(CustomerGroup)).all():
        book.groups[group.id] = group
    for member in session.exec(select(CustomerGroupMember)).all():
        book.group_members.setdefault(member.group_id, []).append(member.customer_id)
        book.group_of[member.customer_id] = member.group_id

    for row in session.exec(select(CaseRow).order_by(CaseRow.created_at, CaseRow.id)).all():
        book.case_rows[row.id] = row
        if row.customer_id and row.customer_id in book.customers:
            book.cases_by_customer.setdefault(row.customer_id, []).append(row.id)

    # Latest stored snapshot per case. A case with no snapshot, or one from an
    # earlier day, is evaluated first: the book is the screen an owner opens
    # first, and an s.16 figure from yesterday is not today's money. This is the
    # same "GET may write" rule `GET /cases/{id}` already follows.
    latest: dict[str, EvaluationRow] = {}
    for row in session.exec(
        select(EvaluationRow).order_by(
            EvaluationRow.as_of.desc(), EvaluationRow.created_at.desc()
        )
    ).all():
        latest.setdefault(row.case_id, row)
    for case_id, case_row in book.case_rows.items():
        stored = latest.get(case_id)
        if stored is None or stored.as_of != as_of:
            stored = case_routes._ensure_evaluation(session, case_row)
        book.evaluations[case_id] = stored

    for row in session.exec(select(TrackRow).where(TrackRow.closed_at.is_(None))).all():
        book.tracks[row.case_id] = row

    book.payment_rows = list(
        session.exec(
            select(PaymentRow).order_by(PaymentRow.paid_on, PaymentRow.created_at, PaymentRow.id)
        ).all()
    )

    snapshots = [
        CaseSnapshot(
            case_id=row.id,
            customer_id=row.customer_id or "",
            customer_name=(
                book.customers[row.customer_id].display_name
                if row.customer_id in book.customers
                else ""
            ),
            invoice_no=row.invoice_no,
            invoice_date=row.invoice_date,
            accepted_amount=row.accepted_amount,
            evaluation=(
                book.evaluations[row.id].response_json
                if row.id in book.evaluations
                else None
            ),
            active_track=_track_summary(book.tracks.get(row.id)),
        )
        for row in book.case_rows.values()
        if row.customer_id
    ]
    payment_records = [
        PaymentRecord(
            payment_id=row.id,
            case_id=row.case_id,
            amount=row.amount,
            paid_on=row.paid_on,
            voided_at=row.voided_at,
        )
        for row in book.payment_rows
    ]

    book.portfolio = portfolio_insights(
        cases=snapshots, payments=payment_records, as_of=as_of, config=config
    )
    book.stats = {result.customer_id: result for result in book.portfolio.customers}

    if with_suggestions:
        settings = identity_settings(load_config())
        book.suggestions = customer_book.suggestions_for_book(
            session, threshold=settings.name_match_threshold
        )
    return book


def _stats_for(book: Book, customer_id: str) -> CustomerStatsResult:
    """The customer's stats, or an empty result for a customer with no invoices."""
    existing = book.stats.get(customer_id)
    if existing is not None:
        return existing
    name = book.customers[customer_id].display_name if customer_id in book.customers else ""
    return customer_stats(
        customer_id=customer_id,
        customer_name=name,
        cases=[],
        payments=[],
        as_of=book.as_of,
        config=book.config,
    )


def _history_reason(result: CustomerStatsResult) -> str | None:
    """Why an average is null. Plain English, always with the sample size."""
    if not result.history_sufficient:
        return (
            f"Not enough history: {result.paid_count} fully paid invoice(s), "
            f"{result.min_history} needed before an average is shown."
        )
    if result.based_on_n == 0:
        return (
            "No fully paid invoice has both an engine acceptance date and a "
            "payment date yet, so there is nothing to average."
        )
    return None


def _paid_total(book: Book, case_ids: Sequence[str]) -> Decimal:
    wanted = set(case_ids)
    return q2(
        sum(
            (
                row.amount
                for row in book.payment_rows
                if row.case_id in wanted and row.voided_at is None
            ),
            Decimal("0.00"),
        )
    )


def _stats_contract(book: Book, result: CustomerStatsResult) -> CustomerStats:
    case_ids = [point.case_id for point in result.series]
    overdue_days = [
        point.days_overdue
        for point in result.series
        if point.status == STATUS_OVERDUE and point.days_overdue is not None
    ]
    return CustomerStats(
        as_of=result.as_of,
        invoice_count=result.invoices_count,
        paid_invoice_count=result.paid_count,
        based_on=result.based_on_n,
        min_history=result.min_history,
        avg_days_to_pay=result.avg_days_to_pay,
        avg_days_to_pay_reason=_history_reason(result),
        on_time_pct=result.on_time_pct,
        on_time_pct_reason=_history_reason(result),
        outstanding_total=result.outstanding,
        overdue_total=result.overdue_amount,
        paid_total=_paid_total(book, case_ids),
        oldest_overdue_days=max(overdue_days) if overdue_days else None,
        last_payment_on=result.last_payment_on,
        cash_in_estimate=None,
        cash_in_estimate_note=(
            "The cash-in estimate is a portfolio figure; see GET /api/v1/insights."
        ),
        interest_accrued_now=result.interest_accrued_now,
        median_days_to_pay=result.median_days_to_pay,
        worst_days_to_pay=result.worst_days_to_pay,
        on_time_count=result.on_time_count,
        paid_count=result.paid_count,
        on_time_text=(
            f"{result.on_time_count} of {result.paid_count} on time"
            if result.paid_count
            else None
        ),
    )


def _customer_contract(book: Book, customer_id: str) -> Customer:
    row = book.customers[customer_id]
    return Customer(
        id=row.id,
        kind=CustomerKind(row.kind),
        pan=row.pan,
        display_name=row.display_name,
        gstins=book.gstins.get(customer_id, []),
        created_at=_aware(row.created_at) or _now(),
    )


def _row_contract(book: Book, customer_id: str) -> CustomerRow:
    row = book.customers[customer_id]
    stats = _stats_contract(book, _stats_for(book, customer_id))
    group_id = book.group_of.get(customer_id)
    tracks = [
        track
        for track in (
            _track_contract(case_id, book.tracks.get(case_id))
            for case_id in book.case_ids(customer_id)
        )
        if track is not None
    ]
    suggestion_count = sum(
        1 for item in book.suggestions if customer_id in (item.get("a"), item.get("b"))
    )
    return CustomerRow(
        id=row.id,
        display_name=row.display_name,
        kind=CustomerKind(row.kind),
        pan=row.pan,
        gstin_count=len(book.gstins.get(customer_id, [])),
        group_id=group_id,
        group_label=book.groups[group_id].label if group_id in book.groups else None,
        invoice_count=stats.invoice_count,
        outstanding_total=stats.outstanding_total,
        overdue_total=stats.overdue_total,
        oldest_overdue_days=stats.oldest_overdue_days,
        last_payment_on=stats.last_payment_on,
        suggestion_count=suggestion_count,
        customer=_customer_contract(book, customer_id),
        gstins=book.gstins.get(customer_id, []),
        stats=stats,
        active_tracks=sorted(tracks, key=lambda track: (track.created_at, track.case_id)),
    )


def _group_row(book: Book, group_id: str) -> CustomerGroupRow | None:
    """A group row whose totals are the sum of its visible members.

    Money and counts sum exactly; averages are left null with a note, because an
    average of averages would describe nobody.
    """
    group = book.groups.get(group_id)
    if group is None:
        return None
    member_ids = [
        customer_id
        for customer_id in _dedup(book.group_members.get(group_id, []))
        if customer_id in book.customers and book.case_ids(customer_id)
    ]
    if not member_ids:
        return None
    member_ids.sort(key=lambda customer_id: (book.customers[customer_id].display_name.casefold(), customer_id))
    members = [_row_contract(book, customer_id) for customer_id in member_ids]
    member_stats = [member.stats for member in members if member.stats is not None]

    last_payments = [
        stats.last_payment_on for stats in member_stats if stats.last_payment_on is not None
    ]
    overdue_days = [
        stats.oldest_overdue_days
        for stats in member_stats
        if stats.oldest_overdue_days is not None
    ]
    paid_count = sum(stats.paid_count for stats in member_stats)
    on_time_count = sum(stats.on_time_count for stats in member_stats)
    totals = CustomerStats(
        as_of=book.as_of,
        invoice_count=sum(stats.invoice_count for stats in member_stats),
        paid_invoice_count=sum(stats.paid_invoice_count for stats in member_stats),
        based_on=sum(stats.based_on for stats in member_stats),
        min_history=book.config.min_history,
        avg_days_to_pay=None,
        avg_days_to_pay_reason=GROUP_AVERAGE_NOTE,
        on_time_pct=None,
        on_time_pct_reason=GROUP_AVERAGE_NOTE,
        outstanding_total=q2(
            sum((stats.outstanding_total for stats in member_stats), Decimal("0.00"))
        ),
        overdue_total=q2(
            sum((stats.overdue_total for stats in member_stats), Decimal("0.00"))
        ),
        paid_total=q2(sum((stats.paid_total for stats in member_stats), Decimal("0.00"))),
        oldest_overdue_days=max(overdue_days) if overdue_days else None,
        last_payment_on=max(last_payments) if last_payments else None,
        cash_in_estimate=None,
        cash_in_estimate_note=None,
        interest_accrued_now=q2(
            sum((stats.interest_accrued_now for stats in member_stats), Decimal("0.00"))
        ),
        median_days_to_pay=None,
        worst_days_to_pay=None,
        on_time_count=on_time_count,
        paid_count=paid_count,
        on_time_text=f"{on_time_count} of {paid_count} on time" if paid_count else None,
    )
    return CustomerGroupRow(
        id=group.id,
        label=group.label,
        created_by=group.created_by,
        created_at=_aware(group.created_at) or _now(),
        member_count=len(members),
        members=members,
        gstins=sorted(
            gstin for customer_id in member_ids for gstin in book.gstins.get(customer_id, [])
        ),
        stats=totals,
        active_tracks=sorted(
            (
                track
                for member in members
                for track in member.active_tracks
            ),
            key=lambda track: (track.created_at, track.case_id),
        ),
        totals_note=GROUP_AVERAGE_NOTE,
    )


def _entry_sort_key(
    sort: CustomerSort, entry: CustomerListEntry
) -> tuple[int, Decimal, str, str]:
    if sort is CustomerSort.NAME:
        return (0, Decimal("0"), entry.display_name.casefold(), entry.id)
    stats = entry.customer.stats if entry.customer is not None else entry.group.stats
    value: Decimal | None = None
    if stats is not None:
        if sort is CustomerSort.OUTSTANDING:
            value = stats.outstanding_total
        elif sort is CustomerSort.OVERDUE:
            value = stats.overdue_total
        elif sort is CustomerSort.AVG_DAYS:
            value = stats.avg_days_to_pay
    if value is None:
        # No figure to rank on (too little history): shown last, never guessed.
        return (1, Decimal("0"), entry.display_name.casefold(), entry.id)
    return (0, -value, entry.display_name.casefold(), entry.id)


def _list_entries(book: Book, *, grouped: bool) -> list[CustomerListEntry]:
    visible = book.visible_customers()
    entries: list[CustomerListEntry] = []
    seen_groups: set[str] = set()
    for customer_id in visible:
        group_id = book.group_of.get(customer_id)
        if grouped and group_id:
            if group_id in seen_groups:
                continue
            group = _group_row(book, group_id)
            seen_groups.add(group_id)
            if group is None:
                continue
            entries.append(
                CustomerListEntry(
                    kind=CustomerEntryKind.GROUP,
                    id=group.id,
                    display_name=group.label,
                    group=group,
                )
            )
            continue
        row = _row_contract(book, customer_id)
        entries.append(
            CustomerListEntry(
                kind=CustomerEntryKind.CUSTOMER,
                id=row.id,
                display_name=row.display_name,
                customer=row,
            )
        )
    return entries


# -------------------------------------------------------------- profile ----


def _case_summary(book: Book, case_id: str) -> CaseSummary:
    """`CaseSummary` from the stored snapshot, without re-running the engine."""
    row = book.case_rows[case_id]
    evaluation_row = book.evaluations.get(case_id)
    evaluation = (
        CaseEvaluationResponse.model_validate(evaluation_row.response_json)
        if evaluation_row is not None
        else None
    )
    track = book.tracks.get(case_id)
    state = TrackState(track.state) if track is not None else TrackState.NEW

    days_overdue = 0
    if evaluation is not None and evaluation.timeline is not None:
        days_overdue = int(evaluation.timeline.days_overdue or 0)

    stage = _stage_from_state(state)
    if stage is None and evaluation is not None and evaluation.evidence_readiness is not None:
        stage = evaluation.evidence_readiness.recommended_stage

    return CaseSummary(
        id=row.id,
        invoice_no=row.invoice_no,
        buyer_gstin=row.buyer_gstin,
        supplier_ref=row.supplier_ref,
        accepted_amount=row.accepted_amount,
        due_date=(
            evaluation.timeline.due_date
            if evaluation is not None and evaluation.timeline is not None
            else None
        ),
        days_overdue=days_overdue,
        calculation_date=(
            evaluation_row.as_of if evaluation_row is not None else row.invoice_date
        ),
        active_track=case_routes._track_contract(track),
        state=state,
        stage=stage,
        available_actions=available_actions(state, track.kind if track else None),
    )


def _series_contract(book: Book, customer_id: str) -> list[CustomerSeriesPoint]:
    result = _stats_for(book, customer_id)
    return [
        CustomerSeriesPoint(
            case_id=point.case_id,
            invoice_no=point.invoice_no,
            accepted_on=point.accepted_on,
            due_date=point.due_date,
            legal_due_days=point.legal_due_days,
            days_to_pay=point.days_to_pay,
            days_open_so_far=point.days_open_so_far,
            days_overdue=point.days_overdue,
            status=point.status,
            outstanding=point.outstanding,
            on_time=point.on_time,
            based_on=point.based_on_n,
        )
        for point in result.series
    ]


def _last_payment_on(book: Book, case_id: str) -> date | None:
    dates = [
        row.paid_on
        for row in book.payment_rows
        if row.case_id == case_id and row.voided_at is None
    ]
    return max(dates) if dates else None


def _invoices_contract(book: Book, customer_id: str) -> list[CustomerInvoice]:
    points = {point.case_id: point for point in _stats_for(book, customer_id).series}
    invoices: list[CustomerInvoice] = []
    for case_id in book.case_ids(customer_id):
        row = book.case_rows[case_id]
        point = points.get(case_id)
        invoices.append(
            CustomerInvoice(
                case_id=case_id,
                invoice_no=row.invoice_no,
                invoice_date=row.invoice_date,
                accepted_amount=row.accepted_amount,
                accepted_on=point.accepted_on if point else None,
                due_date=point.due_date if point else None,
                days_overdue=point.days_overdue if point else None,
                days_to_pay=point.days_to_pay if point else None,
                days_open_so_far=point.days_open_so_far if point else None,
                outstanding=point.outstanding if point else row.accepted_amount,
                status=point.status if point else "NO_ENGINE_EVALUATION",
                on_time=point.on_time if point else None,
                last_payment_on=_last_payment_on(book, case_id),
                active_track=_track_contract(case_id, book.tracks.get(case_id)),
            )
        )
    invoices.sort(key=lambda invoice: (invoice.invoice_date, invoice.invoice_no, invoice.case_id))
    return invoices


def _payments_contract(book: Book, case_ids: Sequence[str]) -> list[Payment]:
    wanted = set(case_ids)
    return [
        Payment(
            id=row.id,
            case_id=row.case_id,
            amount=row.amount,
            paid_on=row.paid_on,
            method=row.method,
            note=row.note,
            created_at=_aware(row.created_at) or _now(),
            voided_at=_aware(row.voided_at),
        )
        for row in book.payment_rows
        if row.case_id in wanted
    ]


def _timeline(session, case_ids: Sequence[str], *, limit: int = MAX_TIMELINE) -> list[ContractEvent]:
    """Every audit event on this customer's invoices, newest first."""
    if not case_ids:
        return []
    rows = session.exec(
        select(EventRow)
        .where(EventRow.case_id.in_(list(case_ids)))
        .order_by(EventRow.created_at.desc(), EventRow.seq.desc())
        .limit(limit)
    ).all()
    return [case_routes._event_contract(row) for row in rows]


def _buyer_cost_summary(book: Book, case_ids: Sequence[str]) -> BuyerCostSummary:
    """The engine's three buyer-cost lines, added up per line and kept apart."""
    permanent = Decimal("0.00")
    deferral = Decimal("0.00")
    permanent_cases: list[str] = []
    deferral_cases: list[str] = []
    disclosure_cases: list[str] = []
    disclosure_items: list[str] = []
    missing: list[str] = []

    for case_id in case_ids:
        evaluation_row = book.evaluations.get(case_id)
        if evaluation_row is None:
            missing.append(case_id)
            continue
        evaluation = CaseEvaluationResponse.model_validate(evaluation_row.response_json)
        block = evaluation.buyer_cost
        if block is None:
            missing.append(case_id)
            continue
        permanent += block.permanent_loss.interest_non_deductible
        permanent_cases.append(case_id)
        if block.deferral.applies and block.deferral.deferral_cost is not None:
            deferral += block.deferral.deferral_cost
            deferral_cases.append(case_id)
        if block.disclosure_flags:
            disclosure_cases.append(case_id)
            for flag in block.disclosure_flags:
                if flag.text not in disclosure_items:
                    disclosure_items.append(flag.text)

    missing_note = (
        f" {len(missing)} invoice(s) have no buyer-cost block (the gate blocked them "
        "or no due date was computed)."
        if missing
        else ""
    )
    return BuyerCostSummary(
        as_of=book.as_of,
        lines=[
            BuyerCostLine(
                id="PERMANENT_LOSS",
                label="Interest the buyer cannot deduct (permanent loss)",
                amount=q2(permanent),
                case_count=len(permanent_cases),
                case_ids=permanent_cases,
                note=(
                    "Interest accrued on the late payment, from the engine's own "
                    "buyer-cost block." + missing_note
                ),
            ),
            BuyerCostLine(
                id="DEFERRAL",
                label="Tax-timing deferral cost",
                amount=q2(deferral) if deferral_cases else None,
                case_count=len(deferral_cases),
                case_ids=deferral_cases,
                note=(
                    "Cost of the buyer holding the deduction past a 31 March "
                    "checkpoint, from the engine's own inputs."
                    if deferral_cases
                    else "No invoice reaches a 31 March checkpoint with the engine's "
                    "current inputs."
                ),
            ),
            BuyerCostLine(
                id="DISCLOSURE",
                label="Disclosure the buyer has to make",
                amount=None,
                case_count=len(disclosure_cases),
                case_ids=disclosure_cases,
                items=disclosure_items,
                note=(
                    "Disclosure flags are not money, so this line carries no amount."
                    + missing_note
                ),
            ),
        ],
        note=BUYER_COST_NOTE,
    )


def _guidance_reason(book: Book, case_id: str) -> str:
    """Why this invoice has these actions, in the engine's own words where possible."""
    evaluation_row = book.evaluations.get(case_id)
    if evaluation_row is None:
        return "No engine evaluation is stored for this invoice yet."
    evaluation = CaseEvaluationResponse.model_validate(evaluation_row.response_json)
    limitation = evaluation.limitation
    if limitation is not None and limitation.status is not LimitationStatus.OK:
        return (
            f"The engine's limitation check reads {limitation.status.value} for this "
            "invoice, based on the dates you entered."
        )
    readiness = evaluation.evidence_readiness
    if readiness is not None and readiness.missing:
        return (
            f"The engine lists {len(readiness.missing)} piece(s) of evidence as "
            "missing for this invoice."
        )
    if readiness is not None:
        return (
            f"The engine's evidence readiness suggests stage {readiness.recommended_stage} "
            "for this invoice."
        )
    return "Taken from this invoice's current workflow state."


def _next_actions(book: Book, customer_id: str) -> list[SuggestedAction]:
    """Next steps for the customer's open invoices, from existing guidance only."""
    open_case_ids = [
        point.case_id
        for point in _stats_for(book, customer_id).series
        if point.outstanding > 0
    ]
    actions: list[SuggestedAction] = []
    for case_id in open_case_ids:
        track = book.tracks.get(case_id)
        state = TrackState(track.state) if track is not None else TrackState.NEW
        reason = _guidance_reason(book, case_id)
        row = book.case_rows[case_id]
        for action in available_actions(state, track.kind if track else None)[
            :MAX_ACTIONS_PER_CASE
        ]:
            if action == "view_events":
                continue
            actions.append(
                SuggestedAction(
                    case_id=case_id,
                    invoice_no=row.invoice_no,
                    action=action,
                    label=ACTION_LABELS.get(action, action.replace("_", " ")),
                    reason=reason,
                    source="WORKFLOW",
                )
            )
            if len(actions) >= MAX_ACTIONS:
                return actions
    return actions


def _suggestion_contract(item: dict[str, Any]) -> Suggestion:
    return Suggestion(
        a=item["a"],
        b=item["b"],
        kind=SuggestionKind(item["kind"]),
        similarity=_similarity(item["similarity"]),
        reason=item["reason"],
    )


def _profile(session, book: Book, customer_id: str) -> CustomerProfile:
    case_ids = book.case_ids(customer_id)
    group_id = book.group_of.get(customer_id)
    return CustomerProfile(
        customer=_customer_contract(book, customer_id),
        group=_group_row(book, group_id) if group_id else None,
        stats=_stats_contract(book, _stats_for(book, customer_id)),
        payments=_payments_contract(book, case_ids),
        suggestions=[
            _suggestion_contract(item)
            for item in book.suggestions
            if customer_id in (item.get("a"), item.get("b"))
        ],
        cases=[_case_summary(book, case_id) for case_id in case_ids],
        gstins=book.gstins.get(customer_id, []),
        series=_series_contract(book, customer_id),
        invoices=_invoices_contract(book, customer_id),
        timeline=_timeline(session, case_ids),
        buyer_cost_summary=_buyer_cost_summary(book, case_ids),
        suggested_next_actions=_next_actions(book, customer_id),
    )


# ------------------------------------------------------------ portfolio ----


def _month_end(day: date) -> date:
    return date(day.year, day.month, calendar.monthrange(day.year, day.month)[1])


def _collections_by_month(book: Book) -> list[ChartSeriesPoint]:
    """Payments the owner recorded, grouped by calendar month (a display grouping)."""
    buckets: dict[str, dict[str, Any]] = {}
    for row in book.payment_rows:
        if row.voided_at is not None:
            continue
        label = f"{row.paid_on.year}-{row.paid_on.month:02d}"
        bucket = buckets.setdefault(
            label,
            {
                "start": row.paid_on.replace(day=1),
                "end": _month_end(row.paid_on),
                "amount": Decimal("0.00"),
                "count": 0,
            },
        )
        bucket["amount"] = q2(bucket["amount"] + row.amount)
        bucket["count"] += 1
    return [
        ChartSeriesPoint(
            label=label,
            value=buckets[label]["amount"],
            count=buckets[label]["count"],
            period_start=buckets[label]["start"],
            period_end=buckets[label]["end"],
        )
        for label in sorted(buckets)
    ]


def _concentration_note(result: PortfolioInsightsResult) -> str:
    threshold = result.concentration.threshold_pct
    if result.concentration.reason == CONCENTRATION_NO_OUTSTANDING:
        return "No outstanding balance, so there is no concentration to describe."
    if result.concentration.reason == CONCENTRATION_BELOW_THRESHOLD:
        return (
            f"No customer holds {format(threshold, 'f')}% or more of the outstanding "
            "balance. This is a concentration fact, not a rating."
        )
    share = result.concentration.top_share_pct
    return (
        f"The largest customer holds {format(share, 'f') if share is not None else '?'}% "
        f"of the outstanding balance, at or above the {format(threshold, 'f')}% "
        "product threshold. This is a concentration fact from your own book, not a "
        "rating of that buyer."
    )


def _portfolio_contract(book: Book, result: PortfolioInsightsResult) -> PortfolioInsights:
    weeks = result.cash_in_estimate or ()
    cash_in_total = q2(sum((week.amount for week in weeks), Decimal("0.00"))) if weeks else None
    if result.cash_in_reason == CASH_IN_NO_HISTORY:
        cash_in_note = (
            "No customer has enough fully paid invoices for an estimate yet "
            "(AGENTS.md rule 25)."
        )
    elif cash_in_total is None:
        cash_in_note = (
            "The cash-in estimate is switched off in config (a product setting, not "
            "law)."
        )
    else:
        cash_in_note = (
            f"{CASH_IN_LABEL}. Sum of the weekly estimate in cash_in_weeks; an "
            "estimate, not a promise."
        )

    return PortfolioInsights(
        as_of=result.as_of,
        customer_count=result.customer_count,
        invoice_count=result.invoices_count,
        outstanding_total=result.outstanding,
        overdue_total=result.overdue_amount,
        paid_total=_paid_total(book, list(book.case_rows)),
        based_on=result.based_on_n,
        min_history=result.min_history,
        avg_days_to_pay=result.avg_days_to_pay,
        avg_days_to_pay_reason=_history_reason(result),
        on_time_pct=result.on_time_pct,
        on_time_pct_reason=_history_reason(result),
        cash_in_estimate=cash_in_total,
        cash_in_estimate_note=cash_in_note,
        top_customer_share_pct=result.concentration.top_share_pct,
        top_customer_id=result.concentration.top_customer_id,
        concentration_note=_concentration_note(result),
        outstanding_by_customer=[
            ChartSeriesPoint(
                label=share.customer_name or share.customer_id,
                value=share.outstanding,
                count=share.based_on_n,
            )
            for share in result.concentration.shares
        ],
        collections_by_month=_collections_by_month(book),
        interest_accrued_now=result.interest_accrued_now,
        paid_count=result.paid_count,
        median_days_to_pay=result.median_days_to_pay,
        worst_days_to_pay=result.worst_days_to_pay,
        on_time_count=result.on_time_count,
        on_time_text=(
            f"{result.on_time_count} of {result.paid_count} on time"
            if result.paid_count
            else None
        ),
        history_reason=_history_reason(result),
        concentration_flag=result.concentration.flagged,
        concentration_reason=result.concentration.reason,
        before_march=[
            BeforeMarchHint(
                customer_id=item.customer_id,
                customer_name=item.customer_name,
                case_id=item.case_id,
                invoice_no=item.invoice_no,
                outstanding=item.outstanding,
                next_march=item.next_march,
                note=item.note or BEFORE_MARCH_NOTE,
                based_on=item.based_on_n,
            )
            for item in result.before_march
        ],
        terms_flags=[
            TermsFlagHint(
                customer_id=flag.customer_id,
                customer_name=flag.customer_name,
                avg_days_to_pay=flag.avg_days_to_pay,
                credit_cap_days=flag.credit_cap_days,
                text=flag.text,
                based_on=flag.based_on_n,
            )
            for flag in result.terms_flags
        ],
        cash_in_weeks=[
            CashInWeekHint(
                iso_week=week.iso_week,
                week_start=week.week_start,
                amount=week.amount,
                invoice_count=week.invoice_count,
                based_on=week.based_on_n,
                label=week.label,
            )
            for week in weeks
        ],
        cash_in_reason=result.cash_in_reason,
        assumptions=list(result.assumptions),
    )


# ------------------------------------------------------------ read routes ----
# `/customers/suggestions` is declared before `/customers/{customer_id}` so the
# literal path wins the match.


@router.get("/customers", response_model=CustomerListResponse)
def list_customers(
    sort: CustomerSort = Query(
        default=CustomerSort.OUTSTANDING,
        description="outstanding | overdue | avg_days | name. Money and days sort largest first.",
    ),
    group: bool = Query(
        default=False,
        description="Collapse customers linked by the owner into one row with totals.",
    ),
) -> CustomerListResponse:
    """The owner's book, sorted, with the sample size beside every average.

    A row is descriptive: outstanding, overdue, accrued interest, payment timing
    and how many invoices stand behind it. There is no score and no comparison
    between buyers. With `group=true`, an owner-made group appears once, with
    summed totals and its members nested for expansion.
    """
    with session_scope() as session:
        book = _load_book(session)
        entries = _list_entries(book, grouped=group)
        entries.sort(key=lambda entry: _entry_sort_key(sort, entry))
        return CustomerListResponse(
            as_of=book.as_of,
            sort=sort,
            grouped=group,
            entries=entries,
            count=len(entries),
            min_history=book.config.min_history,
            note=HISTORY_NOTE,
        )


@router.get("/customers/suggestions", response_model=SuggestionListResponse)
def list_customer_suggestions() -> SuggestionListResponse:
    """Name-match suggestions for the book. Nothing is applied automatically.

    `ATTACH` suggests folding a provisional record into a PAN customer;
    `LINK_AS_GROUP` suggests linking two different PANs as a group. Different
    PANs are never merged, and a pair the owner dismissed is not suggested again.
    """
    settings = identity_settings(load_config())
    with session_scope() as session:
        found = customer_book.suggestions_for_book(
            session, threshold=settings.name_match_threshold
        )
    return SuggestionListResponse(
        suggestions=[
            _suggestion_contract(item)
            for item in found
        ],
        count=len(found),
        threshold=_similarity(settings.name_match_threshold),
        min_history=settings.min_history,
        note=(
            "Suggestions only. Attaching and grouping are your decisions, and both "
            "can be undone. The threshold is a product setting, not law."
        ),
    )


@router.get("/insights", response_model=PortfolioInsights)
def get_insights() -> PortfolioInsights:
    """Descriptive portfolio insights from `backend/insights/`.

    Totals, concentration, the next 31 March for open overdue invoices, customers
    whose observed timing exceeds the engine's credit cap, and the labelled
    cash-in estimate when it is switched on. No buyer is scored, ranked or
    predicted, and nothing is compared with another owner's book.
    """
    with session_scope() as session:
        book = _load_book(session)
        assert book.portfolio is not None
        return _portfolio_contract(book, book.portfolio)


@router.get("/customers/{customer_id}", response_model=CustomerProfile)
def get_customer(customer_id: str) -> CustomerProfile:
    """One customer: identity, group, full stats, invoices, payments and audit trail.

    Days to pay are measured from the engine's day of acceptance and "on time"
    means paid by the engine's legal due date, never the invoice date. The
    buyer-cost block keeps its three lines separate.
    """
    with session_scope() as session:
        if session.get(CustomerRowModel, customer_id) is None:
            raise _not_found("customer", customer_id)
        book = _load_book(session, with_suggestions=True)
        return _profile(session, book, customer_id)


# ------------------------------------------------------------- attach ----


def _audit_cases(
    session,
    case_ids: Iterable[str],
    *,
    event_type: str,
    payload: dict[str, Any],
    actor: str,
    at: datetime,
) -> list[str]:
    """One event per affected case: the case chain is the v4 audit anchor."""
    written = _dedup(case_ids)
    for case_id in written:
        audit.append_event(
            session,
            case_id=case_id,
            type=event_type,
            payload=payload,
            actor=actor,
            created_at=at,
        )
    return written


def _attach_response(
    book: Book, source_id: str, target_id: str, case_ids: list[str], gstins: list[str]
) -> CustomerAttachResponse:
    target = _customer_contract(book, target_id)
    identity_note = (
        " The target has no PAN yet, so the legal identity is still unconfirmed."
        if target.kind is CustomerKind.PROVISIONAL
        else ""
    )
    return CustomerAttachResponse(
        provisional=_customer_contract(book, source_id),
        target=target,
        case_ids=case_ids,
        gstins=gstins,
        audited_case_ids=_dedup(case_ids + book.case_ids(target_id)),
        detach_with=f"POST /api/v1/customers/{target_id}/detach",
        note=(
            "Attached, not merged: the invoices now sit under the target customer "
            "and the provisional record is kept so this can be undone with detach."
            + identity_note
        ),
    )


@router.post("/customers/{customer_id}/attach", response_model=CustomerAttachResponse)
def attach_customer(
    customer_id: str,
    payload: CustomerAttachRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> CustomerAttachResponse:
    """Fold a PROVISIONAL customer's invoices into another customer.

    Same-PAN registrations already group automatically. This is the owner
    confirming that a name-only or unformatted record is the same buyer. A
    customer that already has its own PAN is refused: different PANs are never
    merged, and the two can be linked as a group instead. The provisional row is
    kept with no invoices, which is what makes `detach` an exact undo.
    """
    key = _require_key(idempotency_key)
    digest = idempotency.hash_request(
        {"customer_id": customer_id, "target_customer_id": payload.target_customer_id}
    )

    with session_scope() as session:
        source = session.get(CustomerRowModel, customer_id)
        if source is None:
            raise _not_found("customer", customer_id)
        target = session.get(CustomerRowModel, payload.target_customer_id)
        if target is None:
            raise _not_found("customer", payload.target_customer_id)

        existing = idempotency.lookup(session, key=key, route=ROUTE_ATTACH)
        if existing is not None:
            if existing.request_hash != digest:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "This Idempotency-Key was already used for a different attach. "
                        "Use a new key for a different action."
                    ),
                )
            return CustomerAttachResponse.model_validate(existing.response_json)

        if source.id == target.id:
            raise HTTPException(
                status_code=422, detail="A customer cannot be attached to itself."
            )
        if source.kind == CustomerKind.PAN.value:
            raise HTTPException(
                status_code=409,
                detail=(
                    "This customer already has its own PAN. Different PANs are never "
                    "merged; link the two customers as a group instead."
                ),
            )

        now = _now()
        case_rows = session.exec(
            select(CaseRow).where(CaseRow.customer_id == source.id)
        ).all()
        links = session.exec(
            select(CustomerGstin).where(CustomerGstin.customer_id == source.id)
        ).all()
        moved_cases = [row.id for row in case_rows]
        moved_gstins = [link.gstin for link in links]
        target_case_ids = [
            row.id
            for row in session.exec(
                select(CaseRow).where(CaseRow.customer_id == target.id)
            ).all()
        ]

        if not moved_cases and not moved_gstins:
            # Nothing to move: report it rather than inventing an audit event.
            before = _load_book(session)
            body = CustomerAttachResponse(
                provisional=_customer_contract(before, source.id),
                target=_customer_contract(before, target.id),
                case_ids=[],
                gstins=[],
                audited_case_ids=[],
                detach_with=f"POST /api/v1/customers/{target.id}/detach",
                note="Nothing was attached: this customer has no invoices or GSTINs.",
            )
            idempotency.store(
                session,
                key=key,
                route=ROUTE_ATTACH,
                request_hash=digest,
                response=body.model_dump(mode="json"),
            )
            return body

        for row in case_rows:
            row.customer_id = target.id
            session.add(row)
        for link in links:
            link.customer_id = target.id
            session.add(link)
        session.flush()

        audited = _audit_cases(
            session,
            moved_cases + target_case_ids,
            event_type=CUSTOMER_ATTACH,
            payload={
                "from_customer_id": source.id,
                "to_customer_id": target.id,
                "case_ids": sorted(moved_cases),
                "gstins": sorted(moved_gstins),
                "source": "api.customers.attach",
            },
            actor="USER",
            at=now,
        )

        after = _load_book(session)
        body = _attach_response(
            after, source.id, target.id, sorted(moved_cases), sorted(moved_gstins)
        )
        body.audited_case_ids = audited
        idempotency.store(
            session,
            key=key,
            route=ROUTE_ATTACH,
            request_hash=digest,
            response=body.model_dump(mode="json"),
        )
        return body


def _latest_attach_event(session, case_id: str, to_customer_id: str) -> EventRow | None:
    """The newest `customer.attach` on this case that moved it to this customer."""
    rows = session.exec(
        select(EventRow)
        .where(EventRow.case_id == case_id, EventRow.type == CUSTOMER_ATTACH)
        .order_by(EventRow.seq.desc())
    ).all()
    for row in rows:
        if (row.payload_json or {}).get("to_customer_id") == to_customer_id:
            return row
    return None


@router.post("/customers/{customer_id}/detach", response_model=CustomerDetachResponse)
def detach_customer(
    customer_id: str,
    payload: CustomerDetachRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> CustomerDetachResponse:
    """Separate invoices or a GSTIN from a customer. The undo for `attach`.

    When the invoice was moved by an `attach`, the detach restores the exact
    customer it came from. Otherwise the invoice gets its own provisional record,
    resolved from its own buyer details. Either way the move is audited on the
    invoice's chain and can be reversed by attaching again.
    """
    key = _require_key(idempotency_key)
    if not payload.case_ids and not payload.gstin:
        raise HTTPException(
            status_code=422,
            detail="Name at least one case_id or a GSTIN to detach.",
        )
    case_ids = _dedup(payload.case_ids)
    digest = idempotency.hash_request(
        {
            "customer_id": customer_id,
            "case_ids": sorted(case_ids),
            "gstin": (payload.gstin or "").strip().upper() or None,
        }
    )

    with session_scope() as session:
        customer = session.get(CustomerRowModel, customer_id)
        if customer is None:
            raise _not_found("customer", customer_id)

        existing = idempotency.lookup(session, key=key, route=ROUTE_DETACH)
        if existing is not None:
            if existing.request_hash != digest:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "This Idempotency-Key was already used for a different detach. "
                        "Use a new key for a different action."
                    ),
                )
            return CustomerDetachResponse.model_validate(existing.response_json)

        now = _now()
        moved_to: list[str] = []
        audited: list[str] = []
        moved_cases: list[str] = []
        moved_gstins: list[str] = []

        for case_id in case_ids:
            case = session.get(CaseRow, case_id)
            if case is None:
                raise _not_found("case", case_id)
            if case.customer_id != customer.id:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"Invoice {case.invoice_no} is not attached to "
                        f"{customer.display_name}; nothing to detach."
                    ),
                )

            previous = _latest_attach_event(session, case_id, customer.id)
            previous_id = (previous.payload_json or {}).get("from_customer_id") if previous else None
            if previous_id and session.get(CustomerRowModel, previous_id) is not None:
                case.customer_id = previous_id
                session.add(case)
                session.flush()
                destination = previous_id
                restored = True
            else:
                case.customer_id = None
                session.add(case)
                session.flush()
                resolution = customer_book.attach_case_to_customer(
                    session, case, at=now, source="api.customers.detach", actor="USER"
                )
                destination = resolution.customer_id
                restored = False

            audited.extend(
                _audit_cases(
                    session,
                    [case_id],
                    event_type=CUSTOMER_DETACH,
                    payload={
                        "from_customer_id": customer.id,
                        "to_customer_id": destination,
                        "restored": restored,
                        "source": "api.customers.detach",
                        "reason": (payload.reason or None),
                    },
                    actor="USER",
                    at=now,
                )
            )
            moved_cases.append(case_id)
            if destination not in moved_to:
                moved_to.append(destination)

        if payload.gstin:
            value = customer_book.normalize_gstin(payload.gstin)
            link = session.get(CustomerGstin, value) if value else None
            if link is None:
                raise HTTPException(
                    status_code=422,
                    detail=f"No customer holds the GSTIN {payload.gstin!r}.",
                )
            if link.customer_id != customer.id:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"The GSTIN {value} is attached to another customer; nothing "
                        "to detach here."
                    ),
                )
            previous_id = None
            for case_id in book_case_ids(session, customer.id):
                event = _latest_attach_event(session, case_id, customer.id)
                if event is not None and value in (event.payload_json or {}).get("gstins", []):
                    previous_id = (event.payload_json or {}).get("from_customer_id")
                    break
            if previous_id and session.get(CustomerRowModel, previous_id) is not None:
                link.customer_id = previous_id
                session.add(link)
                session.flush()
                moved_to.append(previous_id)
            else:
                customer_book.detach_gstin(session, gstin=value, actor="USER", at=now)
            moved_gstins.append(value)
            audited.extend(
                _audit_cases(
                    session,
                    book_case_ids(session, previous_id or customer.id),
                    event_type=CUSTOMER_DETACH,
                    payload={
                        "from_customer_id": customer.id,
                        "gstin": value,
                        "restored": bool(previous_id),
                        "source": "api.customers.detach",
                    },
                    actor="USER",
                    at=now,
                )
            )

        after = _load_book(session)
        body = CustomerDetachResponse(
            customer=_customer_contract(after, customer.id),
            case_ids=sorted(moved_cases),
            gstins=sorted(moved_gstins),
            moved_to=_dedup(moved_to),
            audited_case_ids=_dedup(audited),
            note=(
                "Detached. Re-attaching the provisional record reverses this, and "
                "every step is on the invoice's audit trail."
            ),
        )
        idempotency.store(
            session,
            key=key,
            route=ROUTE_DETACH,
            request_hash=digest,
            response=body.model_dump(mode="json"),
        )
        return body


def book_case_ids(session, customer_id: str) -> list[str]:
    """Case ids attached to a customer, oldest first."""
    return customer_book.case_ids_for_customer(session, customer_id)


# --------------------------------------------------------------- groups ----


def _group_or_404(session, group_id: str) -> CustomerGroup:
    group = session.get(CustomerGroup, group_id)
    if group is None:
        raise _not_found("customer group", group_id)
    return group


@router.post("/customer-groups", response_model=CustomerGroupRow, status_code=201)
def create_customer_group(
    payload: CustomerGroupCreateRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> CustomerGroupRow:
    """Link customers that are not the same PAN. It is a label, not a merge.

    The group is descriptive: every invoice keeps its own customer and its own
    legal entity. Membership is one group per customer, and a member can be
    removed at any time.
    """
    key = _require_key(idempotency_key)
    body = {
        "label": payload.label,
        "customer_ids": sorted(_dedup(payload.customer_ids)),
    }
    digest = idempotency.hash_request(body)

    with session_scope() as session:
        existing = idempotency.lookup(session, key=key, route=ROUTE_GROUP_CREATE)
        if existing is not None:
            if existing.request_hash != digest:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "This Idempotency-Key was already used for a different group. "
                        "Use a new key for a different action."
                    ),
                )
            return CustomerGroupRow.model_validate(existing.response_json)

        if not payload.label.strip():
            raise HTTPException(status_code=422, detail="A customer group needs a label.")
        ids = _dedup(payload.customer_ids)
        if not ids:
            raise HTTPException(
                status_code=422, detail="A customer group needs at least one customer."
            )
        for customer_id in ids:
            if session.get(CustomerRowModel, customer_id) is None:
                raise _not_found("customer", customer_id)

        try:
            group = customer_book.create_group(
                session, label=payload.label, customer_ids=ids, actor="USER", at=_now()
            )
        except ValueError as exc:  # already in another group, empty label
            raise HTTPException(status_code=409, detail=str(exc)) from exc

        book = _load_book(session)
        row = _group_row(book, group.id)
        assert row is not None
        idempotency.store(
            session,
            key=key,
            route=ROUTE_GROUP_CREATE,
            request_hash=digest,
            response=row.model_dump(mode="json"),
        )
        return row


def _membership_response(
    session, group_id: str, customer_id: str, *, changed: bool
) -> CustomerGroupMembershipResponse:
    book = _load_book(session)
    row = _group_row(book, group_id)
    if row is None:
        raise _not_found("customer group", group_id)
    return CustomerGroupMembershipResponse(
        group=row,
        customer_id=customer_id,
        changed=changed,
        note=(
            "Membership changed and was audited."
            if changed
            else "Nothing changed: this membership was already in that state."
        ),
    )


@router.post(
    "/customer-groups/{group_id}/members", response_model=CustomerGroupMembershipResponse
)
def add_group_member(
    group_id: str,
    payload: CustomerGroupMemberRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> CustomerGroupMembershipResponse:
    """Add one customer to an existing owner-made group."""
    key = _require_key(idempotency_key)
    digest = idempotency.hash_request(
        {"group_id": group_id, "customer_id": payload.customer_id, "action": "add"}
    )

    with session_scope() as session:
        _group_or_404(session, group_id)
        if session.get(CustomerRowModel, payload.customer_id) is None:
            raise _not_found("customer", payload.customer_id)

        existing = idempotency.lookup(session, key=key, route=ROUTE_GROUP_ADD)
        if existing is not None:
            if existing.request_hash != digest:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "This Idempotency-Key was already used for a different member. "
                        "Use a new key for a different action."
                    ),
                )
            return CustomerGroupMembershipResponse.model_validate(existing.response_json)

        already = session.get(CustomerGroupMember, (group_id, payload.customer_id))
        try:
            customer_book.link_group(
                session,
                group_id=group_id,
                customer_id=payload.customer_id,
                actor="USER",
                at=_now(),
            )
        except LookupError as exc:
            raise _not_found("customer group", group_id) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

        response = _membership_response(
            session, group_id, payload.customer_id, changed=already is None
        )
        idempotency.store(
            session,
            key=key,
            route=ROUTE_GROUP_ADD,
            request_hash=digest,
            response=response.model_dump(mode="json"),
        )
        return response


@router.delete(
    "/customer-groups/{group_id}/members/{customer_id}",
    response_model=CustomerGroupMembershipResponse,
)
def remove_group_member(
    group_id: str,
    customer_id: str,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> CustomerGroupMembershipResponse:
    """Remove one customer from a group. Audited, and repeatable without effect."""
    key = _require_key(idempotency_key)
    digest = idempotency.hash_request(
        {"group_id": group_id, "customer_id": customer_id, "action": "remove"}
    )

    with session_scope() as session:
        _group_or_404(session, group_id)
        if session.get(CustomerRowModel, customer_id) is None:
            raise _not_found("customer", customer_id)

        existing = idempotency.lookup(session, key=key, route=ROUTE_GROUP_REMOVE)
        if existing is not None:
            if existing.request_hash != digest:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "This Idempotency-Key was already used for a different member. "
                        "Use a new key for a different action."
                    ),
                )
            return CustomerGroupMembershipResponse.model_validate(existing.response_json)

        try:
            changed = customer_book.unlink_group(
                session,
                group_id=group_id,
                customer_id=customer_id,
                actor="USER",
                at=_now(),
            )
        except LookupError as exc:
            raise _not_found("customer group", group_id) from exc

        response = _membership_response(session, group_id, customer_id, changed=changed)
        idempotency.store(
            session,
            key=key,
            route=ROUTE_GROUP_REMOVE,
            request_hash=digest,
            response=response.model_dump(mode="json"),
        )
        return response


# ------------------------------------------------------------ dismissal ----


@router.post(
    "/customers/suggestions/dismiss", response_model=SuggestionDismissResponse
)
def dismiss_customer_suggestion(
    payload: SuggestionDismissRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> SuggestionDismissResponse:
    """Record that two customers are not the same buyer, so it is not suggested again.

    The pair stays dismissed until it is undone; nothing is merged and no invoice
    moves. The dismissal is written to both customers' case chains.
    """
    key = _require_key(idempotency_key)
    digest = idempotency.hash_request({"a": payload.a, "b": payload.b})

    with session_scope() as session:
        for customer_id in (payload.a, payload.b):
            if session.get(CustomerRowModel, customer_id) is None:
                raise _not_found("customer", customer_id)

        existing = idempotency.lookup(session, key=key, route=ROUTE_DISMISS)
        if existing is not None:
            if existing.request_hash != digest:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "This Idempotency-Key was already used for a different pair. "
                        "Use a new key for a different action."
                    ),
                )
            return SuggestionDismissResponse.model_validate(existing.response_json)

        try:
            row = customer_book.dismiss_merge(
                session, customer_a=payload.a, customer_b=payload.b, actor="USER", at=_now()
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        response = SuggestionDismissResponse(
            a=row.customer_a,
            b=row.customer_b,
            dismissed=True,
            dismissed_at=_aware(row.dismissed_at),
            note=(
                "Dismissed: this pair will not be suggested again. Nothing was "
                "merged, and the dismissal is recorded on both customers' cases."
            ),
        )
        idempotency.store(
            session,
            key=key,
            route=ROUTE_DISMISS,
            request_hash=digest,
            response=response.model_dump(mode="json"),
        )
        return response


__all__ = ["router", "Book", "HISTORY_NOTE", "GROUP_AVERAGE_NOTE"]
