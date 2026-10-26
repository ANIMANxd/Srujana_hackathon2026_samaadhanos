"""SQLModel tables for the v4 two-option model (architecture_v4 section 4) and
the v5 customer book.

Money is TEXT. `DecimalText` is the only column type money may use: it rejects
`float` loudly on write and returns `Decimal` on read, so a rupee amount can
never round-trip through a binary float.

The schema stays Postgres-compatible: no SQLite-only types, no REAL, no
autoincrement-specific tricks. The one SQLite-only feature is the partial unique
index on `tracks`, which Postgres supports with the same definition.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Column,
    Index,
    Text,
    TypeDecorator,
    UniqueConstraint,
    text,
)
from sqlmodel import Field, SQLModel


class DecimalText(TypeDecorator):
    """A decimal-as-TEXT column: `Decimal` in Python, decimal string in SQLite."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, bool) or isinstance(value, float):
            raise TypeError(
                "money must be Decimal or a decimal string, never float "
                f"(got {type(value).__name__})"
            )
        decimal_value = value if isinstance(value, Decimal) else Decimal(str(value))
        if not decimal_value.is_finite():
            raise ValueError(f"money must be finite, got {decimal_value!r}")
        # `format(..., 'f')` keeps the scale ("1250000.00" stays two dp) and never
        # switches to scientific notation.
        return format(decimal_value, "f")

    def process_result_value(self, value: Any, dialect: Any) -> Decimal | None:
        if value is None:
            return None
        return Decimal(str(value))


def utc_now() -> datetime:
    from datetime import UTC

    return datetime.now(UTC)


def iso_utc(value: datetime) -> str:
    """The one timestamp format used inside event hashes.

    `events.created_at` stores exactly this string, because the audit hash covers
    it: a datetime round-trip through SQLite loses tzinfo and would make the
    chain silently unverifiable.
    """
    from datetime import UTC

    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


GENESIS_HASH = "0" * 64


def canonical_json(payload: Any) -> str:
    """Canonical JSON for hashing: sorted keys, no whitespace, UTF-8 text.

    Callers must pass JSON-safe values (money as strings). A `Decimal` anywhere
    in a payload raises here rather than being silently coerced.
    """
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


# ---------------------------------------------------------------- tables ----


class Customer(SQLModel, table=True):
    """One buyer the supplier sells to, as seen in the owner's own invoices.

    Identity is a PAN where the data gives one: two GSTINs that carry the same
    PAN are the same legal entity and group automatically (AGENTS.md rule 23).
    Without a PAN the row is PROVISIONAL and holds one GSTIN, or a normalised
    name when the invoice has no GSTIN at all. Different PANs are never merged
    here; the owner links them into a `CustomerGroup` instead.

    `pan` is unique only for PAN-kind rows, via a partial index. Provisional
    rows keep `pan` NULL, so any number of them can coexist.
    """

    __tablename__ = "customers"
    __table_args__ = (
        CheckConstraint("kind IN ('PAN', 'PROVISIONAL')", name="ck_customers_kind"),
        CheckConstraint(
            "(kind = 'PAN' AND pan IS NOT NULL) OR (kind = 'PROVISIONAL' AND pan IS NULL)",
            name="ck_customers_pan_kind",
        ),
        # Partial unique index on SQLite (the demo database). On Postgres the
        # same Index renders as a plain unique index over `pan`; equivalent,
        # because a PROVISIONAL row always has `pan` NULL and Postgres allows
        # many NULLs in a unique index.
        Index("ux_customers_pan", "pan", unique=True, sqlite_where=text("kind = 'PAN'")),
    )

    id: str = Field(primary_key=True, max_length=26)
    kind: str = Field(max_length=11, description="PAN or PROVISIONAL")
    pan: str | None = Field(default=None, max_length=10)
    display_name: str
    normalized_name: str = Field(default="", index=True)
    created_at: datetime = Field(default_factory=utc_now)


class CustomerGstin(SQLModel, table=True):
    """A GSTIN seen on an invoice, attached to exactly one customer."""

    __tablename__ = "customer_gstins"

    gstin: str = Field(primary_key=True, max_length=20)
    customer_id: str = Field(foreign_key="customers.id", index=True)
    state_code: str = Field(default="", max_length=2)
    first_seen_at: datetime = Field(default_factory=utc_now)


