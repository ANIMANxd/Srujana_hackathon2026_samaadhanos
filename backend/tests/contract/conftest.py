"""Contract-suite configuration: the judge marker and its label in every run.

The five rehearsed judge manipulations are marked `judge` and grouped in
`TestJudgeManipulations`, so a single `make test` run names them - the report
header below prints on every run, and `-m judge` selects only that group.
"""


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
