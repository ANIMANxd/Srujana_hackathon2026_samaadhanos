// Presentation selections over engine output. These choose WHICH engine value
// to show and how to label it; they never compute a legal value (golden rule 6).

import type {
  CaseRequest,
  CaseResponse,
  Defense,
  EvidenceKind,
  Financials,
  JurisdictionStatus,
  RateSegment,
  Stage,
} from "./types";

export type Tone = "ok" | "warn" | "block" | "info";

export const PLACEHOLDER_CODE = "PLACEHOLDER_DATA";
export const GRN_WARNING_CODE = "GRN_MISSING_DEEMED_ACCEPTANCE";

export function isPlaceholder(res: CaseResponse | null): boolean {
  return Boolean(res?.warnings.some((w) => w.code === PLACEHOLDER_CODE));
}

export function eligibilityTone(status: JurisdictionStatus): Tone {
  if (status === "ELIGIBLE") return "ok";
  if (status === "INSUFFICIENT_DATA") return "warn";
  return "block";
}

const HARD_BLOCKS: JurisdictionStatus[] = ["BARRED_SILPI", "EXCLUDED_TRADER", "EXCLUDED_MEDIUM"];

/**
 * The "Not covered" screen replaces the case screen for hard gate blocks only.
 * The engine nulls the money blocks for exactly these statuses; INSUFFICIENT_DATA
 * keeps computing (CQ-33), and a case with no delivery proof has no money yet
 * but is not "not covered", so both stay on the case screen.
 */
export function isNotCovered(res: CaseResponse): boolean {
  return HARD_BLOCKS.includes(res.jurisdiction.status);
}

/** The engine's recommended stage, kept within the 4-step ladder. */
export function currentStage(res: CaseResponse): Stage {
  const n = res.evidence_readiness.recommended_stage;
  return (n >= 1 && n <= 4 ? n : 1) as Stage;
}

export function isStageBlocked(res: CaseResponse, stage: Stage): boolean {
  return res.evidence_readiness.blocked_stages.includes(stage);
}

/** The defense to surface on the guidance card: at-risk first, then open, then strong. */
export function topDefense(defenses: Defense[]): Defense | null {
  return (
    defenses.find((d) => d.status === "AT_RISK") ??
    defenses.find((d) => d.status === "OPEN_QUESTION") ??
    defenses[0] ??
    null
  );
}

/** The rate segment in force at the calculation date (the engine lists them in order). */
export function latestSegment(fin: Financials | null): RateSegment | null {
  if (!fin || fin.rate_segments.length === 0) return null;
  return fin.rate_segments[fin.rate_segments.length - 1];
}

export function evidencePresent(req: CaseRequest | null, kind: EvidenceKind): boolean {
  return Boolean(req?.evidence.items.some((i) => i.kind === kind && i.present));
}

export function evidenceKinds(req: CaseRequest | null, present: boolean): EvidenceKind[] {
  return (req?.evidence.items ?? []).filter((i) => i.present === present).map((i) => i.kind);
}

/**
 * Show the deemed-acceptance line (spec C2) when the engine flags a missing GRN,
 * or whenever acceptance was deemed from delivery.
 */
export function showDeemedAcceptance(res: CaseResponse): boolean {
  if (res.warnings.some((w) => w.code === GRN_WARNING_CODE)) return true;
  return res.timeline?.objection_status === "DEEMED_ACCEPTANCE";
}

export function hasCode(res: CaseResponse, code: string): boolean {
  return res.warnings.some((w) => w.code === code);
}
