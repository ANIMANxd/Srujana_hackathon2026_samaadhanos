"""Fixture-export tests (architecture.md section 11, `tests/contract`).

What they prove, per task B10:

- the export writes every preset's request + response **and** the five CASE-01
  artifact samples, each validated against its contract model before any file
  is written;
- the committed fixtures carry no `PLACEHOLDER_DATA`;
- a failing `tests/spec` makes the export **refuse** - nothing lands in the
  target folder at all - while a suite with no tests yet warns instead of
  pretending it was consulted;
- a response that does not validate, or a preset the engine refuses, aborts the
  whole run without writing;
- `make fixtures` really runs the export before it copies to `frontend/fixtures`;
- the committed samples are exactly what the code produces now (freshness).

Every test passes its own `tmp_path`: `export()` with the default path is never
called from a test, because a test that rewrote `contracts/fixtures` first
would make the freshness tests pass by accident.
"""

import json
import re
from pathlib import Path

import pytest

from backend.app.export_fixtures import (
    ARTIFACT_PRESET,
    FIXTURES,
    FixturesError,
    SpecStatus,
    export,
    spec_status,
)
from backend.app.main import PRESETS_DIR
from backend.app.schemas import (
    ArtifactKind,
    CaseEvaluationRequest,
    CaseEvaluationResponse,
)

ROOT = Path(__file__).resolve().parents[3]


def _preset_stems() -> list[str]:
    return sorted(path.stem for path in PRESETS_DIR.glob("*.json"))


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# --------------------------------------------------------------- writing ----


def test_export_writes_every_preset_and_everything_validates(tmp_path):
    result = export(tmp_path)
    stems = _preset_stems()
    assert stems, "no presets found"

    for stem in stems:
        assert f"{stem}.request.json" in result.written
        assert f"{stem}.response.json" in result.written

        request = json.loads(_read(tmp_path / f"{stem}.request.json"))
        CaseEvaluationRequest.model_validate(request)  # must not raise

        response = json.loads(_read(tmp_path / f"{stem}.response.json"))
        CaseEvaluationResponse.model_validate(response)  # must not raise
        # Acceptance: no placeholder warnings in anything the frontend will read.
        codes = {w["code"] for w in response.get("warnings", [])}
        assert "PLACEHOLDER_DATA" not in codes, f"{stem} carries PLACEHOLDER_DATA"

    assert result.spec.refused is False


def test_request_fixtures_are_the_preset_inputs(tmp_path):
    """A request fixture is the preset re-serialised, never a hand edit."""
    export(tmp_path)
    for stem in _preset_stems():
        preset = json.loads(_read(PRESETS_DIR / f"{stem}.json"))
        expected = CaseEvaluationRequest.model_validate(preset["request"])
        written = json.loads(_read(tmp_path / f"{stem}.request.json"))
        assert written == expected.model_dump(mode="json", by_alias=True)


def test_committed_fixtures_carry_no_placeholder_data():
    """The acceptance check on the files that ship, not just on new ones."""
    responses = sorted(FIXTURES.glob("*.response.json"))
    assert responses, "no committed response fixtures"
    for path in responses:
        payload = json.loads(_read(path))
        codes = {w["code"] for w in payload.get("warnings", [])}
        assert "PLACEHOLDER_DATA" not in codes, f"{path.name} is a placeholder"
        CaseEvaluationResponse.model_validate(payload)


# ---------------------------------------------------------- samples ----


def test_export_writes_the_five_case01_artifact_samples(tmp_path):
    result = export(tmp_path)
    expected_names = sorted(
        f"{ARTIFACT_PRESET}.{kind.value}.md" for kind in ArtifactKind
    )
    written_samples = sorted(name for name in result.written if name.endswith(".md"))
    assert written_samples == expected_names
    for name in expected_names:
        text = _read(tmp_path / name)
        assert text.startswith("# DRAFT"), f"{name} is not marked DRAFT"
        assert "not legal advice" in text.lower()
        assert "## Assumptions this draft was made under" in text

    # Each sample is really its own kind, not the same document five times.
    stage2 = _read(tmp_path / f"{ARTIFACT_PRESET}.STAGE2_CFO_MEMO.md")
    assert "### 1. Permanent loss" in stage2
    assert "Udyam registration" in stage2
    stage4 = _read(tmp_path / f"{ARTIFACT_PRESET}.STAGE4_EVIDENCE_PACK.md")
    assert "BSA s.63" in stage4 and "TEMPLATE" in stage4
    assert "to be confirmed against the live portal" in stage4
    stage1 = _read(tmp_path / f"{ARTIFACT_PRESET}.STAGE1_ACCEPTANCE_NOTE.md")
    assert "\u20b9" not in stage1, "the operational note carries no amount"


