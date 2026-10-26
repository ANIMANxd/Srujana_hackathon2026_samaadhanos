"""The v5 customer book: identity resolution, groups, dismissals and payments.

Boundaries (AGENTS.md rules 22-26):

- Everything here is **descriptive**. A customer is a grouping of the owner's
  own invoices, not a score, rank or prediction about the buyer.
- Two GSTINs carrying the same PAN are the same legal entity and group
  automatically. Different PANs are **never** merged: the owner may link them
  into a `CustomerGroup`, and legal calculations stay per invoice.
- A buyer with no usable GSTIN becomes a PROVISIONAL customer: by GSTIN when
  there is one, by normalised name when there is not. Similar names are not
  merged automatically.
- Every write that changes the book appends a `customer.*` or `payment.*`
  event to the **existing** hash-chained case log. A customer always comes from
  at least one case, so the affected cases are the audit anchors. A group or a
  dismissal writes one event per affected case.
- Payments are voided, never deleted. Group membership and a dismissal can be
  undone; that undo is itself audited.

This module computes no legal number and never touches `backend/engine/` or
`backend/finance/`. It records what the owner entered; `backend/insights/` is
where descriptive statistics are derived from it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Iterable

from sqlalchemy.orm import Session
from sqlmodel import select

from backend.insights.identity import (
    Suggestion,
    CustomerRecord as IdentityCustomerRecord,
    normalize_name,
    pan_from_gstin,
    resolve as resolve_identity,
    suggestions as identity_suggestions,
)
from backend.store import audit
from backend.store.ids import new_ulid
from backend.store.models import (
    Case,
    Customer,
    CustomerGroup,
    CustomerGroupMember,
    CustomerGstin,
    MergeDismissal,
    Payment,
    utc_now,
)

PAYMENT_METHODS: tuple[str, ...] = ("bank", "upi", "cheque", "cash", "other")

# Event types written into the existing hash-chained case log.
CUSTOMER_CREATED = "customer.created"
CUSTOMER_ATTACHED = "customer.attached"
CUSTOMER_GSTIN_ATTACHED = "customer.gstin_attached"
CUSTOMER_GSTIN_DETACHED = "customer.gstin_detached"
CUSTOMER_GROUP_CREATED = "customer.group_created"
CUSTOMER_GROUP_LINKED = "customer.group_linked"
CUSTOMER_GROUP_UNLINKED = "customer.group_unlinked"
CUSTOMER_MERGE_DISMISSED = "customer.merge_dismissed"
CUSTOMER_MERGE_DISMISSAL_UNDONE = "customer.merge_dismissal_undone"
PAYMENT_RECORDED = "payment.recorded"
PAYMENT_VOIDED = "payment.voided"

_TWO_PLACES = Decimal("0.01")


# ------------------------------------------------------------- identity ----


def clean_name(name: str | None) -> str:
    """Trim and collapse whitespace, keeping the owner's capitalisation."""
    if not isinstance(name, str):
        return ""
    return " ".join(name.split())


def _as_utc(value: datetime | None) -> datetime | None:
    """Make a timestamp timezone-aware (SQLite may hand back a naive one)."""
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def _moment(at: datetime | None) -> datetime:
    return _as_utc(at) or utc_now()


def normalize_gstin(gstin: str | None) -> str | None:
    """Uppercase and trim, or None when there is no GSTIN."""
    if not isinstance(gstin, str):
        return None
    value = gstin.strip().upper()
    return value or None


def state_code_from_gstin(gstin: str | None) -> str:
    """The first two characters (the state code) or an empty string."""
    value = normalize_gstin(gstin)
    return value[:2] if value else ""


def case_buyer(case: Case) -> tuple[str | None, str]:
    """The buyer GSTIN and name stored with a case.

    `cases.buyer_gstin` is the column the API fills; older or hand-built rows
    may only carry the engine input, so the request's `buyer` block is the
    fallback. The name is read, never inferred.
    """
    payload: dict[str, Any] = case.input_json if isinstance(case.input_json, dict) else {}
    buyer = payload.get("buyer")
    buyer = buyer if isinstance(buyer, dict) else {}
    gstin = normalize_gstin(case.buyer_gstin) or normalize_gstin(buyer.get("gstin"))
    name = clean_name(buyer.get("name")) or clean_name(payload.get("buyer_name"))
    return gstin, name


