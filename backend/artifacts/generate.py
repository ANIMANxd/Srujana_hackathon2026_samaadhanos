"""Turn a case evaluation into a draft artifact: markdown first, PDF when it works.

`build_artifact` is the whole entry point. It decides availability, asks the
right template to write the draft, stamps the filename, and then tries the PDF.
If reportlab cannot render it, the markdown comes back alone with a warning -
the draft is never lost with the PDF (task B8).

The templates themselves compute nothing: they print the evaluation's figures
and the request's inputs. The only arithmetic in an artifact happens in the
engine (`settlement.evaluate_settlement` for Stage 3), and this module only
calls it.
"""

from __future__ import annotations

import base64
import re
from dataclasses import dataclass, field

from backend.app.schemas import (
    CaseEvaluationRequest,
    CaseEvaluationResponse,
    SettlementTerms,
)
from backend.artifacts.availability import availability
from backend.artifacts.kinds import ArtifactKind, KIND_TITLES, STAGE_BY_KIND
from backend.artifacts.pdf import render_pdf
from backend.artifacts.stage1 import acceptance_note, balance_confirmation
from backend.artifacts.stage2 import cfo_memo
from backend.artifacts.stage3 import settlement_termsheet
from backend.artifacts.stage4 import evidence_pack
from backend.artifacts.unavailable import render_unavailable

PDF_WARNING_CODE = "PDF_RENDER_FAILED"

# Filename safety: a case id comes from a request, and the name is offered to a
# browser as a download, so it is reduced to a plain slug.
_SLUG = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass
class ArtifactResult:
    """What the route serialises: the markdown, plus a PDF when it rendered."""

    kind: ArtifactKind
    filename: str
    markdown: str
    pdf_base64: str | None = None
    pdf_filename: str | None = None
    warnings: list[dict[str, str]] = field(default_factory=list)


def build_artifact(
    *,
    kind: ArtifactKind | str,
    request: CaseEvaluationRequest,
    evaluation: CaseEvaluationResponse,
    settlement: SettlementTerms | None = None,
) -> ArtifactResult:
    """Draft `kind` for this case. Always returns markdown; the PDF is optional."""
    resolved = ArtifactKind(kind)
    avail = availability(resolved, evaluation, request)
    if avail.available:
        markdown = _render(resolved, request, evaluation, settlement)
    else:
        markdown = render_unavailable(request, evaluation, avail)

    slug = _SLUG.sub("_", evaluation.case_id).strip("_") or "case"
    stem = f"{slug}_{resolved.value.lower()}"
    filename = f"{stem}.md"

    result = ArtifactResult(kind=resolved, filename=filename, markdown=markdown)
    title = f"DRAFT - Stage {STAGE_BY_KIND[resolved]} {KIND_TITLES[resolved]} - {evaluation.case_id}"
    try:
        pdf_bytes = render_pdf(markdown, title=title, case_id=evaluation.case_id)
    except Exception as exc:  # noqa: BLE001 - any render failure degrades to markdown
        result.warnings.append(
            {
                "code": PDF_WARNING_CODE,
                "severity": "WARN",
                "text": (
                    "The PDF could not be rendered "
                    f"({type(exc).__name__}: {exc}). The markdown draft is complete and "
                    "is returned instead, so nothing from the draft was lost."
                ),
            }
        )
    else:
        result.pdf_base64 = base64.b64encode(pdf_bytes).decode("ascii")
        result.pdf_filename = f"{stem}.pdf"
    return result


def _render(
    kind: ArtifactKind,
    request: CaseEvaluationRequest,
    evaluation: CaseEvaluationResponse,
    settlement: SettlementTerms | None,
) -> str:
    """Dispatch to the stage template. Availability was checked by the caller."""
    if kind == ArtifactKind.STAGE1_ACCEPTANCE_NOTE:
        return acceptance_note(request, evaluation)
    if kind == ArtifactKind.STAGE1_BALANCE_CONFIRMATION:
        return balance_confirmation(request, evaluation)
    if kind == ArtifactKind.STAGE2_CFO_MEMO:
        return cfo_memo(request, evaluation)
    if kind == ArtifactKind.STAGE3_SETTLEMENT_TERMSHEET:
        return settlement_termsheet(request, evaluation, settlement)
    if kind == ArtifactKind.STAGE4_EVIDENCE_PACK:
        return evidence_pack(request, evaluation)
    raise ValueError(f"Unknown artifact kind: {kind!r}")
