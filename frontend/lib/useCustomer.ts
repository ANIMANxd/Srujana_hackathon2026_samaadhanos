"use client";

// One customer's profile (GET /customers/{id}). The stats are descriptive
// figures from the owner's own records, never a score or a prediction. Days to
// pay run from the engine's day of acceptance and "on time" means paid by the
// engine's legal due date; the server computes both, this file only decides
// whether there is enough history to show them.

import { getCustomer } from "./api";
import { useBookRead, type BookRead } from "./customerBook";
import type { CustomerProfile } from "./types";

/** Fewest fully paid invoices before an average is shown, when the server does not say. */
const DEFAULT_MIN_HISTORY = 3;

export type HistoryFigure =
  | { kind: "value"; value: string; basedOn: number }
  | { kind: "not_enough"; basedOn: number; min: number; reason: string | null };

/**
 * An average with its sample size, or "not enough history". Below the minimum
 * (or when the server sent no figure) the average is withheld even if present.
 */
export function historyFigure(
  value: string | null,
  reason: string | null,
  basedOn: number,
  minHistory: number | null | undefined,
): HistoryFigure {
  const min = minHistory ?? DEFAULT_MIN_HISTORY;
  if (value === null || basedOn < min) return { kind: "not_enough", basedOn, min, reason };
  return { kind: "value", value, basedOn };
}

export type CustomerView = BookRead<CustomerProfile> & {
  avgDaysToPay: HistoryFigure | null;
  onTimePct: HistoryFigure | null;
};

export function useCustomer(id: string | null): CustomerView {
  const read = useBookRead(`customer:${id ?? ""}`, id !== null, () => getCustomer(id ?? ""), "customer.load_failed");
  const s = read.data?.stats;
  return {
    ...read,
    avgDaysToPay: s ? historyFigure(s.avg_days_to_pay, s.avg_days_to_pay_reason, s.based_on, s.min_history) : null,
    onTimePct: s ? historyFigure(s.on_time_pct, s.on_time_pct_reason, s.based_on, s.min_history) : null,
  };
}
