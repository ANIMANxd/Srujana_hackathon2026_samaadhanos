"""Database wiring: `DATABASE_URL`, the engine, sessions and `init_db()`.

Default is `sqlite:///./data/samadhaan.db` (relative to the working directory,
which is the repo root for `make` and uvicorn). `data/` is git-ignored.

The module holds one lazily-built engine so tests can point the whole store at a
temporary file with `configure(...)` instead of re-importing the package.
"""

from __future__ import annotations

import os
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session, SQLModel, create_engine

DEFAULT_DATABASE_URL = "sqlite:///./data/samadhaan.db"

# Models must be imported before `create_all` so every table is registered.
from backend.store import models as _models  # noqa: E402,F401  (side effect: table registration)

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None
_url_in_use: str | None = None

# Startup does DDL and a data backfill. Two app lifespans can run at once (the
# workflow suite starts two TestClients in parallel), and both would otherwise
# see the same case as "no customer" and insert the same GSTIN. The lock makes
# in-process startup sequential; the backfill retry below covers a second process.
_INIT_LOCK = threading.Lock()


def database_url() -> str:
    """`DATABASE_URL` from the environment, else the documented SQLite default."""
    return os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)


def _sqlite_path(url: str) -> Path | None:
    """The file behind a `sqlite:///...` URL, or None for anything else."""
    prefix = "sqlite:///"
    if not url.startswith(prefix):
        return None
    raw = url[len(prefix) :]
    if not raw or raw == ":memory:":
        return None
    return Path(raw)


def configure(url: str | None = None) -> Engine:
    """(Re)build the engine for `url` (default: the environment). Idempotent."""
    global _engine, _session_factory, _url_in_use

    target = url or database_url()
    if _engine is not None and _url_in_use == target:
        return _engine

    sqlite_file = _sqlite_path(target)
    if sqlite_file is not None:
        sqlite_file.parent.mkdir(parents=True, exist_ok=True)

    connect_args = {"check_same_thread": False} if target.startswith("sqlite") else {}
    _engine = create_engine(target, connect_args=connect_args)
    _session_factory = sessionmaker(bind=_engine, class_=Session, expire_on_commit=False)
    _url_in_use = target
    return _engine


def get_engine() -> Engine:
    return _engine or configure()


def get_session_factory() -> sessionmaker[Session]:
    if _session_factory is None:
        configure()
    assert _session_factory is not None
    return _session_factory


@contextmanager
def session_scope() -> Iterator[Session]:
    """A transactional session: commits on success, rolls back on any exception."""
    factory = get_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _refresh_customer_names() -> None:
    """Recompute normalised names before resolving any case (v5 normaliser)."""
    from backend.store import customers

    with session_scope() as session:
        customers.refresh_normalized_names(session)


def _backfill_existing_cases() -> None:
    """Run the customer backfill, retrying once if another process won a race.

    A unique-GSTIN violation means a concurrent startup inserted the same buyer
    first. The whole transaction is rolled back and re-run: the retry sees the
    committed link and assigns the case to it. The backfill is idempotent, so a
    retry cannot double-write.
    """
    from backend.store import customers

    attempts = 3
    for attempt in range(1, attempts + 1):
        try:
            with session_scope() as session:
                customers.backfill_case_customers(session)
            return
        except IntegrityError:
            if attempt == attempts:
                raise


def init_db(url: str | None = None, *, backfill: bool = True) -> Engine:
    """Create every table, apply additive migrations, assign missing customers.

    Safe to call on every startup. New tables are created by `create_all`; the
    one column-level v5 change is applied by `migrations.migrate_schema`; then
    every case without a customer is resolved and attached, with an audit event
    on its own chain (`backend/store/customers.py`). The backfill is idempotent,
    so a second call writes nothing.
    """
    with _INIT_LOCK:
        engine = configure(url)
        SQLModel.metadata.create_all(engine)

        from backend.store.migrations import migrate_schema

        migrate_schema(engine)

        if backfill:
            _refresh_customer_names()
            _backfill_existing_cases()
        return engine


def reset_db(url: str | None = None) -> Engine:
    """Drop every table and recreate them. Destructive: `make db-reset` only."""
    engine = configure(url)
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)

    from backend.store.migrations import migrate_schema

    migrate_schema(engine)
    return engine


def database_file(url: str | None = None) -> Path | None:
    """Where the SQLite file lives, so callers can delete it outright."""
    return _sqlite_path(url or database_url())


def dispose() -> None:
    """Drop the cached engine so the file can be deleted or the URL repointed."""
    global _engine, _session_factory, _url_in_use
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None
    _url_in_use = None