@dataclass(frozen=True)
class Resolution:
    """What identity resolution decided for one set of buyer details."""

    customer_id: str
    kind: str
    created: bool
    gstin: str | None
    gstin_attached: bool
    case_attached: bool
    key: str = ""
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class BackfillReport:
    """Counts from one backfill run. All zero on a second, idempotent run."""

    cases_assigned: int
    customers_created: int
    gstins_attached: int
    unnamed_cases: int


def _customer_or_raise(session: Session, customer_id: str) -> Customer:
    customer = session.get(Customer, customer_id)
    if customer is None:
        raise LookupError(f"No customer with id {customer_id!r}")
    return customer


def _gstins_for_customer(session: Session, customer_id: str) -> list[CustomerGstin]:
    return list(
        session.exec(
            select(CustomerGstin).where(CustomerGstin.customer_id == customer_id)
        ).all()
    )


def _identity_records(
    session: Session,
    *,
    gstin: str | None,
    pan: str | None,
    normalized_name: str,
) -> list[IdentityCustomerRecord]:
    """The customers that could match this buyer, as pure snapshots.

    Only three narrow looks: the owner of the exact GSTIN, the PAN customer, and
    provisionals with the same normalised name. That is enough for every branch
    of `backend.insights.identity.resolve` and avoids loading the whole book for
    one case. Duplicate rows are collapsed by id.
    """
    candidates: dict[str, Customer] = {}

    def add(customer: Customer | None) -> None:
        if customer is not None:
            candidates[customer.id] = customer

    if gstin:
        link = session.get(CustomerGstin, gstin)
        if link is not None:
            add(session.get(Customer, link.customer_id))
    if pan:
        for customer in session.exec(
            select(Customer).where(Customer.kind == "PAN", Customer.pan == pan)
        ).all():
            add(customer)
    if normalized_name:
        for customer in session.exec(
            select(Customer)
            .where(
                Customer.kind == "PROVISIONAL",
                Customer.normalized_name == normalized_name,
            )
            .order_by(Customer.created_at, Customer.id)
        ).all():
            add(customer)

    return [
        IdentityCustomerRecord(
            id=customer.id,
            kind=customer.kind,
            pan=customer.pan,
            normalized_name=customer.normalized_name,
            display_name=customer.display_name,
            gstins=tuple(link.gstin for link in _gstins_for_customer(session, customer.id)),
        )
        for customer in candidates.values()
    ]


def resolve_customer(
    session: Session,
    *,
    buyer_gstin: str | None,
    buyer_name: str | None,
    at: datetime | None = None,
    first_seen_at: datetime | None = None,
) -> Resolution:
    """Find or create the customer for one buyer's details, without a case.

    The identity decision is made by `backend.insights.identity.resolve`; this
    function only supplies the existing snapshots and applies the result. A
    valid GSTIN maps to a PAN customer (same PAN groups automatically); an
    invalid or absent GSTIN maps to a PROVISIONAL customer by normalised name.
    Different PANs are never merged.
    """
    moment = _moment(at)
    gstin = normalize_gstin(buyer_gstin)
    name = clean_name(buyer_name)
    normalized = normalize_name(name)
    pan = pan_from_gstin(gstin) if gstin else None

    decision = resolve_identity(
        gstin,
        name,
        _identity_records(
            session, gstin=gstin, pan=pan, normalized_name=normalized
        ),
    )

    customer = (
        session.get(Customer, decision.customer_id)
        if decision.customer_id is not None
        else None
    )
    created = False
    if customer is None:
        customer = Customer(
            id=new_ulid(moment),
            kind=decision.kind,
            pan=decision.pan,
            display_name=decision.display_name or "Unnamed buyer",
            normalized_name=decision.normalized_name,
            created_at=moment,
        )
        session.add(customer)
        session.flush()
        created = True
    elif decision.promote_to_pan and customer.kind != "PAN":
        # A valid GSTIN on a provisional row: the PAN is the legal identity, so
        # the owner-confirmed record becomes the PAN customer.
        customer.kind = "PAN"
        customer.pan = decision.pan
        session.add(customer)
        session.flush()

    gstin_attached = False
    if decision.gstin is not None and decision.attach_gstin:
        existing_link = session.get(CustomerGstin, decision.gstin)
        if existing_link is None:
            session.add(
                CustomerGstin(
                    gstin=decision.gstin,
                    customer_id=customer.id,
                    state_code=state_code_from_gstin(decision.gstin),
                    first_seen_at=_as_utc(first_seen_at) or moment,
                )
            )
            session.flush()
            gstin_attached = True
        elif existing_link.customer_id != customer.id:
            # The pure resolver saw no owner, so this is a concurrent writer.
            # Never move a GSTIN between customers silently.
            raise ValueError(
                f"GSTIN {decision.gstin} is already attached to another customer; "
                "the case was not attached to that identity."
            )

    return Resolution(
        customer_id=customer.id,
        kind=customer.kind,
        created=created,
        gstin=decision.gstin,
        gstin_attached=gstin_attached,
        case_attached=False,
        key=decision.key,
        warnings=decision.warnings,
    )


