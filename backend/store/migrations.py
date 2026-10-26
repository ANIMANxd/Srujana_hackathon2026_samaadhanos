"""Additive schema migrations for the v5 customer book.

The v4 store used `SQLModel.metadata.create_all` alone: fine while the schema
only ever gained tables. v5 adds `cases.customer_id`, and `create_all` does not
alter a table that already exists. This module applies the one column-level
change that cannot be expressed by creating a missing table.

Rules for everything here:

- **Additive only.** No drops, no renames, no type changes, no data loss.
- **Idempotent.** The database's own shape is the source of truth; every step
  inspects before it alters, so `init_db()` can run on every startup.
- **Portable.** `ALTER TABLE ... ADD COLUMN` and `CREATE INDEX IF NOT EXISTS`
  are plain SQLite and Postgres SQL. No Alembic dependency for one column.

New tables (`customers`, `customer_gstins`, `customer_groups`,
`customer_group_members`, `merge_dismissals`, `payments`) need no step here:
`SQLModel.metadata.create_all` already creates a table that is missing.
"""

from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError

CUSTOMER_COLUMN = "customer_id"
CUSTOMER_INDEX = "ix_cases_customer_id"

# Every step, in the order it runs. A test can assert the list stays additive.
MIGRATION_STEPS: tuple[str, ...] = ("cases.customer_id", "cases.customer_id.index")


def _table_names(engine: Engine) -> set[str]:
    return set(inspect(engine).get_table_names())


def _column_names(engine: Engine, table: str) -> set[str]:
    return {column["name"] for column in inspect(engine).get_columns(table)}


def _index_names(engine: Engine, table: str) -> set[str]:
    return {index["name"] for index in inspect(engine).get_indexes(table)}


def migrate_schema(engine: Engine) -> list[str]:
    """Bring an existing v4 database up to the v5 shape. Return applied steps.

    Call **after** `SQLModel.metadata.create_all`, so the referenced `customers`
    table exists before the foreign key is added to `cases`.

    An empty list means the schema was already current. The function never
    touches a row; the data backfill is `backend.store.customers`' job.
    """
    if "cases" not in _table_names(engine):
        return []

    applied: list[str] = []

    if CUSTOMER_COLUMN not in _column_names(engine, "cases"):
        if "customers" not in _table_names(engine):
            raise RuntimeError(
                "Cannot add cases.customer_id before the customers table exists. "
                "Run SQLModel.metadata.create_all first."
            )
        try:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        f"ALTER TABLE cases ADD COLUMN {CUSTOMER_COLUMN} VARCHAR(26) "
                        "REFERENCES customers(id)"
                    )
                )
        except DBAPIError:
            # A second process may have added the column between the inspection
            # and the ALTER. Only swallow the error if the column is now there.
            if CUSTOMER_COLUMN not in _column_names(engine, "cases"):
                raise
        else:
            applied.append("cases.customer_id")

    if CUSTOMER_INDEX not in _index_names(engine, "cases"):
        with engine.begin() as connection:
            connection.execute(
                text(
                    f"CREATE INDEX IF NOT EXISTS {CUSTOMER_INDEX} "
                    f"ON cases ({CUSTOMER_COLUMN})"
                )
            )
        applied.append("cases.customer_id.index")

    return applied
