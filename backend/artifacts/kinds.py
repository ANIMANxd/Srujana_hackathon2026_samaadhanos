"""The artifact kinds this product can produce, and the stage each belongs to.

`ArtifactKind` lives here rather than in `backend/app/schemas.py` so the route
and the templates read one list of names; the contract imports it from this
module (architecture.md section 8.1 names `POST /generate-artifact`).

Stage 1 has two drafts: the acceptance note (operational, no law in it) and the
balance-confirmation request (asks for the outstanding amount and a signature).
"""

from enum import Enum


class ArtifactKind(str, Enum):
    STAGE1_ACCEPTANCE_NOTE = "STAGE1_ACCEPTANCE_NOTE"
    STAGE1_BALANCE_CONFIRMATION = "STAGE1_BALANCE_CONFIRMATION"
    STAGE2_CFO_MEMO = "STAGE2_CFO_MEMO"
    STAGE3_SETTLEMENT_TERMSHEET = "STAGE3_SETTLEMENT_TERMSHEET"
    STAGE4_EVIDENCE_PACK = "STAGE4_EVIDENCE_PACK"


# Which escalation stage each kind belongs to, for headings and explanations.
STAGE_BY_KIND: dict[ArtifactKind, int] = {
    ArtifactKind.STAGE1_ACCEPTANCE_NOTE: 1,
    ArtifactKind.STAGE1_BALANCE_CONFIRMATION: 1,
    ArtifactKind.STAGE2_CFO_MEMO: 2,
    ArtifactKind.STAGE3_SETTLEMENT_TERMSHEET: 3,
    ArtifactKind.STAGE4_EVIDENCE_PACK: 4,
}

# Human names used in headings and in the "why unavailable" explanation.
KIND_TITLES: dict[ArtifactKind, str] = {
    ArtifactKind.STAGE1_ACCEPTANCE_NOTE: "acceptance note",
    ArtifactKind.STAGE1_BALANCE_CONFIRMATION: "balance confirmation request",
    ArtifactKind.STAGE2_CFO_MEMO: "note for the buyer's finance team",
    ArtifactKind.STAGE3_SETTLEMENT_TERMSHEET: "settlement term sheet",
    ArtifactKind.STAGE4_EVIDENCE_PACK: "evidence pack",
}
