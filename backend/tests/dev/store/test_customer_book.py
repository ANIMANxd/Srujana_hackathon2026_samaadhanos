"""The v5 customer book: resolution, backfill, groups and audit.

Hand-built buyer details are deliberately round and small. What is being proved
is identity behaviour, not money: the same PAN groups, different PANs never do,
name-only provisionals match only by an exact normalised key, and every write
lands on the existing case hash chain.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from backend.store import customers
from backend.store.audit import verify_chain
from backend.store.ids import new_ulid
from backend.store.models import Case, Customer, CustomerGstin, Event

AT = datetime(2026, 10, 26, 9, 0, tzinfo=UTC)


def _add_case(
    session: Session,
    *,
    gstin: str | None = None,
    name: str | None = None,
    invoice_no: str = "INV-001",
    case_id: str | None = None,
) -> Case:
    payload: dict = {"buyer": {}}
    if name is not None:
        payload["buyer"]["name"] = name
    if gstin is not None:
        payload["buyer"]["gstin"] = gstin
    row = Case(
        id=case_id or new_ulid(AT),
        supplier_ref="SUP-SYN-0001",
        buyer_gstin=gstin,
        invoice_no=invoice_no,
        invoice_date=date(2026, 9, 1),
        accepted_amount=Decimal("100000.00"),
        delivery_date=date(2026, 9, 1),
        input_json=payload,
        engine_version="1.0",
        config_version="1.0",
        created_at=AT,
    )
    session.add(row)
    session.flush()
    return row


def _event_types(session: Session, case_id: str) -> list[str]:
    return [
        event.type
        for event in session.exec(
            select(Event).where(Event.case_id == case_id).order_by(Event.seq)
        ).all()
    ]


# ---------------------------------------------------------- resolution ----


def test_backfill_gives_every_case_a_customer(session: Session):
    """Six cases, four identities: every case ends up attached and audited."""
    acme_a = _add_case(
        session, gstin="27ABCDE1234F1Z5", name="Acme Traders Pvt Ltd", invoice_no="INV-1"
    )
    acme_b = _add_case(
        session, gstin="29ABCDE1234F1Z9", name="Acme Traders Pvt Ltd", invoice_no="INV-2"
    )
    other_pan = _add_case(
        session, gstin="29ZZZZZ9999Z1Z5", name="Acme Traders Pvt Ltd", invoice_no="INV-3"
    )
    beta_a = _add_case(session, name="Beta & Co.", invoice_no="INV-4")
    beta_b = _add_case(session, name="beta and co", invoice_no="INV-5")
    unnamed = _add_case(session, invoice_no="INV-6")
    cases = [acme_a, acme_b, other_pan, beta_a, beta_b, unnamed]

    report = customers.backfill_case_customers(session, at=AT)

    assert report.cases_assigned == 6
    assert report.customers_created == 4  # PAN ABCDE1234F, PAN ZZZZZ9999Z, beta, unnamed
    assert report.gstins_attached == 3
    assert report.unnamed_cases == 1

    for case in cases:
        session.refresh(case)
        assert case.customer_id, f"{case.invoice_no} was left without a customer"

    # Same PAN across two GSTINs is one legal entity.
    assert acme_a.customer_id == acme_b.customer_id
    # A different PAN is never merged, even with the same display name.
    assert other_pan.customer_id != acme_a.customer_id
    # Exact normalised name groups name-only provisionals; "&" -> "and".
    assert beta_a.customer_id == beta_b.customer_id
    assert unnamed.customer_id != beta_a.customer_id

    acme = session.get(Customer, acme_a.customer_id)
    assert acme is not None and acme.kind == "PAN" and acme.pan == "ABCDE1234F"

    for case in cases:
        assert verify_chain(session, case.id)["ok"] is True

    # customer.created once per new customer, customer.attached once per case.
    all_types = [kind for case in cases for kind in _event_types(session, case.id)]
    assert all_types.count("customer.created") == 4
    assert all_types.count("customer.attached") == 6


def test_resolver_reads_the_engine_input_when_the_column_is_empty(session: Session):
    """A row that only carries input_json.buyer still resolves by its GSTIN."""
    case = _add_case(session, gstin=None, name=None, invoice_no="INV-9")
    case.input_json = {
        "buyer": {"name": "Input Only Buyer", "gstin": "27ABCDE1234F1Z5"}
    }
    session.add(case)
    session.flush()

    report = customers.backfill_case_customers(session, at=AT)
    session.refresh(case)

    assert report.cases_assigned == 1
    assert case.customer_id is not None
    customer = session.get(Customer, case.customer_id)
    assert customer.kind == "PAN"
    assert customer.pan == "ABCDE1234F"


def test_backfill_is_idempotent(session: Session):
    case = _add_case(session, gstin="27ABCDE1234F1Z5", name="Acme", invoice_no="INV-1")

    first = customers.backfill_case_customers(session, at=AT)
    session.refresh(case)
    customer_id = case.customer_id
    event_count = len(_event_types(session, case.id))

    second = customers.backfill_case_customers(session, at=AT)

    assert first.cases_assigned == 1
    assert second.cases_assigned == 0
    assert second.customers_created == 0
    session.refresh(case)
    assert case.customer_id == customer_id
    assert len(_event_types(session, case.id)) == event_count


def test_a_pan_is_unique_and_provisionals_may_share_a_null_pan(session: Session):
    first = Customer(
        id=new_ulid(AT), kind="PAN", pan="ABCDE1234F", display_name="A",
        normalized_name="a", created_at=AT,
    )
    session.add(first)
    session.flush()

    session.add(
        Customer(
            id=new_ulid(AT), kind="PAN", pan="ABCDE1234F", display_name="B",
            normalized_name="b", created_at=AT,
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()

    # A rollback removed the first row with it; both null-PAN provisionals are fine.
    session.add_all(
        [
            Customer(
                id=new_ulid(AT), kind="PROVISIONAL", pan=None, display_name="C",
                normalized_name="c", created_at=AT,
            ),
            Customer(
                id=new_ulid(AT), kind="PROVISIONAL", pan=None, display_name="D",
                normalized_name="d", created_at=AT,
            ),
        ]
    )
    session.flush()


# --------------------------------------------------------------- groups ----


def test_group_membership_is_single_and_audited(session: Session):
    first = _add_case(session, gstin="27ABCDE1234F1Z5", name="Acme", invoice_no="INV-1")
    second = _add_case(session, gstin="29ZZZZZ9999Z1Z5", name="Zed", invoice_no="INV-2")
    customers.backfill_case_customers(session, at=AT)
    session.refresh(first)
    session.refresh(second)

    group = customers.create_group(
        session, label="Same owner group", customer_ids=[first.customer_id], at=AT
    )
    member = customers.link_group(
        session, group_id=group.id, customer_id=second.customer_id, at=AT
    )

    assert member.group_id == group.id
    assert customers.group_for_customer(session, second.customer_id).id == group.id

    # A customer is in at most one group.
    with pytest.raises(ValueError, match="already in another group"):
        customers.create_group(
            session, label="Second group", customer_ids=[second.customer_id], at=AT
        )

    assert customers.unlink_group(
        session, group_id=group.id, customer_id=second.customer_id, at=AT
    )
    assert not customers.unlink_group(
        session, group_id=group.id, customer_id=second.customer_id, at=AT
    )

    types = _event_types(session, first.id) + _event_types(session, second.id)
    assert types.count("customer.group_created") == 1
    assert types.count("customer.group_linked") == 1
    assert types.count("customer.group_unlinked") == 1
    assert verify_chain(session, first.id)["ok"] is True
    assert verify_chain(session, second.id)["ok"] is True


def test_a_group_does_not_merge_the_two_customers(session: Session):
    """Linking is descriptive: each case keeps its own customer and PAN."""
    first = _add_case(session, gstin="27ABCDE1234F1Z5", name="Acme", invoice_no="INV-1")
    second = _add_case(session, gstin="29ZZZZZ9999Z1Z5", name="Zed", invoice_no="INV-2")
    customers.backfill_case_customers(session, at=AT)
    session.refresh(first)
    session.refresh(second)

    customers.create_group(
        session,
        label="Same owner",
        customer_ids=[first.customer_id, second.customer_id],
        at=AT,
    )

    assert first.customer_id != second.customer_id
    assert session.get(Customer, first.customer_id).pan == "ABCDE1234F"
    assert session.get(Customer, second.customer_id).pan == "ZZZZZ9999Z"


# ------------------------------------------------------------ dismissals ----


def test_merge_dismissal_is_canonical_idempotent_and_undoable(session: Session):
    first = _add_case(session, gstin="27ABCDE1234F1Z5", name="Acme", invoice_no="INV-1")
    second = _add_case(session, gstin="29ZZZZZ9999Z1Z5", name="Zed", invoice_no="INV-2")
    customers.backfill_case_customers(session, at=AT)
    session.refresh(first)
    session.refresh(second)
    a, b = sorted((first.customer_id, second.customer_id))

    row = customers.dismiss_merge(session, customer_a=b, customer_b=a, at=AT)

    assert (row.customer_a, row.customer_b) == (a, b)
    assert customers.is_merge_dismissed(session, a, b)
    assert customers.is_merge_dismissed(session, b, a)
    event_total = len(_event_types(session, first.id)) + len(_event_types(session, second.id))

    again = customers.dismiss_merge(session, customer_a=a, customer_b=b, at=AT)
    assert again.customer_a == a
    assert (
        len(_event_types(session, first.id)) + len(_event_types(session, second.id))
        == event_total
    ), "a repeated dismissal must not write a second event"

    assert customers.undo_merge_dismissal(session, customer_a=a, customer_b=b, at=AT)
    assert not customers.undo_merge_dismissal(session, customer_a=a, customer_b=b, at=AT)
    assert not customers.is_merge_dismissed(session, a, b)
    assert (
        len(_event_types(session, first.id)) + len(_event_types(session, second.id))
        == event_total + 2
    ), "undo writes one event per affected customer"


# ----------------------------------------------------------- GSTIN links ----


def test_attaching_a_gstin_promotes_a_provisional_and_refuses_another_pan(session: Session):
    case = _add_case(session, name="Gamma Works", invoice_no="INV-1")
    customers.backfill_case_customers(session, at=AT)
    session.refresh(case)
    customer = session.get(Customer, case.customer_id)
    assert customer.kind == "PROVISIONAL" and customer.pan is None

    link = customers.attach_gstin(
        session, customer_id=customer.id, gstin="27ABCDE1234F1Z5", at=AT
    )
    assert link.state_code == "27"
    assert customer.kind == "PAN" and customer.pan == "ABCDE1234F"

    # Same PAN, different state registration: still the same legal entity.
    customers.attach_gstin(
        session, customer_id=customer.id, gstin="29ABCDE1234F1Z9", at=AT
    )

    with pytest.raises(ValueError, match="different PAN"):
        customers.attach_gstin(
            session, customer_id=customer.id, gstin="29ZZZZZ9999Z1Z5", at=AT
        )

    assert customers.detach_gstin(session, gstin="27ABCDE1234F1Z5", at=AT)
    assert not customers.detach_gstin(session, gstin="27ABCDE1234F1Z5", at=AT)
    # The confirmed PAN identity survives detaching one registration.
    assert customer.kind == "PAN" and customer.pan == "ABCDE1234F"

    types = _event_types(session, case.id)
    assert types.count("customer.gstin_attached") == 2
    assert types.count("customer.gstin_detached") == 1
    assert verify_chain(session, case.id)["ok"] is True


def test_a_gstin_attached_to_one_customer_cannot_move_to_another(session: Session):
    first = _add_case(session, gstin="27ABCDE1234F1Z5", name="Acme", invoice_no="INV-1")
    second = _add_case(session, gstin="29ZZZZZ9999Z1Z5", name="Zed", invoice_no="INV-2")
    customers.backfill_case_customers(session, at=AT)
    session.refresh(first)
    session.refresh(second)

    with pytest.raises(ValueError, match="already attached"):
        customers.attach_gstin(
            session, customer_id=second.customer_id, gstin="27ABCDE1234F1Z5", at=AT
        )


# ----------------------------------------------------------------- seed ----


def test_db_reset_seeds_a_customer_for_every_case(database_url: str):
    """`make db-reset` path: every preset gets a customer and an audit event."""
    from backend.store import db as store_db
    from backend.store.seed import preset_files, reset_and_seed

    store_db.dispose()
    cases = reset_and_seed(database_url)
    try:
        assert len(cases) == len(preset_files())

        with store_db.session_scope() as session:
            rows = session.exec(select(Case)).all()
            assert len(rows) == len(cases)
            for row in rows:
                assert row.customer_id, f"seeded case {row.invoice_no} has no customer"
                assert verify_chain(session, row.id)["ok"] is True
                assert "customer.attached" in _event_types(session, row.id)

            gstins = session.exec(select(CustomerGstin)).all()
            assert len(gstins) == len(rows), "each preset GSTIN should be attached once"
            raw = session.execute(
                text("SELECT typeof(amount) FROM payments LIMIT 1")
            ).first()
            assert raw is None  # seeding records no payment
    finally:
        store_db.dispose()


def test_refresh_normalized_names_moves_the_old_key_to_the_v5_key(session: Session):
    customer = Customer(
        id=new_ulid(AT),
        kind="PROVISIONAL",
        display_name="Acme Industries Pvt. Ltd.",
        normalized_name="acme industries pvt ltd",  # the pre-v5 lowercase key
        created_at=AT,
    )
    session.add(customer)
    session.flush()

    changed = customers.refresh_normalized_names(session)

    assert changed == 1
    assert customer.normalized_name == "ACME INDUSTRIES PRIVATE LIMITED"
    assert customers.refresh_normalized_names(session) == 0


def test_suggestions_use_the_configured_threshold_and_respect_dismissals(session: Session):
    from backend.app.config_loader import identity_settings, load_config

    acme = _add_case(
        session, gstin="27ABCDE1234F1Z5", name="Acme Industries Private Limited",
        invoice_no="INV-1",
    )
    zenith = _add_case(
        session, gstin="29ZZZZZ9999Z1Z5", name="Zenith Components Private Limited",
        invoice_no="INV-2",
    )
    provisional = _add_case(
        session, name="Acme Industries Pvt. Ltd.", invoice_no="INV-3"
    )
    customers.backfill_case_customers(session, at=AT)
    for case in (acme, zenith, provisional):
        session.refresh(case)

    settings = identity_settings(load_config())
    assert settings.name_match_threshold == 0.90
    assert settings.verified is False

    found = customers.suggestions_for_book(
        session, threshold=settings.name_match_threshold
    )
    assert len(found) == 1
    assert found[0]["kind"] == "ATTACH"
    assert {found[0]["a"], found[0]["b"]} == {
        provisional.customer_id,
        acme.customer_id,
    }

    customers.dismiss_merge(
        session,
        customer_a=provisional.customer_id,
        customer_b=acme.customer_id,
        at=AT,
    )
    assert customers.suggestions_for_book(
        session, threshold=settings.name_match_threshold
    ) == []

