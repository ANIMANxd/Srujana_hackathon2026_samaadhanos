"""Generate contract fixtures from the live models and the live engine.

Run: `make fixtures` (regenerates, then copies everything to `frontend/fixtures`),
or `python -m backend.app.export_fixtures` / `make contract-fixtures`.

Writes, for every preset:

    contracts/fixtures/<preset>.request.json    the preset's input, re-validated
    contracts/fixtures/<preset>.response.json   the engine's own evaluation

plus the artifact samples for CASE-01, one file per kind:

    contracts/fixtures/case_01.<KIND>.md

Nothing here is hand-typed (golden rule 7 and 12): a request comes from its
preset file, a response from `evaluate_case`, a sample from `build_artifact`
over that same evaluation. Three gates protect the folder, in this order:

1. **tests/spec must not be failing.** The spec suite runs first; if it fails,
   `FixturesError` is raised before a single byte is written, so the committed
   fixtures stay as they were. No spec tests yet counts as "nothing to run" -
   a warning, not a refusal, because refusing would freeze the folder too.
2. **Every payload must validate.** Each request, response and artifact
   response is round-tripped through its contract model, and a payload that
   changes when re-serialised is treated as a failure (it would mean the
   committed file is not what the model says it is).
3. **Nothing is written until everything built.** One broken preset or one
   unbuildable sample aborts the whole export with the list of problems.

The PDF bytes `build_artifact` returns are deliberately not stored: a sample is
the markdown a human can diff, and the PDF regenerates from it byte-for-byte
(reportlab runs with `invariant=1`).
"""

import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from backend.app.config_loader import load_config
from backend.app.main import PRESETS_DIR, _read_json
from backend.app.schemas import (
    CONTRACT_VERSION,
    ArtifactKind,
    ArtifactResponse,
    CaseEvaluationRequest,
    CaseEvaluationResponse,
    Warning,
)
from backend.artifacts.generate import build_artifact
from backend.engine.config import ConfigError, StatuteConfig
from backend.engine.evaluate import evaluate_case

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "contracts" / "fixtures"
SPEC_DIR = ROOT / "backend" / "tests" / "spec"

# The preset whose artifacts are sampled: the demo case the frontend and the
# judges read first (task: "artifact samples for CASE-01").
ARTIFACT_PRESET = "case_01"

# Generous, because a spec suite may grow: a slow suite must not hang the
# export, and timing out counts as "could not verify" = do not overwrite.
SPEC_TIMEOUT_SECONDS = 600

# How much of a failing spec run is echoed back in the refusal message.
SPEC_TAIL_CHARS = 3000


class FixturesError(RuntimeError):
    """The export refused to write. The fixtures on disk are untouched."""


@dataclass(frozen=True)
class SpecStatus:
    """What `tests/spec` did when it was run just now (or why it was not)."""

    returncode: int | None
    output: str

    @property
    def refused(self) -> bool:
        """Anything but a clean run or a no-tests run: do not overwrite."""
        return self.returncode not in (None, 0, 5)

    @property
    def is_empty(self) -> bool:
        """The guard had nothing to check - say so rather than look like a pass."""
        return self.returncode in (None, 5)


@dataclass(frozen=True)
class ExportResult:
    written: list[str] = field(default_factory=list)
    pruned: list[str] = field(default_factory=list)
    spec: SpecStatus = SpecStatus(returncode=None, output="")

    @property
    def spec_empty(self) -> bool:
        return self.spec.is_empty


