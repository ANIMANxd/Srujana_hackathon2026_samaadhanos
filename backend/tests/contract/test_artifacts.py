"""Artifact tests (architecture.md section 11, `tests/contract`).

What they prove, per task B8's acceptance: every kind generates for CASE-01 and
for the two blocked presets; the blocked presets explain why the stage is
unavailable instead of producing a half-draft; Stage 1 states no law; Stage 2
keeps the three cost lines separate and advisory; Stage 3 prices the offer with
the engine's settlement arithmetic; Stage 4 carries its four parts; and a PDF
failure degrades to markdown plus a warning.

These are **text-structure** tests on purpose: the snapshots store the markdown
with every digit replaced by `#`, so a snapshot can pin the shape of a document
but can never pin a legal value, and `make test` keeps passing when an engine
figure legitimately moves. Refresh a snapshot only after reviewing the diff:

    UPDATE_ARTIFACT_SNAPSHOTS=1 python -m pytest backend/tests/contract -q

No test here computes or asserts a legal number: document values are the
engine's, asserted only as "the figure the request sent appears" (for example
that the Udyam number is printed) or as structure.
"""

import base64
import difflib
import json
import os
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.schemas import (
    ArtifactKind,
    ArtifactResponse,
    CaseEvaluationResponse,
    OtherPressurePoint,
    Warning,
)
from backend.artifacts.stage2 import _disclosure_line
from backend.engine.buyer_cost import WARNING_UNVERIFIED_GATED_FEATURE

ROOT = Path(__file__).resolve().parents[3]
PRESETS = ROOT / "backend" / "presets"
FIXTURES = ROOT / "contracts" / "fixtures"
SNAPSHOTS = Path(__file__).resolve().parent / "snapshots"

KINDS = [kind.value for kind in ArtifactKind]
STAGE1_KINDS = [
    ArtifactKind.STAGE1_ACCEPTANCE_NOTE.value,
    ArtifactKind.STAGE1_BALANCE_CONFIRMATION.value,
]
# The two presets stopped at the gate (CQ-32); case_06 is the stretch preset
# with no delivery proof, which blocks Stage 4 through the readiness output.
BLOCKED_IDS = {"case_05a": "EXCLUDED_MEDIUM", "case_05b": "EXCLUDED_TRADER"}
CASE_01 = "case_01"
NO_DELIVERY_PROOF_ID = "case_06"

# Words a Stage 1 note must never carry: that stage is operational (task B8).
LAW_TOKENS = [
    "msmed",
    "statutory",
    "bank rate",
    "interest",
    "43b",
    "limitation",
    "tribunal",
    "s.15",
    "s.16",
    "section",
    " act ",
    "odr portal",
]

# Things an advisory memo must not say (advisory tone, no threats).
THREAT_TOKENS = [
    "last warning",
    "we will file",
    "we shall file",
    "legal action",
    "regulatory action",
    "we will report",
    "will be reported",
    "final notice",
    "unless you pay",
]

client = TestClient(app)


# ------------------------------------------------------------- helpers ----


def _preset_request(preset_id: str) -> dict:
    data = json.loads((PRESETS / f"{preset_id}.json").read_text(encoding="utf-8"))
    return data["request"]


def _generate(
    kind: str, preset_id: str, settlement: dict | None = None
) -> ArtifactResponse:
    payload: dict = {"kind": kind, "request": _preset_request(preset_id)}
    if settlement is not None:
        payload["settlement"] = settlement
    response = client.post("/api/v1/generate-artifact", json=payload)
    assert response.status_code == 200, response.text[:600]
    return ArtifactResponse.model_validate(response.json())


def _evaluation(preset_id: str) -> CaseEvaluationResponse:
    """The recorded evaluation, for unit-testing one template helper."""
    path = FIXTURES / f"{preset_id}.response.json"
    return CaseEvaluationResponse.model_validate(
        json.loads(path.read_text(encoding="utf-8"))
    )


def _redact(markdown: str) -> str:
    """Every digit becomes `#`: structure without legal values."""
    return re.sub(r"\d", "#", markdown)


# --------------------------------------------------- CASE-01, all kinds ----