class CustomerGroup(SQLModel, table=True):
    """An owner-made link between customers that are not the same PAN.

    A group is descriptive only: it never changes a legal calculation, and every
    invoice keeps its own customer and its own legal entity (AGENTS.md rule 23).
    """

    __tablename__ = "customer_groups"

    id: str = Field(primary_key=True, max_length=26)
    label: str
    created_by: str = Field(default="owner")
    created_at: datetime = Field(default_factory=utc_now)


class CustomerGroupMember(SQLModel, table=True):
    """Group membership. The unique customer_id keeps a customer in one group."""

    __tablename__ = "customer_group_members"
    __table_args__ = (
        UniqueConstraint("customer_id", name="ux_customer_group_members_customer"),
    )

    group_id: str = Field(primary_key=True, foreign_key="customer_groups.id")
    customer_id: str = Field(primary_key=True, foreign_key="customers.id", index=True)


class MergeDismissal(SQLModel, table=True):
    """A merge suggestion the owner dismissed, so it is not suggested again.

    The pair is stored in ascending id order, which makes a duplicate dismissal
    of (A, B) and (B, A) the same row.
    """

    __tablename__ = "merge_dismissals"
    __table_args__ = (
        CheckConstraint("customer_a < customer_b", name="ck_merge_dismissals_order"),
    )

    customer_a: str = Field(primary_key=True, foreign_key="customers.id", max_length=26)
    customer_b: str = Field(primary_key=True, foreign_key="customers.id", max_length=26)
    dismissed_at: datetime = Field(default_factory=utc_now)


class Payment(SQLModel, table=True):
    """Money the buyer actually paid, recorded by the owner.

    Payments are voided, never deleted: `voided_at` plus a `payment.voided`
    audit event keeps the history explainable. `amount` is TEXT decimal.
    """

    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint(
            "method IN ('bank', 'upi', 'cheque', 'cash', 'other')",
            name="ck_payments_method",
        ),
        Index("ix_payments_case_paid_on", "case_id", "paid_on"),
    )

    id: str = Field(primary_key=True, max_length=26)
    case_id: str = Field(foreign_key="cases.id", index=True)
    amount: Decimal = Field(sa_column=Column(DecimalText, nullable=False))
    paid_on: date
    method: str = Field(max_length=10)
    note: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    voided_at: datetime | None = None


class Case(SQLModel, table=True):
    """The engine input stored verbatim, so any stored result is reproducible."""

    __tablename__ = "cases"

    id: str = Field(primary_key=True, max_length=26)
    supplier_ref: str
    customer_id: str | None = Field(default=None, foreign_key="customers.id", index=True)
    buyer_gstin: str | None = None
    invoice_no: str
    invoice_date: date
    accepted_amount: Decimal = Field(sa_column=Column(DecimalText, nullable=False))
    delivery_date: date | None = None
    input_json: dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))
    engine_version: str = "1.0"
    config_version: str = "1.0"
    created_at: datetime = Field(default_factory=utc_now)


class Evaluation(SQLModel, table=True):
    """An immutable engine snapshot for a case at a point in time."""

    __tablename__ = "evaluations"
    __table_args__ = (Index("ix_evaluations_case_as_of", "case_id", "as_of"),)

    id: str = Field(primary_key=True, max_length=26)
    case_id: str = Field(foreign_key="cases.id", index=True)
    as_of: date
    response_json: dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))
    engine_version: str = "1.0"
    config_hash: str = ""
    created_at: datetime = Field(default_factory=utc_now)


class Track(SQLModel, table=True):
    """One active track per case, enforced by a partial unique index.

    The index is the database half of the track-locking rules in
    `docs/state-machines.md` section 3: a second open track for the same case is
    rejected even if the application guard is bypassed.
    """

    __tablename__ = "tracks"
    __table_args__ = (
        Index(
            "ux_tracks_one_active_per_case",
            "case_id",
            unique=True,
            sqlite_where=text("closed_at IS NULL"),
        ),
    )

    id: str = Field(primary_key=True, max_length=26)
    case_id: str = Field(foreign_key="cases.id", index=True)
    kind: str = Field(description="FINANCING or RECOVERY")
    state: str
    version: int = Field(default=1, description="Optimistic lock; clients send If-Match.")
    created_at: datetime = Field(default_factory=utc_now)
    closed_at: datetime | None = None


