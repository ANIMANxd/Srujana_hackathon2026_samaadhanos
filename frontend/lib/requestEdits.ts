// Input edits shared by the judge console and the evidence locker. These only
// rewrite what the person entered; every figure still comes from the engine.

import type { CaseRequest, EvidenceKind } from "./types";

export const EVIDENCE_ORDER: EvidenceKind[] = ["INVOICE", "PO", "DELIVERY_PROOF", "WHATSAPP", "UDYAM", "GST_RETURN"];

/** Set one evidence item (adding it if the request has none of that kind). */
export function withEvidence(r: CaseRequest, kind: EvidenceKind, patch: { present?: boolean; ref?: string | null }): CaseRequest {
  const has = r.evidence.items.some((i) => i.kind === kind);
  const items = has
    ? r.evidence.items.map((i) => (i.kind === kind ? { ...i, ...patch } : i))
    : [...r.evidence.items, { kind, present: patch.present ?? false, ref: patch.ref ?? null }];
  return { ...r, evidence: { ...r.evidence, items } };
}

/**
 * Delivery proof is two inputs together (judge rehearsal 2): the evidence item
 * and the delivery date. Withdrawing it clears both; restoring it brings back
 * the preset's date when the field is empty.
 */
export function withDeliveryProof(r: CaseRequest, held: boolean, base: CaseRequest): CaseRequest {
  const next = withEvidence(r, "DELIVERY_PROOF", held ? { present: true } : { present: false, ref: null });
  const delivery = held ? r.transaction.delivery_date ?? base.transaction.delivery_date ?? null : null;
  return { ...next, transaction: { ...next.transaction, delivery_date: delivery } };
}