@pytest.mark.parametrize("kind", KINDS)
def test_every_kind_generates_for_case_01(kind: str):
    result = _generate(kind, CASE_01)
    assert result.contract_version == "1.0"
    assert result.kind == kind
    assert result.markdown.strip()

    # DRAFT label, assumptions block, not-legal-advice footer on every artifact.
    assert "DRAFT" in result.markdown
    assert "## Assumptions this draft was made under" in result.markdown
    assert "not legal advice" in result.markdown.lower()
    assert result.markdown.rstrip().endswith("draft.*")

    # Filenames slug the case id plus the kind, and markdown/PDF names pair up.
    assert result.filename == f"{CASE_01}_{kind.lower()}.md"
    if result.pdf_base64 is None:
        assert result.pdf_filename is None
        assert any(w.code == "PDF_RENDER_FAILED" for w in result.warnings)
    else:
        assert result.pdf_filename == f"{CASE_01}_{kind.lower()}.pdf"
        assert base64.b64decode(result.pdf_base64).startswith(b"%PDF-")


@pytest.mark.parametrize("kind", KINDS)
def test_generation_is_markdown_deterministic(kind: str):
    """No clock is read: the same request produces the same document twice."""
    first = _generate(kind, CASE_01)
    second = _generate(kind, CASE_01)
    assert first.markdown == second.markdown
    assert first.filename == second.filename


# ---------------------------------------------------------- blocked cases ----


@pytest.mark.parametrize("preset_id", sorted(BLOCKED_IDS))
@pytest.mark.parametrize("kind", KINDS)
def test_blocked_cases_explain_why_the_stage_is_unavailable(preset_id: str, kind: str):
    """Acceptance: blocked presets generate, and their output explains the block."""
    markdown = _generate(kind, preset_id).markdown
    assert "## Why this stage is unavailable" in markdown
    assert "not available" in markdown.lower()
    assert (
        f"The eligibility gate stopped this case with status {BLOCKED_IDS[preset_id]}."
        in markdown
    )
    # The engine's own check detail and remedy are quoted, not paraphrased here.
    assert "does not predict an outcome" in markdown
    # A blocked case shows no money: the blocks are absent, not zero.
    assert "\u20b9" not in markdown
    # Still a draft, still not legal advice.
    assert "DRAFT" in markdown
    assert "not legal advice" in markdown.lower()


def test_no_delivery_proof_blocks_stage_4_with_the_readiness_reason():
    """case_06 has dates but no delivery proof: Stage 4 says why, quoting readiness."""
    markdown = _generate(
        ArtifactKind.STAGE4_EVIDENCE_PACK.value, NO_DELIVERY_PROOF_ID
    ).markdown
    assert "## Why this stage is unavailable" in markdown
    assert "delivery proof" in markdown.lower()
    assert "stage 4" in markdown.lower()


# -------------------------------------------------------------- Stage 1 ----


@pytest.mark.parametrize("kind", STAGE1_KINDS)
def test_stage1_drafts_state_no_law(kind: str):
    """Stage 1 is warm and operational: no statute, no rate, no entitlement."""
    markdown = _generate(kind, CASE_01).markdown.lower()
    found = [token for token in LAW_TOKENS if token in markdown]
    assert not found, f"Stage 1 output mentioned law: {found}"
    # Warm, addressed, and it asks rather than demands.
    assert "dear " in markdown
    assert "with thanks," in markdown


def test_acceptance_note_carries_no_amount():
    """The note asks for an acknowledgement; the money lives in the other draft."""
    markdown = _generate(ArtifactKind.STAGE1_ACCEPTANCE_NOTE.value, CASE_01).markdown
    assert "\u20b9" not in markdown


def test_balance_confirmation_asks_for_the_amount_and_a_signature():
    markdown = _generate(
        ArtifactKind.STAGE1_BALANCE_CONFIRMATION.value, CASE_01
    ).markdown
    assert "Outstanding amount as on" in markdown
    assert "\u20b9" in markdown
    assert "Signature:" in markdown
    assert "Amount confirmed:" in markdown


def test_acceptance_note_asks_for_receipt_when_delivery_proof_is_missing():
    """The Stage 1 cure note (architecture 6.2) asks instead of asserting a date."""
    markdown = _generate(
        ArtifactKind.STAGE1_ACCEPTANCE_NOTE.value, NO_DELIVERY_PROOF_ID
    ).markdown
    assert "not in our file yet" in markdown
    assert "confirm that the goods reached you" in markdown