def test_committed_samples_are_exactly_what_the_code_produces(tmp_path):
    """Freshness: a stale sample fails here, the way a stale fixture does."""
    export(tmp_path)
    committed = sorted(FIXTURES.glob(f"{ARTIFACT_PRESET}.STAGE*.md"))
    assert committed, "no committed samples; run `make fixtures`"
    for path in committed:
        fresh = tmp_path / path.name
        assert fresh.exists(), f"{path.name} is no longer produced"
        assert _read(path) == _read(fresh), f"{path.name} is stale; run `make fixtures`"


def test_retired_sample_kinds_are_pruned(tmp_path):
    """A kind that stops being produced must not linger as a stale file."""
    export(tmp_path)
    stale = tmp_path / f"{ARTIFACT_PRESET}.STAGE9_RETIRED.md"
    stale.write_text("# DRAFT - old\n", encoding="utf-8")
    result = export(tmp_path)
    assert stale.name in result.pruned
    assert not stale.exists()


# ------------------------------------------------------------ refusals ----


def test_a_failing_spec_suite_refuses_and_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "backend.app.export_fixtures.spec_status",
        lambda: SpecStatus(returncode=1, output="2 failed, 10 passed"),
    )
    with pytest.raises(FixturesError) as excinfo:
        export(tmp_path)
    message = str(excinfo.value)
    assert "tests/spec is failing" in message
    assert "2 failed" in message
    assert list(tmp_path.iterdir()) == [], "a refusal must write nothing at all"


def test_a_spec_suite_with_no_tests_warns_and_proceeds(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        "backend.app.export_fixtures.spec_status",
        lambda: SpecStatus(returncode=5, output="no tests ran"),
    )
    result = export(tmp_path)
    assert result.written, "an empty suite must not block the export either"
    assert result.spec_empty is True
    assert "no tests ran" in capsys.readouterr().out


def test_a_response_that_does_not_validate_writes_nothing(tmp_path, monkeypatch):
    class FakeEvaluation:
        """What a broken serialiser would hand back: not a contract payload."""

        def model_dump(self, **kwargs):
            return {"case_id": "broken"}

    monkeypatch.setattr(
        "backend.app.export_fixtures.evaluate_case",
        lambda config, request: FakeEvaluation(),
    )
    with pytest.raises(FixturesError) as excinfo:
        export(tmp_path)
    assert "does not validate" in str(excinfo.value)
    assert list(tmp_path.iterdir()) == []


def test_a_preset_the_engine_refuses_writes_nothing(tmp_path, monkeypatch):
    def refuse(config, request):
        raise ValueError("NoEpochFound: no bank rate covers 2019-12-01")

    monkeypatch.setattr("backend.app.export_fixtures.evaluate_case", refuse)
    with pytest.raises(FixturesError) as excinfo:
        export(tmp_path)
    message = str(excinfo.value)
    assert "the engine could not evaluate it" in message
    assert "NoEpochFound" in message
    assert "nothing was written" in message
    assert list(tmp_path.iterdir()) == []


def test_spec_status_reports_the_current_repo_state():
    """The real guard, as the script runs it: refused is what stops a write."""
    status = spec_status()
    assert status.refused is False, f"the spec suite is red: {status.output[-500:]}"


def test_spec_status_reads_the_exit_code_of_a_real_pytest_run(tmp_path, monkeypatch):
    """The guard must actually run the suite and read what it said."""
    spec_dir = tmp_path / "spec"
    spec_dir.mkdir()
    passing = spec_dir / "test_passing.py"
    passing.write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    monkeypatch.setattr("backend.app.export_fixtures.SPEC_DIR", spec_dir)

    clean = spec_status()
    assert clean.returncode == 0 and clean.refused is False

    (spec_dir / "test_failing.py").write_text(
        "def test_broken():\n    assert False, 'the engine is wrong'\n",
        encoding="utf-8",
    )
    red = spec_status()
    assert red.refused is True
    assert "the engine is wrong" in red.output or "1 failed" in red.output

    passing.unlink()
    (spec_dir / "test_failing.py").unlink()
    empty = spec_status()
    assert empty.returncode is None and empty.refused is False


# --------------------------------------------------------- make wiring ----


def test_make_fixtures_runs_the_export_before_the_copy():
    """`make fixtures` must regenerate first; a copy alone would ship stale files."""
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    target = re.search(r"^fixtures:\n((?:\t[^\n]*\n)+)", makefile, re.MULTILINE)
    assert target, "the Makefile has no fixtures target"
    recipe = target.group(1)
    assert "backend.app.export_fixtures" in recipe, "fixtures does not regenerate"
    assert "frontend/fixtures" in recipe, "fixtures does not copy to the frontend"
    assert recipe.index("backend.app.export_fixtures") < recipe.index(
        "frontend/fixtures"
    )
