"""A temporary store per test: the case routes must never touch `data/samadhaan.db`."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.store import db as store_db


@pytest.fixture()
def database_url(tmp_path) -> str:
    return f"sqlite:///{tmp_path / 'cases.db'}"


@pytest.fixture()
def client(database_url: str, monkeypatch) -> Iterator[TestClient]:
    """A client on a throwaway database.

    `DATABASE_URL` is set as well as passed to `init_db`, because the app's lifespan
    calls `init_db()` with no argument: without the env var it would repoint the
    engine at `data/samadhaan.db` and the tests would run against the demo data.
    """
    monkeypatch.setenv("DATABASE_URL", database_url)
    store_db.dispose()
    store_db.init_db(database_url)
    # The context manager runs the lifespan (provider guard + init_db), which is
    # what a real deployment does; the URL is already pointed at a temp file.
    with TestClient(app) as active:
        yield active
    store_db.dispose()