def attach_case_to_customer(
    session: Session,
    case: Case,
    *,
    at: datetime | None = None,
    source: str = "backfill",
    actor: str = "SYSTEM",
) -> Resolution:
    """Resolve and attach one case, recording the decision on its own chain.

    Idempotent: a case that already has a customer is returned unchanged and
    writes no second event. Money never appears here, so the payload is plain
    JSON.
    """
    moment = _moment(at)
    if case.customer_id:
        customer = session.get(Customer, case.customer_id)
        return Resolution(
            customer_id=case.customer_id,
            kind=customer.kind if customer is not None else "",
            created=False,
            gstin=None,
            gstin_attached=False,
            case_attached=False,
        )

    gstin, name = case_buyer(case)
    resolution = resolve_customer(
        session,
        buyer_gstin=gstin,
        buyer_name=name,
        at=moment,
        first_seen_at=_as_utc(case.created_at) or moment,
    )
    case.customer_id = resolution.customer_id
    session.add(case)
    session.flush()

    payload = {
        "customer_id": resolution.customer_id,
        "key": resolution.key,
        "kind": resolution.kind,
        "buyer_gstin": resolution.gstin,
        "source": source,
        "created": resolution.created,
        "warnings": list(resolution.warnings),
    }
    if resolution.created:
        audit.append_event(
            session,
            case_id=case.id,
            type=CUSTOMER_CREATED,
            payload=payload,
            actor=actor,
            created_at=moment,
        )
    audit.append_event(
        session,
        case_id=case.id,
        type=CUSTOMER_ATTACHED,
        payload=payload,
        actor=actor,
        created_at=moment,
    )
    session.flush()
    return Resolution(
        customer_id=resolution.customer_id,
        kind=resolution.kind,
        created=resolution.created,
        gstin=resolution.gstin,
        gstin_attached=resolution.gstin_attached,
        case_attached=True,
        key=resolution.key,
        warnings=resolution.warnings,
    )


def backfill_case_customers(
    session: Session,
    *,
    at: datetime | None = None,
    actor: str = "SYSTEM",
) -> BackfillReport:
    """Assign a customer to every case that has none. Safe to run repeatedly.

    This is what `init_db()` runs on an existing v4 database, and what seeding
    runs after it inserts the presets. It never changes a case's money or dates;
    it only fills `cases.customer_id` and appends the audit events.
    """
    moment = _moment(at)
    pending = session.exec(
        select(Case)
        .where(Case.customer_id.is_(None))
        .order_by(Case.created_at, Case.id)
    ).all()

    created = 0
    gstins = 0
    unnamed = 0
    for case in pending:
        _gstin, name = case_buyer(case)
        if not name:
            unnamed += 1
        resolution = attach_case_to_customer(
            session, case, at=moment, source="backfill", actor=actor
        )
        created += int(resolution.created)
        gstins += int(resolution.gstin_attached)

    session.flush()
    return BackfillReport(
        cases_assigned=len(pending),
        customers_created=created,
        gstins_attached=gstins,
        unnamed_cases=unnamed,
    )


