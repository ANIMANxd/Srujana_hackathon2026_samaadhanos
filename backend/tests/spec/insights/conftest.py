"""Fixtures for the v5 Customer book spec tests.

The book, its stats and the portfolio view all read from the store, so these
tests go through the HTTP API with a throwaway database per test: never
`data/samadhaan.db`. The app's lifespan runs (provider guard + `init_db`), the
same way a real deployment starts.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.store import db as store_db


@pytest.fixture()
def client(tmp_path, monkeypatch) -> Iterator[TestClient]:
    url = f"sqlite:///{tmp_path / 'spec-insights.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    store_db.dispose()
    store_db.init_db(url)
    with TestClient(app, raise_server_exceptions=False) as active:
        yield active
    store_db.dispose()
