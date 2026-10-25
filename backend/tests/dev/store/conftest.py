"""Shared fixtures for the store tests: every test gets its own SQLite file.

The session fixture deliberately does **not** auto-commit: a test that expects a
failed flush (a float write, a second open track) must be able to inspect the
session afterwards without the teardown raising a pending-rollback error.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from decimal import Decimal

import pytest
from sqlmodel import Session

from backend.store import db as store_db
from backend.store.ids import new_ulid
from backend.store.models import Case


@pytest.fixture()
def database_url(tmp_path) -> str:
    return f"sqlite:///{tmp_path / 'store.db'}"


@pytest.fixture()
def session(database_url: str) -> Iterator[Session]:
    store_db.dispose()
    store_db.init_db(database_url)
    active = store_db.get_session_factory()()
    try:
        yield active
    finally:
        active.rollback()
        active.close()
        store_db.dispose()


@pytest.fixture()
def case(session: Session) -> Case:
    row = Case(
        id=new_ulid(),
        supplier_ref="SUP-SYN-0001",
        buyer_gstin="29SYN000000000Z1",
        invoice_no="INV-0042",
        invoice_date=date(2026, 9, 16),
        accepted_amount=Decimal("1250000.00"),
        delivery_date=date(2026, 9, 14),
        input_json={"contract_version": "1.0", "case_id": "seed"},
        engine_version="1.0",
        config_version="1.0",
    )
    session.add(row)
    session.flush()
    return row
