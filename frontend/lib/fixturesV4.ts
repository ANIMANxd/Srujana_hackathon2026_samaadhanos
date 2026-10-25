// Offline samples for contract v1.1, synced from ../contracts/fixtures/v4.
// Each file is {_fixture, payload}; only the payload is used. Money in these
// files is engine output or is labelled placeholder in its own _fixture block;
// nothing here is computed in the browser.

import { RAW_V4 } from "@/fixtures";
import type {
  AuditEvent,
  Bid,
  CaseDetail,
  CaseSummary,
  ChainVerifyResult,
  ESignSession,
  OptionsResponse,
  PayoutStatus,
  TrackState,
  WebhookDelivery,
} from "./types";

function payload(name: string): unknown {
  const f = RAW_V4[name];
  return typeof f === "object" && f !== null && "payload" in f ? (f as { payload: unknown }).payload : null;
}

function isObject(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null;
}

function asCaseDetail(v: unknown): CaseDetail | null {
  return isObject(v) && isObject(v.case) && typeof v.case.id === "string" ? (v as unknown as CaseDetail) : null;
}

/** Track states that have a saved sample case-detail. */
export const OFFLINE_STATES: TrackState[] = [
  "FINANCEABLE",
  "AWAITING_BUYER_ACCEPTANCE",
  "BIDS_AVAILABLE",
  "AWAITING_ESIGN",
  "AWAITING_DISBURSEMENT",
  "DISBURSED",
  "BUYER_DECLINED",
  "NO_BIDS",
];

/** The saved sample case in the requested state (default FINANCEABLE), or null if none is bundled. */
export function offlineCaseDetail(state?: string | null): CaseDetail | null {
  // "NONE": the same sample case before any option was started (no track, no actions).
  if (state === "NONE") {
    const base = asCaseDetail(payload("case-detail-FINANCEABLE"));
    return base ? { ...base, active_track: null, available_actions: [] } : null;
  }
  const wanted = state && OFFLINE_STATES.some((s) => s === state) ? state : "FINANCEABLE";
  return asCaseDetail(payload(`case-detail-${wanted}`));
}

/** `variant` "overdue" picks the sample where Option 1 is blocked; anything else the financeable one. */
/** The saved sample case as a Dues row. Every field is copied from the sample, nothing is worked out. */
export function offlineCases(): CaseSummary[] | null {
  const d = offlineCaseDetail("FINANCEABLE");
  if (!d) return null;
  const tl = d.latest_evaluation?.timeline;
  return [
    {
      id: d.case.id,
      invoice_no: d.case.invoice_no,
      supplier_ref: d.case.supplier_ref,
      buyer_gstin: d.case.buyer_gstin,
      accepted_amount: d.case.accepted_amount,
      calculation_date: d.latest_evaluation?.calculation_date ?? d.case.invoice_date,
      days_overdue: tl?.days_overdue ?? 0,
      due_date: tl?.due_date ?? null,
      state: d.active_track?.state ?? "NEW",
      active_track: d.active_track,
      available_actions: d.available_actions,
      stage: null,
    },
  ];
}

export function offlineOptions(variant?: string | null): OptionsResponse | null {
  const v = payload(variant === "overdue" ? "options-not-financeable-overdue" : "options-financeable");
  return isObject(v) && isObject(v.get_paid_early) ? (v as unknown as OptionsResponse) : null;
}

export function offlineEsign(): ESignSession | null {
  const v = payload("esign-session");
  return isObject(v) && typeof v.session_id === "string" ? (v as unknown as ESignSession) : null;
}

export function offlinePayout(): PayoutStatus | null {
  const v = payload("payout");
  return isObject(v) && typeof v.payout_ref === "string" ? (v as unknown as PayoutStatus) : null;
}

export function offlineDeliveries(): WebhookDelivery[] | null {
  const v = payload("webhook-deliveries");
  return Array.isArray(v) ? (v as WebhookDelivery[]) : null;
}

export function offlineBids(): Bid[] | null {
  const v = payload("bids");
  return Array.isArray(v) ? (v as Bid[]) : null;
}

export function offlineEvents(): AuditEvent[] | null {
  const v = payload("events");
  return Array.isArray(v) ? (v as AuditEvent[]) : null;
}

export function offlineChainResult(): ChainVerifyResult | null {
  const v = payload("chain-verify-result");
  return isObject(v) && typeof v.valid === "boolean" ? (v as unknown as ChainVerifyResult) : null;
}
