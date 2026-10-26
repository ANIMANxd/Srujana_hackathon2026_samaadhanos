// The four portfolio views on the insights cards. `backend/insights` computes
// them (concentration shares, invoices before 31 March, terms flags, the
// labelled cash-in weeks) but the v1.2 `PortfolioInsights` response does not
// carry them yet (CR-21). They are read defensively by the module's own names:
// a view with no data is absent, never filled in here. Nothing is added up or
// worked out on the client; counts of listed items are the only arithmetic.

import type { PortfolioInsights } from "./types";

const isObject = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);
const str = (v: unknown): string | null => (typeof v === "string" && v !== "" ? v : null);
const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);
const list = (v: unknown): Record<string, unknown>[] => (Array.isArray(v) ? v.filter(isObject) : []);

export type Share = { customerId: string; name: string; sharePct: string; outstanding: string | null };

export type ConcentrationView = {
  /** The largest customer, as the server names it. */
  top: { customerId: string; name: string | null; sharePct: string };
  /** The server's shares, largest first; empty when only the top figure was sent. */
  shares: Share[];
  /** Set only when the server says the top share is above the product threshold. */
  flaggedAbove: string | null;
};

export type MarchItem = { customerId: string; customerName: string; caseId: string; invoiceNo: string; outstanding: string; nextMarch: string; note: string | null };
export type TermsItem = { customerId: string; customerName: string; avgDays: string; capDays: number | null; text: string | null; basedOn: number | null; planStep1Day: number | null };
export type CashWeek = { isoWeek: string; weekStart: string; amount: string; invoiceCount: number | null; label: string | null };

export type PortfolioViews = {
  concentration: ConcentrationView | null;
  beforeMarch: MarchItem[];
  terms: TermsItem[];
  /** Whether the server sent the list at all; an empty list it did send means "nothing to flag". */
  sent: { beforeMarch: boolean; terms: boolean };
  /** Null when the estimate is off or has nothing to show. */
  cashIn: CashWeek[] | null;
};

export function portfolioViews(d: PortfolioInsights | null, nameOf: (customerId: string) => string | null): PortfolioViews {
  const empty: PortfolioViews = { concentration: null, beforeMarch: [], terms: [], sent: { beforeMarch: false, terms: false }, cashIn: null };
  if (!d) return empty;
  const x = d as unknown as Record<string, unknown>;

  const conc = isObject(x.concentration) ? x.concentration : null;
  const shares: Share[] = list(conc?.shares).flatMap((s) => {
    const id = str(s.customer_id);
    const pctText = str(s.share_pct);
    return id && pctText ? [{ customerId: id, name: str(s.customer_name) ?? nameOf(id) ?? id, sharePct: pctText, outstanding: str(s.outstanding) }] : [];
  });
  const topId = d.top_customer_id ?? str(conc?.top_customer_id);
  const topPct = d.top_customer_share_pct ?? str(conc?.top_share_pct);
  const flagged = conc?.flagged === true ? str(conc.threshold_pct) : null;
  const concentration: ConcentrationView | null =
    topId && topPct ? { top: { customerId: topId, name: shares.find((s) => s.customerId === topId)?.name ?? nameOf(topId), sharePct: topPct }, shares, flaggedAbove: flagged } : null;

  const beforeMarch = list(x.before_march).flatMap((b): MarchItem[] => {
    const caseId = str(b.case_id);
    const customerId = str(b.customer_id);
    const nextMarch = str(b.next_march);
    return caseId && customerId && nextMarch
      ? [{ customerId, customerName: str(b.customer_name) ?? nameOf(customerId) ?? customerId, caseId, invoiceNo: str(b.invoice_no) ?? caseId, outstanding: str(b.outstanding) ?? "", nextMarch, note: str(b.note) }]
      : [];
  });

  const terms = list(x.terms_flags).flatMap((f): TermsItem[] => {
    const customerId = str(f.customer_id);
    const avg = str(f.avg_days_to_pay);
    return customerId && avg
      ? [{ customerId, customerName: str(f.customer_name) ?? nameOf(customerId) ?? customerId, avgDays: avg, capDays: num(f.credit_cap_days), text: str(f.text), basedOn: num(f.based_on_n), planStep1Day: num(f.plan_step1_day) }]
      : [];
  });

  const weeks = list(x.cash_in_weeks ?? x.cash_in_estimate_weeks).flatMap((w): CashWeek[] => {
    const amount = str(w.amount);
    const weekStart = str(w.week_start);
    return amount && weekStart ? [{ isoWeek: str(w.iso_week) ?? weekStart, weekStart, amount, invoiceCount: num(w.invoice_count), label: str(w.label) }] : [];
  });

  return {
    concentration,
    beforeMarch,
    terms,
    sent: { beforeMarch: Array.isArray(x.before_march), terms: Array.isArray(x.terms_flags) },
    cashIn: weeks.length > 0 ? weeks : null,
  };
}

const MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

/** "2027-03-31" -> "31 March". */
export function dayMonth(value: string): string {
  const m = /^\d{4}-(\d{2})-(\d{2})/.exec(value);
  return m ? `${Number(m[2])} ${MONTH_NAMES[Number(m[1]) - 1] ?? m[1]}` : value;
}
