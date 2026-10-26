"use client";

// What a customer row needs beyond CustomerRow: the profile's history figures,
// its cases' track chips, and the law's interest for the ticker. CustomerRow
// carries none of these yet (CR-17), so each row reads its profile, and a
// customer with exactly one overdue invoice reads that case's engine figures.
// Interest across several invoices is NOT added up here (golden rule 6): the
// row says how many invoices accrue until the server sends a per-customer total.

import { useEffect, useState } from "react";
import { getCase, getCustomer, type Source } from "./api";
import { offlineCustomerProfile } from "./fixturesV5";
import { historyFigure, type HistoryFigure } from "./useCustomer";
import type { CaseSummary, CustomerStats } from "./types";

export type RowInterest =
  | { kind: "single"; interest: string; dailyAccrual: string; caseId: string }
  | { kind: "several"; invoices: number }
  | { kind: "none" }
  | { kind: "unknown" };

export type RowDetail = {
  stats: CustomerStats;
  avgDaysToPay: HistoryFigure;
  onTimePct: HistoryFigure;
  cases: CaseSummary[];
  interest: RowInterest;
};

async function interestFor(cases: CaseSummary[], source: Source): Promise<RowInterest> {
  const overdue = cases.filter((c) => (c.days_overdue ?? 0) > 0);
  if (overdue.length === 0) return { kind: "none" };
  if (overdue.length > 1) return { kind: "several", invoices: overdue.length };
  // The saved v1.1 case sample is a different invoice, so offline there is no ticker to show.
  if (source !== "live") return { kind: "unknown" };
  try {
    const d = await getCase(overdue[0].id);
    const fin = d.source === "live" ? d.data.latest_evaluation?.financials : null;
    return fin ? { kind: "single", interest: fin.interest_outstanding, dailyAccrual: fin.daily_accrual, caseId: overdue[0].id } : { kind: "unknown" };
  } catch {
    return { kind: "unknown" };
  }
}

async function detailFor(id: string, source: Source): Promise<RowDetail | null> {
  let profile;
  if (source === "live") {
    try {
      const r = await getCustomer(id);
      profile = r.source === "live" ? r.data : null;
    } catch {
      profile = null;
    }
  } else {
    // One sample profile exists; it belongs to one sample customer only, never lent to the others.
    const sample = offlineCustomerProfile();
    profile = sample?.customer.id === id ? sample : null;
  }
  if (!profile) return null;
  const s = profile.stats;
  const cases = profile.cases ?? [];
  return {
    stats: s,
    avgDaysToPay: historyFigure(s.avg_days_to_pay, s.avg_days_to_pay_reason, s.based_on, s.min_history),
    onTimePct: historyFigure(s.on_time_pct, s.on_time_pct_reason, s.based_on, s.min_history),
    cases,
    interest: await interestFor(cases, source),
  };
}

/** Details keyed by customer id; a missing key is still loading, `null` means none could be read. */
export function useCustomerDetails(ids: string[], source: Source | null): Map<string, RowDetail | null> {
  const [details, setDetails] = useState<Map<string, RowDetail | null>>(new Map());
  const key = `${source}:${ids.join(",")}`;

  useEffect(() => {
    if (source === null) return;
    let alive = true;
    Promise.all(ids.map(async (id) => [id, await detailFor(id, source)] as const)).then((pairs) => {
      if (alive) setDetails(new Map(pairs));
    });
    return () => {
      alive = false;
    };
    // `key` names the request; the ids array is a fresh value each render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  return details;
}
