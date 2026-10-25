// Offline samples for contract v1.1, synced from ../contracts/fixtures/v4.
// Each file is {_fixture, payload}; only the payload is used. Money in these
// files is engine output or is labelled placeholder in its own _fixture block;
// nothing here is computed in the browser.

import { RAW_V4 } from "@/fixtures";
import type { AuditEvent, Bid, CaseDetail, ChainVerifyResult, OptionsResponse, TrackState } from "./types";

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
export function offlineOptions(variant?: string | null): OptionsResponse | null {
  const v = payload(variant === "overdue" ? "options-not-financeable-overdue" : "options-financeable");
  return isObject(v) && isObject(v.get_paid_early) ? (v as unknown as OptionsResponse) : null;
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