def refresh_normalized_names(session: Session) -> int:
    """Recompute `customers.normalized_name` from the current pure normaliser.

    v5 changed the normaliser from a lowercase key to the uppercase, legal-form
    aware key in `backend.insights.identity`. Existing rows must be refreshed
    before a backfill resolves against them, or an old "acme pvt ltd" row and a
    new "ACME PRIVATE LIMITED" row would look like two different buyers. This is
    derived data, not a business mutation, so it writes no audit event. Returns
    the number of rows changed.
    """
    changed = 0
    for customer in session.exec(select(Customer)).all():
        expected = normalize_name(customer.display_name)
        if customer.normalized_name != expected:
            customer.normalized_name = expected
            session.add(customer)
            changed += 1
    session.flush()
    return changed


def suggestions_for_book(
    session: Session, *, threshold: float
) -> list[Suggestion]:
    """Suggest owner actions from the stored customer book. Read-only.

    `threshold` must come from `insights.name_match_threshold` (the app's
    `identity_settings()` helper reads it). Suggestions are never applied here:
    ATTACH means a provisional record can be attached to a PAN customer, and
    LINK_AS_GROUP means two different PANs can be linked as a group, never
    merged.
    """
    customers = session.exec(
        select(Customer).order_by(Customer.created_at, Customer.id)
    ).all()
    links = session.exec(select(CustomerGstin)).all()
    memberships = session.exec(select(CustomerGroupMember)).all()
    dismissals = session.exec(select(MergeDismissal)).all()

    gstins_by_customer: dict[str, list[str]] = {}
    for link in links:
        gstins_by_customer.setdefault(link.customer_id, []).append(link.gstin)

    group_by_customer = {
        member.customer_id: member.group_id for member in memberships
    }

    dismissed_with: dict[str, set[str]] = {}
    for row in dismissals:
        dismissed_with.setdefault(row.customer_a, set()).add(row.customer_b)
        dismissed_with.setdefault(row.customer_b, set()).add(row.customer_a)

    records = [
        IdentityCustomerRecord(
            id=customer.id,
            kind=customer.kind,
            pan=customer.pan,
            normalized_name=customer.normalized_name,
            display_name=customer.display_name,
            gstins=tuple(gstins_by_customer.get(customer.id, ())),
            group_id=group_by_customer.get(customer.id),
            dismissed_with=frozenset(dismissed_with.get(customer.id, ())),
        )
        for customer in customers
    ]
    return identity_suggestions(records, threshold=threshold)


# ----------------------------------------------------------------- audit ----


def case_ids_for_customer(session: Session, customer_id: str) -> list[str]:
    """Every case attached to a customer, oldest first. The audit anchors."""
    return list(
        session.exec(
            select(Case.id)
            .where(Case.customer_id == customer_id)
            .order_by(Case.created_at, Case.id)
        ).all()
    )


def _audit_for_customer(
    session: Session,
    customer_id: str,
    *,
    event_type: str,
    payload: dict[str, Any],
    actor: str,
    at: datetime,
) -> int:
    """Write one event per case of the customer. Returns the number written."""
    written = 0
    for case_id in case_ids_for_customer(session, customer_id):
        audit.append_event(
            session,
            case_id=case_id,
            type=event_type,
            payload=payload,
            actor=actor,
            created_at=at,
        )
        written += 1
    return written


# ---------------------------------------------------------------- groups ----


def _unique_ids(customer_ids: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(customer_ids))


def _membership_for_customer(
    session: Session, customer_id: str
) -> CustomerGroupMember | None:
    return session.exec(
        select(CustomerGroupMember).where(
            CustomerGroupMember.customer_id == customer_id
        )
    ).first()