# -------------------------------------------------------------- Stage 2 ----


def test_stage2_memo_keeps_three_lines_separate_and_advisory():
    markdown = _generate(ArtifactKind.STAGE2_CFO_MEMO.value, CASE_01).markdown
    for heading in ("### 1. Permanent loss", "### 2. Deferral", "### 3. Disclosure"):
        assert heading in markdown
    assert "not added into one number" in markdown
    # Advisory, not threatening.
    found = [token for token in THREAT_TOKENS if token in markdown.lower()]
    assert not found, f"memo sounded like a threat: {found}"
    assert "What we would like to agree" in markdown
    # The supplier's Udyam number is in the memo, from the request inputs.
    assert _preset_request(CASE_01)["supplier"]["udyam_number"] in markdown
    # The disclosure line carries its verification status, never a bare claim.
    assert "not yet checked against a captured source" in markdown
    # Open points stay visible rather than hidden (principle 6).
    assert "## Open points from this calculation" in markdown


def test_gated_pressure_points_appear_only_when_verified():
    """The rule from task B8, unit-tested on the line builder itself."""
    buyer_cost = _evaluation(CASE_01).buyer_cost
    assert buyer_cost is not None
    with_points = buyer_cost.model_copy(
        update={
            "other_pressure_points": [
                OtherPressurePoint(id="gst_itc_180d", text="A gated point.")
            ]
        }
    )
    flagged = Warning(
        code=WARNING_UNVERIFIED_GATED_FEATURE,
        severity="WARN",
        text="These buyer pressure points are switched on but their rule is still open.",
    )
    # Flagged as unverified -> left out of the memo body, and the memo says so.
    excluded = _disclosure_line(with_points, [flagged])
    assert "A gated point." not in excluded
    assert "left out here" in excluded
    # Not flagged -> shown, because nothing marks it unverified.
    shown = _disclosure_line(with_points, [])
    assert "A gated point." in shown


# -------------------------------------------------------------- Stage 3 ----


def test_stage3_term_sheet_prices_the_offer():
    markdown = _generate(
        ArtifactKind.STAGE3_SETTLEMENT_TERMSHEET.value, CASE_01
    ).markdown
    assert "## The claim" in markdown
    assert "## Proposed terms" in markdown
    assert "## Agreement (draft \u2014 unsigned)" in markdown
    assert "Single payment (today)" in markdown
    # The buyer-cost lines never become sections of a term sheet (golden rule 8).
    assert "## What the delay is costing you" not in markdown
    assert "### 1. Permanent loss" not in markdown


def test_stage3_accepts_negotiated_terms_and_echoes_them():
    terms = {"upfront_pct": "50", "waiver_pct": "20", "days_to_second_payment": 30}
    markdown = _generate(
        ArtifactKind.STAGE3_SETTLEMENT_TERMSHEET.value, CASE_01, settlement=terms
    ).markdown
    assert "proposes 20% of the outstanding interest waived" in markdown
    assert "after 30 day(s)" in markdown
    assert "Payment 1 of 2, day 0" in markdown
    assert "Payment 2 of 2, day 30" in markdown


def test_stage3_refuses_out_of_range_terms_with_the_error_envelope():
    payload = {
        "kind": ArtifactKind.STAGE3_SETTLEMENT_TERMSHEET.value,
        "request": _preset_request(CASE_01),
        "settlement": {
            "upfront_pct": "50",
            "waiver_pct": "150",
            "days_to_second_payment": 30,
        },
    }
    response = client.post("/api/v1/generate-artifact", json=payload)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "RULE_VIOLATION"


# -------------------------------------------------------------- Stage 4 ----


def test_stage4_pack_carries_its_four_parts():
    markdown = _generate(ArtifactKind.STAGE4_EVIDENCE_PACK.value, CASE_01).markdown
    # 1. Portal fields: no field name until V10 is captured.
    assert "## Portal fields" in markdown
    assert "to be confirmed against the live portal" in markdown
    # 2. Chronological evidence ledger, plus the documents held.
    assert "## Evidence in date order" in markdown
    assert "### Documents in this case" in markdown
    # 3. Interest calculation sheet, printed from the engine's rows.
    assert "## Interest calculation sheet" in markdown
    assert "| Row | From | To | Opening | Interest |" in markdown
    # 4. The certificate, unmistakably a template.
    assert "BSA s.63) \u2014 TEMPLATE" in markdown
    assert "person responsible" in markdown
    assert "not an issued certificate" in markdown
    assert "Signature:" in markdown


