"use client";

// A case's payments (GET /cases/{id}/payments) and the one sentence that says it
// is paid. The amount still owed is the engine's (`total_claim`); this file only
// reads it, it never works it out. Voided rows stay in the list, marked.

import { daysBetween } from "./derive";
import { listPayments } from "./api";
import { useBookRead, type BookRead } from "./customerBook";
import type { CaseResponse, Payment } from "./types";

export function usePayments(caseId: string, enabled: boolean): BookRead<Payment[]> {
  return useBookRead(`payments:${caseId}`, enabled, () => listPayments(caseId), "pay.load_failed");
}

const ZERO = /^0*(\.0*)?$/;

export type PaidSummary = { paidOn: string; daysAfterAcceptance: number | null; legalDueDays: number | null };

/**
 * Set only when the engine says nothing is left to pay and an unvoided payment
 * exists. The date is the latest unvoided payment's; the day counts are the
 * engine's acceptance date and applied days, differenced as calendar dates.
 */
export function paidSummary(response: CaseResponse, payments: Payment[] | null): PaidSummary | null {
  const fin = response.financials;
  if (!fin || !payments || !ZERO.test(fin.total_claim)) return null;
  const live = payments.filter((p) => !p.voided_at);
  if (live.length === 0) return null;
  const paidOn = live.reduce((latest, p) => (p.paid_on > latest ? p.paid_on : latest), live[0].paid_on);
  const accepted = response.timeline?.acceptance_date ?? null;
  return {
    paidOn,
    daysAfterAcceptance: accepted ? daysBetween(accepted, paidOn) : null,
    legalDueDays: response.timeline?.applied_days ?? null,
  };
}