def create_group(
    session: Session,
    *,
    label: str,
    customer_ids: Iterable[str],
    actor: str = "USER",
    at: datetime | None = None,
) -> CustomerGroup:
    """Create an owner link between customers. Never a merge.

    Different PANs stay different customers; the group is a descriptive label
    over them. Membership is one group per customer, enforced in the table.
    """
    moment = _moment(at)
    clean_label = clean_name(label)
    if not clean_label:
        raise ValueError("A customer group needs a label.")
    ids = _unique_ids(customer_ids)
    if not ids:
        raise ValueError("A customer group needs at least one customer.")

    customers = [_customer_or_raise(session, customer_id) for customer_id in ids]
    for customer in customers:
        existing = _membership_for_customer(session, customer.id)
        if existing is not None:
            raise ValueError(
                f"{customer.display_name} is already in another group. "
                "Unlink it from that group first."
            )

    group = CustomerGroup(
        id=new_ulid(moment), label=clean_label, created_by="owner", created_at=moment
    )
    session.add(group)
    session.flush()
    for customer in customers:
        session.add(CustomerGroupMember(group_id=group.id, customer_id=customer.id))
    session.flush()

    for customer in customers:
        _audit_for_customer(
            session,
            customer.id,
            event_type=CUSTOMER_GROUP_CREATED,
            payload={
                "group_id": group.id,
                "group_label": group.label,
                "customer_id": customer.id,
            },
            actor=actor,
            at=moment,
        )
    return group


def group_for_customer(session: Session, customer_id: str) -> CustomerGroup | None:
    membership = _membership_for_customer(session, customer_id)
    if membership is None:
        return None
    return session.get(CustomerGroup, membership.group_id)


def link_group(
    session: Session,
    *,
    group_id: str,
    customer_id: str,
    actor: str = "USER",
    at: datetime | None = None,
) -> CustomerGroupMember:
    """Add one customer to an existing group. Idempotent for the same group."""
    moment = _moment(at)
    group = session.get(CustomerGroup, group_id)
    if group is None:
        raise LookupError(f"No customer group with id {group_id!r}")
    customer = _customer_or_raise(session, customer_id)

    existing = _membership_for_customer(session, customer.id)
    if existing is not None:
        if existing.group_id == group.id:
            return existing
        raise ValueError(
            f"{customer.display_name} is already in another group. "
            "Unlink it from that group first."
        )

    member = CustomerGroupMember(group_id=group.id, customer_id=customer.id)
    session.add(member)
    session.flush()
    _audit_for_customer(
        session,
        customer.id,
        event_type=CUSTOMER_GROUP_LINKED,
        payload={
            "group_id": group.id,
            "group_label": group.label,
            "customer_id": customer.id,
        },
        actor=actor,
        at=moment,
    )
    return member


def unlink_group(
    session: Session,
    *,
    group_id: str,
    customer_id: str,
    actor: str = "USER",
    at: datetime | None = None,
) -> bool:
    """Remove one customer from a group. Idempotent when not a member."""
    moment = _moment(at)
    group = session.get(CustomerGroup, group_id)
    if group is None:
        raise LookupError(f"No customer group with id {group_id!r}")
    customer = _customer_or_raise(session, customer_id)

    member = session.get(CustomerGroupMember, (group.id, customer.id))
    if member is None:
        return False
    session.delete(member)
    session.flush()
    _audit_for_customer(
        session,
        customer.id,
        event_type=CUSTOMER_GROUP_UNLINKED,
        payload={
            "group_id": group.id,
            "group_label": group.label,
            "customer_id": customer.id,
        },
        actor=actor,
        at=moment,
    )
    return True


# ------------------------------------------------------ merge dismissals ----


def _ordered_pair(customer_a: str, customer_b: str) -> tuple[str, str]:
    if customer_a == customer_b:
        raise ValueError("A merge suggestion needs two different customers.")
    return (customer_a, customer_b) if customer_a < customer_b else (customer_b, customer_a)


def is_merge_dismissed(session: Session, customer_a: str, customer_b: str) -> bool:
    first, second = _ordered_pair(customer_a, customer_b)
    return session.get(MergeDismissal, (first, second)) is not None


