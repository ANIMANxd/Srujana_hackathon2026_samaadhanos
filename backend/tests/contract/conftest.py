"""Contract-suite configuration: the judge marker and its label in every run.

The five rehearsed judge manipulations are marked `judge` and grouped in
`TestJudgeManipulations`, so a single `make test` run names them - the report
header below prints on every run, and `-m judge` selects only that group.

The suite also needs a v4 store: the case routes are declared in the contract and
must be called for real, and a bare `TestClient` (no context manager) never runs the
app's lifespan, so `init_db()` here is what creates the tables. The database is a
per-run temporary file, never `data/samadhaan.db`, so a test run cannot touch demo
data.
"""

from __future__ import annotations

import os
import tempfile

import pytest

_STORE_DIR = tempfile.mkdtemp(prefix="samadhaan-contract-")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_STORE_DIR}/contract.db")


@pytest.fixture(scope="session", autouse=True)
def _v4_store() -> None:
    """Create the store schema once for the whole contract suite."""
    from backend.store import db as store_db

    store_db.dispose()
    store_db.init_db()
    yield
    store_db.dispose()


def pytest_configure(config) -> None:
    config.addinivalue_line(
        "markers",
        "judge: one of the five rehearsed judge manipulations (architecture section 11)",
    )


def pytest_report_header(config) -> str:
    return (
        "judge manipulations: 5 rehearsals in "
        "backend/tests/contract/test_judge_manipulations.py::TestJudgeManipulations "
        "(select with -m judge)"
    )


def pytest_terminal_summary(terminalreporter, exitstatus, config) -> None:
    """Label the judge group in every run, including a quiet `make test`.

    pytest hides report headers under `-q`, so the group is announced in the
    terminal summary instead, with its own pass/fail counts. (pytest 9 renamed
    this hook from `pytest_report_terminal_summary`.)
    """
    nodeids = []
    for outcome in ("passed", "failed", "skipped", "error"):
        for item in terminalreporter.stats.get(outcome, []):
            nodeid = getattr(item, "nodeid", "")
            if "TestJudgeManipulations" in nodeid:
                nodeids.append((outcome, nodeid))
    if not nodeids:
        return
    counts = {}
    for outcome, _ in nodeids:
        counts[outcome] = counts.get(outcome, 0) + 1
    breakdown = ", ".join(
        f"{count} {outcome}" for outcome, count in sorted(counts.items())
    )
    terminalreporter.write_line(
        "judge manipulations: 5 rehearsals in "
        f"backend/tests/contract/test_judge_manipulations.py::TestJudgeManipulations "
        f"- {breakdown} (select with -m judge)"
    )