def spec_status() -> SpecStatus:
    """Run the spec suite exactly as `make test` would, and report it.

    Never raises: a suite that cannot even be started counts as failing, since
    the question is only "may I overwrite the recorded answers?".
    """
    if not SPEC_DIR.is_dir() or not any(SPEC_DIR.glob("test_*.py")):
        return SpecStatus(
            returncode=None, output="backend/tests/spec has no test files yet"
        )
    try:
        # The repo-relative suite name when it lives here, so the run sees the
        # same rootdir and imports as `make test` does; an absolute path when a
        # test points the guard somewhere else.
        try:
            target = str(SPEC_DIR.relative_to(ROOT))
        except ValueError:
            target = str(SPEC_DIR)
        completed = subprocess.run(
            [sys.executable, "-m", "pytest", target, "-q"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=SPEC_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return SpecStatus(returncode=1, output=f"tests/spec could not be run: {exc}")
    output = (completed.stdout or "") + (completed.stderr or "")
    return SpecStatus(returncode=completed.returncode, output=output[-SPEC_TAIL_CHARS:])


def _dump(model) -> str:
    return json.dumps(model.model_dump(mode="json", by_alias=True), indent=2) + "\n"


def _validate(model_cls, text: str, label: str) -> None:
    """Round-trip `text` through `model_cls`, failing on drift as well as errors."""
    try:
        validated = model_cls.model_validate(json.loads(text))
    except ValidationError as exc:
        raise FixturesError(
            f"{label} does not validate against {model_cls.__name__}: {exc}"
        ) from exc
    if _dump(validated) != text:
        raise FixturesError(
            f"{label} changes when it is re-read through {model_cls.__name__}: the file "
            "on disk is not what the contract model says it is."
        )


def _samples(stem: str, request, evaluation) -> tuple[dict[str, str], list[str]]:
    """Build every artifact kind for one preset and validate each response.

    Returns the file contents keyed by `<preset>.<KIND>.md`, plus any warnings
    the builds raised (a PDF failure, for instance): warnings are printed, not
    treated as a failure, because a draft whose PDF would not render is still a
    valid draft - but a silently committed one would be a surprise.
    """
    files: dict[str, str] = {}
    notices: list[str] = []
    for kind in ArtifactKind:
        built = build_artifact(
            kind=kind, request=request, evaluation=evaluation, settlement=None
        )
        response = ArtifactResponse(
            contract_version=CONTRACT_VERSION,
            kind=kind,
            filename=built.filename,
            markdown=built.markdown,
            pdf_base64=built.pdf_base64,
            pdf_filename=built.pdf_filename,
            warnings=[Warning.model_validate(w) for w in built.warnings],
        )
        _validate(ArtifactResponse, _dump(response), f"{stem} sample {kind.value}")
        if not built.markdown.lstrip().startswith("# DRAFT"):
            raise FixturesError(
                f"{stem} sample {kind.value} is not marked DRAFT; a sample must be the "
                "draft the endpoint returns."
            )
        files[f"{stem}.{kind.value}.md"] = built.markdown.rstrip("\n") + "\n"
        notices.extend(f"{kind.value}: {w['code']}" for w in built.warnings)
    return files, notices


def _prune_stale_samples(fixtures_dir: Path, keep: set[str]) -> list[str]:
    """Remove artifact samples this run no longer produces (a retired kind)."""
    removed = []
    for path in sorted(fixtures_dir.glob("*.STAGE*.md")):
        if path.name not in keep:
            path.unlink()
            removed.append(path.name)
    return removed


def export(fixtures_dir: Path = FIXTURES) -> ExportResult:
    """Regenerate every fixture and sample. Raises `FixturesError` on refusal."""
    spec = (
        spec_status()
    )  # gate 1: never overwrite recorded answers while the spec is red
    if spec.refused:
        raise FixturesError(
            "tests/spec is failing, so nothing was overwritten:\n"
            f"{spec.output.strip()[-SPEC_TAIL_CHARS:]}"
        )

    try:
        config = StatuteConfig.from_dict(load_config())
    except ConfigError as exc:
        raise FixturesError(f"the statute config could not be loaded: {exc}") from exc

    # gate 3: build and validate everything first, write only at the end.
    pairs: dict[str, tuple[str, str]] = {}
    models: dict[str, tuple[CaseEvaluationRequest, CaseEvaluationResponse]] = {}
    errors: list[str] = []
    for preset in sorted(PRESETS_DIR.glob("*.json")):
        stem = preset.stem
        try:
            data = _read_json(preset)
            request = CaseEvaluationRequest.model_validate(data.get("request", data))
            try:
                response = evaluate_case(config, request)
            except ValueError as exc:  # an engine rule violation: plain English
                raise FixturesError(f"the engine could not evaluate it: {exc}") from exc
            request_text = _dump(request)
            response_text = _dump(response)
            _validate(CaseEvaluationRequest, request_text, f"{stem}.request.json")
            _validate(CaseEvaluationResponse, response_text, f"{stem}.response.json")
        except FixturesError as exc:
            errors.append(f"{stem}: {exc}")
            continue
        pairs[stem] = (request_text, response_text)
        models[stem] = (request, response)

    samples: dict[str, str] = {}
    notices: list[str] = []
    if ARTIFACT_PRESET in models:
        try:
            request, evaluation = models[ARTIFACT_PRESET]
            samples, notices = _samples(ARTIFACT_PRESET, request, evaluation)
        except FixturesError as exc:
            errors.append(f"{ARTIFACT_PRESET} artifacts: {exc}")

    if errors:
        raise FixturesError(
            "nothing was written; "
            + f"{len(errors)} problem(s):\n- "
            + "\n- ".join(errors)
        )

    # ---- everything validated: now, and only now, touch the folder ----
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for stem, (request_text, response_text) in sorted(pairs.items()):
        (fixtures_dir / f"{stem}.request.json").write_text(
            request_text, encoding="utf-8"
        )
        (fixtures_dir / f"{stem}.response.json").write_text(
            response_text, encoding="utf-8"
        )
        written.extend([f"{stem}.request.json", f"{stem}.response.json"])
    for name, text in sorted(samples.items()):
        (fixtures_dir / name).write_text(text, encoding="utf-8")
        written.append(name)
    pruned = _prune_stale_samples(fixtures_dir, keep=set(samples))

    for notice in notices:
        print(f"NOTE: sample build reported {notice}")
    if spec.is_empty:
        print(
            "WARNING: "
            f"{spec.output.strip()} - the spec guard had nothing to run, so nothing "
            "stood between an engine change and this overwrite."
        )
    return ExportResult(written=written, pruned=pruned, spec=spec)


if __name__ == "__main__":
    try:
        result = export()
    except FixturesError as exc:
        print(f"FIXTURES NOT WRITTEN: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    for name in result.written:
        print(f"wrote {name}")
    for name in result.pruned:
        print(f"removed stale {name}")
    if not result.spec_empty:
        print("tests/spec passed - fixtures regenerated from the engine")