def dismiss_merge(
    session: Session,
    *,
    customer_a: str,
    customer_b: str,
    actor: str = "USER",
    at: datetime | None = None,
) -> MergeDismissal:
    """Remember that the owner rejected a merge suggestion. Never merges them."""
    moment = _moment(at)
    first, second = _ordered_pair(customer_a, customer_b)
    _customer_or_raise(session, first)
    _customer_or_raise(session, second)

    existing = session.get(MergeDismissal, (first, second))
    if existing is not None:
        return existing

    row = MergeDismissal(customer_a=first, customer_b=second, dismissed_at=moment)
    session.add(row)
    session.flush()
    payload = {"customer_a": first, "customer_b": second}
    for customer_id in (first, second):
        _audit_for_customer(
            session,
            customer_id,
            event_type=CUSTOMER_MERGE_DISMISSED,
            payload=payload,
            actor=actor,
            at=moment,
        )
    return row


def undo_merge_dismissal(
    session: Session,
    *,
    customer_a: str,
    customer_b: str,
    actor: str = "USER",
    at: datetime | None = None,
) -> bool:
    """Undo a dismissal so the suggestion may be shown again."""
    moment = _moment(at)
    first, second = _ordered_pair(customer_a, customer_b)
    row = session.get(MergeDismissal, (first, second))
    if row is None:
        return False
    session.delete(row)
    session.flush()
    payload = {"customer_a": first, "customer_b": second}
    for customer_id in (first, second):
        _audit_for_customer(
            session,
            customer_id,
            event_type=CUSTOMER_MERGE_DISMISSAL_UNDONE,
            payload=payload,
            actor=actor,
            at=moment,
        )
    return True


# ------------------------------------------------------------ GSTIN links ----


def attach_gstin(
    session: Session,
    *,
    customer_id: str,
    gstin: str,
    actor: str = "USER",
    at: datetime | None = None,
    first_seen_at: datetime | None = None,
) -> CustomerGstin:
    """Attach one GSTIN to a customer, auditing it on every attached case.

    A provisional customer is promoted to PAN when the GSTIN carries one and no
    other customer already owns that PAN. If another customer owns it, the
    owner is told to group the two: this function will not merge them.
    """
    moment = _moment(at)
    customer = _customer_or_raise(session, customer_id)
    value = normalize_gstin(gstin)
    if value is None:
        raise ValueError("A GSTIN is required.")

    existing = session.get(CustomerGstin, value)
    if existing is not None:
        if existing.customer_id == customer.id:
            return existing
        raise ValueError(
            "This GSTIN is already attached to another customer. "
            "Different registrations are never merged automatically; "
            "link the two customers as a group instead."
        )

    pan = pan_from_gstin(value)
    if customer.kind == "PAN":
        if pan is not None and pan != customer.pan:
            raise ValueError(
                "This GSTIN belongs to a different PAN. Different PANs are never "
                "merged; link the two customers as a group instead."
            )
    else:
        current_links = _gstins_for_customer(session, customer.id)
        if current_links:
            raise ValueError(
                "This customer already has a GSTIN. "
                "Different registrations are never merged automatically; "
                "link the two customers as a group instead."
            )
        if pan is not None:
            owner = session.exec(
                select(Customer).where(Customer.kind == "PAN", Customer.pan == pan)
            ).first()
            if owner is not None and owner.id != customer.id:
                raise ValueError(
                    "A customer with this PAN already exists. Different PANs are "
                    "never merged; link the two customers as a group instead."
                )
            customer.kind = "PAN"
            customer.pan = pan
            session.add(customer)
            session.flush()

    link = CustomerGstin(
        gstin=value,
        customer_id=customer.id,
        state_code=state_code_from_gstin(value),
        first_seen_at=_as_utc(first_seen_at) or moment,
    )
    session.add(link)
    session.flush()
    _audit_for_customer(
        session,
        customer.id,
        event_type=CUSTOMER_GSTIN_ATTACHED,
        payload={
            "customer_id": customer.id,
            "gstin": value,
            "state_code": link.state_code,
            "pan": pan,
            "kind": customer.kind,
        },
        actor=actor,
        at=moment,
    )
    return link


