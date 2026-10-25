"use client";

import { date, money, pct } from "@/lib/format";
import { useT } from "@/lib/i18n";
import type { Financials } from "@/lib/types";

/** Month-by-month ledger exactly as the engine returned it. */
export function LedgerTable({ financials, placeholder }: { financials: Financials; placeholder: boolean }) {
  const { t } = useT();
  const rows = financials.ledger;
  return (
    <div className="flex flex-col gap-3">
      <div className="overflow-x-auto rounded-lg border border-rule">
        <table className="w-full min-w-[44rem] border-collapse text-sm">
          <caption className="sr-only">{t("ledger.title")}</caption>
          <thead className="border-b border-rule bg-paper text-left text-xs text-ink-500">
            <tr>
              <th scope="col" className="px-3 py-2 font-medium">{t("ledger.col.kind")}</th>
              <th scope="col" className="px-3 py-2 font-medium">{t("ledger.col.from")}</th>
              <th scope="col" className="px-3 py-2 font-medium">{t("ledger.col.to")}</th>
              <th scope="col" className="px-3 py-2 text-right font-medium">{t("ledger.col.opening")}</th>
              <th scope="col" className="px-3 py-2 text-right font-medium">{t("ledger.col.interest")}</th>
              <th scope="col" className="px-3 py-2 text-right font-medium">{t("ledger.col.payment")}</th>
              <th scope="col" className="px-3 py-2 text-right font-medium">{t("ledger.col.closing")}</th>
              <th scope="col" className="px-3 py-2 text-right font-medium">{t("ledger.col.rate")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr>
                <td colSpan={8} className="px-3 py-4 text-ink-600">{t("ledger.empty")}</td>
              </tr>
            )}
            {rows.map((r, i) => (
              <tr key={`${r.from}-${r.kind}-${i}`} className="border-t border-rule align-top first:border-t-0 hover:bg-paper">
                <td className="px-3 py-2 font-medium text-ink-900">
                  {t(`ledger.kind.${r.kind}`)}
                  {r.note && <span className="block text-xs font-normal text-ink-600">{r.note}</span>}
                </td>
                <td className="num px-3 py-2">{date(r.from)}</td>
                <td className="num px-3 py-2">{date(r.to)}</td>
                <td className="num px-3 py-2 text-right">{money(r.opening)}</td>
                <td className="num px-3 py-2 text-right">{money(r.interest)}</td>
                <td className="num px-3 py-2 text-right">{money(r.payment)}</td>
                <td className="num px-3 py-2 text-right font-medium">{money(r.closing)}</td>
                <td className="num px-3 py-2 text-right">{pct(r.rate_pct)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs leading-relaxed text-ink-500">
        {t("ledger.caption", {
          mode: t(`mode.${financials.rate_mode}`),
          app: t(`appropriation.${financials.appropriation_mode}`),
          conv: t(`convention.${financials.payment_boundary_convention}`),
        })}
        {placeholder && ` (${t("badge.placeholder")})`}
      </p>
    </div>
  );
}
