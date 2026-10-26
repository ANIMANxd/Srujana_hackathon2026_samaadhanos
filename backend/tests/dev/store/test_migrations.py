"""The v5 migration is additive and keeps every existing case.

The old database is built with the v4 shape by hand (a `cases` table without
`customer_id`, plus a valid `case.created` event) because that is exactly what a
v4 file looks like. `init_db()` must add the column, keep the rows, keep the
chain valid, and backfill a customer.
"""

from __future__ import annotations

import threading
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import create_engine, text
from sqlmodel import Session, SQLModel, select

from backend.store import db as store_db
from backend.store.audit import append_event, verify_chain
from backend.store.migrations import migrate_schema
from backend.store.models import Case, Customer, CustomerGstin, Event

OLD_CASE_ID = "01JAV4E7K3M9Q2R5T8V0W1XCZE"
OLD_AT = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)


def _create_v4_database(url: str) -> None:
    """A v4 `cases` row and a valid chain, with no v5 tables at all."""
    engine = create_engine(url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    CREATE TABLE cases (
                        id VARCHAR(26) NOT NULL PRIMARY KEY,
                        supplier_ref VARCHAR(255) NOT NULL,
                        buyer_gstin VARCHAR(255),
                        invoice_no VARCHAR(255) NOT NULL,
                        invoice_date DATE NOT NULL,
                        accepted_amount TEXT NOT NULL,
                        delivery_date DATE,
                        input_json JSON NOT NULL,
                        engine_version VARCHAR(255) NOT NULL,
                        config_version VARCHAR(255) NOT NULL,
                        created_at DATETIME NOT NULL
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO cases (
                        id, supplier_ref, buyer_gstin, invoice_no, invoice_date,
                        accepted_amount, delivery_date, input_json, engine_version,
                        config_version, created_at
                    ) VALUES (
                        :id, 'SUP-SYN-0001', :gstin, 'INV-OLD-1', '2026-09-01',
                        '1250000.00', '2026-09-01',
                        '{"buyer": {"name": "Legacy Buyer", "gstin": "27ABCDE1234F1Z5"}}',
                        '1.0', '1.0', '2026-09-01 09:00:00.000000'
                    )
                    """
                ),
                {"id": OLD_CASE_ID, "gstin": "27ABCDE1234F1Z5"},
            )
        # The audit table is unchanged by v5, so the old database already has it.
        SQLModel.metadata.tables["events"].create(engine)
        with Session(engine) as session:
            append_event(
                session,
                case_id=OLD_CASE_ID,
                type="case.created",
                payload={"invoice_no": "INV-OLD-1"},
                actor="USER",
                created_at=OLD_AT,
            )
            session.commit()
    finally:
        engine.dispose()


def test_migration_on_an_existing_database_keeps_every_case(database_url: str):
    _create_v4_database(database_url)
    store_db.dispose()

    store_db.init_db(database_url)
    try:
        with store_db.session_scope() as session:
            cases = session.exec(select(Case)).all()
            assert len(cases) == 1, "the migration must not lose a case"
            case = cases[0]
            assert case.id == OLD_CASE_ID
            assert case.customer_id, "the backfill must assign every case a customer"

            customer = session.get(Customer, case.customer_id)
            assert customer is not None
            assert customer.kind == "PAN"
            assert customer.pan == "ABCDE1234F"
            assert customer.display_name == "Legacy Buyer"

            gstin = session.get(CustomerGstin, "27ABCDE1234F1Z5")
            assert gstin is not None and gstin.customer_id == customer.id
            assert gstin.first_seen_at.replace(tzinfo=UTC) == OLD_AT

            # The original event is intact and the backfill appended to it.
            chain = verify_chain(session, case.id)
            assert chain["ok"] is True
            assert chain["checked"] == 3
            seq_one = session.execute(
                text("SELECT type FROM events WHERE case_id = :cid AND seq = 1"),
                params={"cid": case.id},
            ).one()
            assert seq_one[0] == "case.created"

            columns = {
                row[1] for row in session.execute(text("PRAGMA table_info(cases)"))
            }
            assert "customer_id" in columns
            indexes = {
                row[1] for row in session.execute(text("PRAGMA index_list(cases)"))
            }
            assert "ix_cases_customer_id" in indexes

        # A second startup changes nothing.
        assert migrate_schema(store_db.get_engine()) == []
        store_db.init_db(database_url)
        with store_db.session_scope() as session:
            assert len(session.exec(select(Case)).all()) == 1
            assert verify_chain(session, OLD_CASE_ID)["checked"] == 3
            assert len(session.exec(select(Customer)).all()) == 1
    finally:
        store_db.dispose()


def test_a_fresh_database_has_the_whole_v5_shape(database_url: str):
    store_db.dispose()
    store_db.init_db(database_url)
    try:
        with store_db.session_scope() as session:
            tables = {
                row[0]
                for row in session.execute(
                    text("SELECT name FROM sqlite_master WHERE type='table'")
                ).all()
            }
            assert {
                "customers",
                "customer_gstins",
                "customer_groups",
                "customer_group_members",
                "merge_dismissals",
                "payments",
            } <= tables

            payment_types = {
                row[1]: row[2]
                for row in session.execute(text("PRAGMA table_info(payments)")).all()
            }
            assert payment_types["amount"].upper() == "TEXT"

            indexes = {
                row[1] for row in session.execute(text("PRAGMA index_list(cases)"))
            }
            assert "ix_cases_customer_id" in indexes

            # Nothing to migrate on a database created from the current metadata.
            assert migrate_schema(store_db.get_engine()) == []
    finally:
        store_db.dispose()


def test_two_startups_at_once_backfill_the_case_only_once(database_url: str):
    """Two app lifespans racing on one database must not insert the GSTIN twice.

    This is the shape of the v4 workflow suite's concurrent-bid test: two
    TestClients start together on the same file. The startup lock serialises the
    backfill; the retry in `init_db` covers a second process.
    """
    store_db.dispose()
    store_db.init_db(database_url, backfill=False)
    with store_db.session_scope() as session:
        session.add(
            Case(
                id=OLD_CASE_ID,
                supplier_ref="SUP-SYN-0001",
                buyer_gstin="27ABCDE1234F1Z5",
                invoice_no="INV-RACE-1",
                invoice_date=date(2026, 9, 1),
                accepted_amount=Decimal("100000.00"),
                input_json={"buyer": {"name": "Race Buyer", "gstin": "27ABCDE1234F1Z5"}},
                created_at=OLD_AT,
            )
        )

    barrier = threading.Barrier(2)
    errors: list[BaseException] = []

    def start() -> None:
        try:
            barrier.wait(timeout=10)
            store_db.init_db(database_url)
        except BaseException as exc:  # noqa: BLE001 - reported to the assertion
            errors.append(exc)

    threads = [threading.Thread(target=start) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert errors == [], f"startup raised: {errors!r}"
    try:
        with store_db.session_scope() as session:
            cases = session.exec(select(Case)).all()
            assert len(cases) == 1
            assert cases[0].customer_id

            assert len(session.exec(select(CustomerGstin)).all()) == 1
            assert len(session.exec(select(Customer)).all()) == 1
            attached = session.exec(
                select(Event).where(Event.type == "customer.attached")
            ).all()
            assert len(attached) == 1
            assert verify_chain(session, OLD_CASE_ID)["ok"] is True
    finally:
        store_db.dispose()