def detach_gstin(
    session: Session,
    *,
    gstin: str,
    actor: str = "USER",
    at: datetime | None = None,
) -> bool:
    """Remove a GSTIN link. Idempotent when it is already gone.

    The customer keeps PAN kind if it was promoted: that identity was confirmed
    by the owner, and detaching one registration does not un-confirm the PAN.
    """
    moment = _moment(at)
    value = normalize_gstin(gstin)
    if value is None:
        return False
    link = session.get(CustomerGstin, value)
    if link is None:
        return False
    customer_id = link.customer_id
    session.delete(link)
    session.flush()
    _audit_for_customer(
        session,
        customer_id,
        event_type=CUSTOMER_GSTIN_DETACHED,
        payload={"customer_id": customer_id, "gstin": value},
        actor=actor,
        at=moment,
    )
    return True


# -------------------------------------------------------------- payments ----


def _money_text(value: Decimal) -> str:
    return format(value, "f")


def _validated_amount(amount: Decimal | str | int) -> Decimal:
    if isinstance(amount, bool) or isinstance(amount, float):
        raise TypeError(
            "A payment amount must be Decimal or a decimal string, never float "
            f"(got {type(amount).__name__})"
        )
    try:
        value = amount if isinstance(amount, Decimal) else Decimal(str(amount))
    except Exception as exc:  # noqa: BLE001 - all conversions fail the same way
        raise ValueError(f"A payment amount must be a decimal number, got {amount!r}") from exc
    if not value.is_finite():
        raise ValueError("A payment amount must be finite.")
    if value <= 0:
        raise ValueError("A payment must be more than zero.")
    rounded = value.quantize(_TWO_PLACES, ROUND_HALF_UP)
    if rounded != value:
        raise ValueError("A payment amount can have at most two decimal places.")
    return rounded


def record_payment(
    session: Session,
    *,
    case_id: str,
    amount: Decimal | str | int,
    paid_on: date,
    method: str,
    note: str | None = None,
    actor: str = "USER",
    at: datetime | None = None,
) -> Payment:
    """Record money received. Appends `payment.recorded` to the case chain."""
    moment = _moment(at)
    case = session.get(Case, case_id)
    if case is None:
        raise LookupError(f"No case with id {case_id!r}")
    if isinstance(paid_on, datetime) or not isinstance(paid_on, date):
        raise TypeError("paid_on must be a date (YYYY-MM-DD).")
    method_value = (method or "").strip().lower()
    if method_value not in PAYMENT_METHODS:
        raise ValueError(
            f"Unknown payment method {method!r}. Use one of: "
            + ", ".join(PAYMENT_METHODS)
            + "."
        )

    value = _validated_amount(amount)
    payment = Payment(
        id=new_ulid(moment),
        case_id=case.id,
        amount=value,
        paid_on=paid_on,
        method=method_value,
        note=clean_name(note) or None,
        created_at=moment,
    )
    session.add(payment)
    session.flush()
    audit.append_event(
        session,
        case_id=case.id,
        type=PAYMENT_RECORDED,
        payload={
            "payment_id": payment.id,
            "amount": _money_text(value),
            "paid_on": paid_on.isoformat(),
            "method": method_value,
        },
        actor=actor,
        created_at=moment,
    )
    return payment


def void_payment(
    session: Session,
    *,
    payment_id: str,
    reason: str | None = None,
    actor: str = "USER",
    at: datetime | None = None,
) -> Payment:
    """Void a payment instead of deleting it. Idempotent on an already-void row."""
    moment = _moment(at)
    payment = session.get(Payment, payment_id)
    if payment is None:
        raise LookupError(f"No payment with id {payment_id!r}")
    if payment.voided_at is not None:
        return payment

    payment.voided_at = moment
    session.add(payment)
    session.flush()
    audit.append_event(
        session,
        case_id=payment.case_id,
        type=PAYMENT_VOIDED,
        payload={
            "payment_id": payment.id,
            "amount": _money_text(payment.amount),
            "reason": clean_name(reason),
        },
        actor=actor,
        created_at=moment,
    )
    return payment


def payments_for_case(
    session: Session, case_id: str, *, include_voided: bool = True
) -> list[Payment]:
    """The case's payments, oldest first. Voided rows stay in the list by default."""
    statement = select(Payment).where(Payment.case_id == case_id)
    if not include_voided:
        statement = statement.where(Payment.voided_at.is_(None))
    return list(session.exec(statement.order_by(Payment.paid_on, Payment.created_at)).all())