class FinancingRequest(SQLModel, table=True):
    """The financing terms for a track. One row per track (`track_id` is the key)."""

    __tablename__ = "financing_requests"

    track_id: str = Field(primary_key=True, foreign_key="tracks.id", max_length=26)
    accepted_amount: Decimal = Field(sa_column=Column(DecimalText, nullable=False))
    tenor_days: int
    due_date: date
    buyer_acceptance_status: str = "NOT_REQUESTED"
    selected_bid_id: str | None = None
    esign_session_id: str | None = None
    disbursement_ref: str | None = None


class Bid(SQLModel, table=True):
    """A financier bid. Aliases are fictional only (golden rule 17).

    `discount`, `fee` and `net_amount` are computed by `backend/finance/`, never
    by the mock provider, so a mock cannot introduce maths bugs.
    """

    __tablename__ = "bids"
    __table_args__ = (Index("ix_bids_track_status", "track_id", "status"),)

    id: str = Field(primary_key=True, max_length=40)
    track_id: str = Field(foreign_key="tracks.id")
    financier_alias: str
    annual_rate: Decimal = Field(sa_column=Column(DecimalText, nullable=False))
    discount: Decimal = Field(sa_column=Column(DecimalText, nullable=False))
    fee: Decimal = Field(sa_column=Column(DecimalText, nullable=False))
    net_amount: Decimal = Field(sa_column=Column(DecimalText, nullable=False))
    valid_until: datetime
    status: str = "AVAILABLE"


class Event(SQLModel, table=True):
    """Append-only, hash-chained audit event (architecture_v4 section 4).

    `seq` is per case, so a case's chain is (case_id, seq) ordered. The primary
    key is composite for the same reason: it makes a duplicate seq impossible.

    `created_at` is stored as an ISO-8601 UTC string, not a datetime, because the
    hash covers it verbatim (see `iso_utc`).
    """

    __tablename__ = "events"
    __table_args__ = (Index("ix_events_case_seq", "case_id", "seq"),)

    case_id: str = Field(primary_key=True, foreign_key="cases.id")
    seq: int = Field(primary_key=True)
    track_id: str | None = None
    type: str
    payload_json: dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))
    actor: str = Field(description="USER, SYSTEM or PROVIDER_MOCK")
    created_at: str = Field(description="ISO-8601 UTC, e.g. 2026-10-25T09:12:04Z")
    prev_hash: str = Field(max_length=64)
    hash: str = Field(max_length=64)


class IdempotencyKey(SQLModel, table=True):
    """A recorded mutation, so a replay returns the first response and a body that
    changed under the same key is a conflict (409), never a second write."""

    __tablename__ = "idempotency_keys"
    __table_args__ = (UniqueConstraint("key", "route", name="ux_idempotency_key_route"),)

    id: int | None = Field(default=None, primary_key=True)
    key: str = Field(index=True, max_length=200)
    route: str
    request_hash: str = Field(max_length=64)
    response_json: dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))
    created_at: datetime = Field(default_factory=utc_now)


class WebhookInbox(SQLModel, table=True):
    """Every verified provider delivery, deduplicated by `provider_event_id`.

    A duplicate is recorded and returns 200 with no side effects; an event that is
    not valid for the current state is stored and **parked**, then retried after the
    next successful transition on the same track (`docs/webhooks.md`).

    The body is stored because a parked event has to be applied later, and
    re-fetching it is not possible. Only verified deliveries are stored: an
    unverified body is attacker-controlled data and never enters the inbox.
    """

    __tablename__ = "webhook_inbox"
    __table_args__ = (Index("ix_webhook_inbox_track_outcome", "track_id", "outcome"),)

    provider_event_id: str = Field(primary_key=True, max_length=80)
    provider: str
    case_id: str | None = Field(default=None, index=True)
    track_id: str | None = None
    payload_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    received_at: datetime = Field(default_factory=utc_now)
    signature_ok: bool
    processed_at: datetime | None = None
    outcome: str = Field(default="PENDING", description="APPLIED, DUPLICATE, PARKED or REJECTED")


# Tables in dependency order, for `create_all` and for seeding diagnostics.
ALL_TABLES: tuple[type[SQLModel], ...] = (
    Customer,
    CustomerGstin,
    CustomerGroup,
    CustomerGroupMember,
    MergeDismissal,
    Case,
    Payment,
    Evaluation,
    Track,
    FinancingRequest,
    Bid,
    Event,
    IdempotencyKey,
    WebhookInbox,
)