def test_stage4_chronology_is_in_date_order():
    markdown = _generate(ArtifactKind.STAGE4_EVIDENCE_PACK.value, CASE_01).markdown
    section = markdown.split("## Evidence in date order")[1].split("### Documents")[0]
    dates = re.findall(r"^\| (\d{4}-\d{2}-\d{2}) \|", section, flags=re.MULTILINE)
    assert len(dates) >= 8, "the ledger should carry the case's dated events"
    assert dates == sorted(dates), "the ledger must be chronological"


def test_stage4_lists_documents_the_case_does_not_hold():
    markdown = _generate(ArtifactKind.STAGE4_EVIDENCE_PACK.value, CASE_01).markdown
    assert "not in this case" in markdown


# ------------------------------------------------------ request handling ----


def test_unknown_kind_is_rejected_with_the_error_envelope():
    payload = {"kind": "STAGE9_SOMETHING", "request": _preset_request(CASE_01)}
    response = client.post("/api/v1/generate-artifact", json=payload)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_malformed_request_is_rejected():
    payload = {"kind": ArtifactKind.STAGE2_CFO_MEMO.value}
    response = client.post("/api/v1/generate-artifact", json=payload)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_generate_artifact_is_in_the_committed_contract():
    """Section 9.4: the exported contract must carry the new path and shapes."""
    committed = json.loads(
        (ROOT / "contracts" / "openapi.json").read_text(encoding="utf-8")
    )
    assert "/api/v1/generate-artifact" in committed["paths"]
    schema = committed["components"]["schemas"]["ArtifactResponse"]
    assert {"kind", "filename", "markdown"} <= set(schema["required"])
    kinds = committed["components"]["schemas"]["ArtifactKind"]["enum"]
    assert kinds == KINDS


def test_pdf_failure_degrades_to_markdown_with_a_warning(monkeypatch):
    """Task B8: PDF fails -> markdown only, plus a warning; never a 500."""
    from backend.artifacts import generate as generate_module

    def explode(markdown: str, *, title: str, case_id: str) -> bytes:
        raise RuntimeError("simulated reportlab failure")

    monkeypatch.setattr(generate_module, "render_pdf", explode)
    result = _generate(ArtifactKind.STAGE4_EVIDENCE_PACK.value, CASE_01)
    assert result.markdown.strip()
    assert result.pdf_base64 is None
    assert result.pdf_filename is None
    warning = next(w for w in result.warnings if w.code == "PDF_RENDER_FAILED")
    assert "simulated reportlab failure" in warning.text
    assert "markdown draft is complete" in warning.text


# ------------------------------------------------------------- snapshots ----


@pytest.mark.parametrize("preset_id", [CASE_01, *sorted(BLOCKED_IDS)])
@pytest.mark.parametrize("kind", KINDS)
def test_structure_snapshot(preset_id: str, kind: str):
    """The document's shape, digit-free, against the recorded snapshot."""
    redacted = _redact(_generate(kind, preset_id).markdown)
    path = SNAPSHOTS / f"{preset_id}__{kind}.txt"

    if os.environ.get("UPDATE_ARTIFACT_SNAPSHOTS"):
        SNAPSHOTS.mkdir(parents=True, exist_ok=True)
        path.write_text(redacted, encoding="utf-8", newline="\n")

    assert path.exists(), (
        f"no snapshot for {preset_id}/{kind}; run "
        "UPDATE_ARTIFACT_SNAPSHOTS=1 python -m pytest backend/tests/contract -q "
        "and review the diff"
    )
    expected = path.read_text(encoding="utf-8")
    if redacted == expected:
        return
    diff = "\n".join(
        list(
            difflib.unified_diff(
                expected.splitlines(),
                redacted.splitlines(),
                fromfile=str(path.name),
                tofile="regenerated",
                lineterm="",
            )
        )[:60]
    )
    pytest.fail(
        f"snapshot drifted for {preset_id}/{kind}:\n{diff}\n"
        "Review the change; if it is intended, refresh with UPDATE_ARTIFACT_SNAPSHOTS=1."
    )
