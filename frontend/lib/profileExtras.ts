// Fields the backend's customer stats already compute (backend/insights/stats.py:
// InvoiceSeriesPoint, CustomerStatsResult) but the v1.2 CustomerProfile does not
// publish yet (CR-18). They are read here, defensively, only if the profile
// response carries them; nothing is worked out in the browser. Until the
// contract adds them, every reader returns null and the screen says the server
// has not sent that figure. Once they are in contracts/types.ts, replace this
// file with the generated types.

import type { CustomerProfile } from "./types";

export type SeriesStatus = "PAID" | "OPEN" | "PARTLY_PAID" | string;

/** One invoice on the payment-history chart, as the server computed it. */
export type SeriesPoint = {
  case_id: string;
  invoice_no: string;
  accepted_on: string | null;
  due_date: string | null;
  /** Engine due date minus engine acceptance date. */
  legal_due_days: number | null;
  /** Set only when the invoice is fully paid. */
  days_to_pay: number | null;
  /** Set only while the invoice is open. */
  days_open_so_far: number | null;
  days_overdue: number | null;
  status: SeriesStatus;
  outstanding: string;
  on_time: boolean | null;
  paid_on: string | null;
};

export type ProfileExtras = {
  series: SeriesPoint[] | null;
  onTimeCount: number | null;
  interestNow: string | null;
};

function isObject(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null;
}

const intOrNull = (v: unknown): number | null => (typeof v === "number" && Number.isInteger(v) ? v : null);
const strOrNull = (v: unknown): string | null => (typeof v === "string" ? v : null);

function asPoint(v: unknown): SeriesPoint | null {
  if (!isObject(v) || typeof v.case_id !== "string" || typeof v.invoice_no !== "string") return null;
  return {
    case_id: v.case_id,
    invoice_no: v.invoice_no,
    accepted_on: strOrNull(v.accepted_on),
    due_date: strOrNull(v.due_date),
    legal_due_days: intOrNull(v.legal_due_days),
    days_to_pay: intOrNull(v.days_to_pay),
    days_open_so_far: intOrNull(v.days_open_so_far),
    days_overdue: intOrNull(v.days_overdue),
    status: typeof v.status === "string" ? v.status : "OPEN",
    outstanding: typeof v.outstanding === "string" ? v.outstanding : "0.00",
    on_time: typeof v.on_time === "boolean" ? v.on_time : null,
    paid_on: strOrNull(v.paid_on ?? v.final_payment_on),
  };
}

export function profileExtras(profile: CustomerProfile): ProfileExtras {
  const raw: unknown = profile;
  const p = isObject(raw) ? raw : {};
  const stats: unknown = p.stats;
  const s = isObject(stats) ? stats : {};
  const list = Array.isArray(p.series) ? p.series : Array.isArray(s.series) ? s.series : null;
  const series = list ? list.map(asPoint).filter((x): x is SeriesPoint => x !== null) : null;
  return {
    series,
    onTimeCount: intOrNull(s.on_time_count),
    interestNow: strOrNull(s.interest_accrued_now ?? s.interest_outstanding),
  };
}
