"use client";

// Portfolio insights (GET /insights): totals, chart series and the cash-in
// estimate exactly as the server computed them. The estimate is shown with its
// note, never as a promise; the averages go through the same history gate as a
// single customer's.

import { getInsights } from "./api";
import { useBookRead, type BookRead } from "./customerBook";
import { historyFigure, type HistoryFigure } from "./useCustomer";
import type { PortfolioInsights } from "./types";

export type InsightsView = BookRead<PortfolioInsights> & {
  avgDaysToPay: HistoryFigure | null;
  onTimePct: HistoryFigure | null;
};

export function useInsights(): InsightsView {
  const read = useBookRead("insights", true, getInsights, "insights.load_failed");
  const d = read.data;
  return {
    ...read,
    avgDaysToPay: d ? historyFigure(d.avg_days_to_pay, d.avg_days_to_pay_reason, d.based_on, d.min_history) : null,
    onTimePct: d ? historyFigure(d.on_time_pct, d.on_time_pct_reason, d.based_on, d.min_history) : null,
  };
}
