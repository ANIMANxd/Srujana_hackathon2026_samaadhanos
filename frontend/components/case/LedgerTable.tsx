"use client";

import { Fragment, useState } from "react";
import { date, money, pct } from "@/lib/format";
import { useT } from "@/lib/i18n";
import type { Financials } from "@/lib/types";
import { Icon } from "../common/Icon";

/**
 * Month-by-month ledger exactly as the engine returned it. With `expandable`,
 * each row's note opens under it (one row or all); otherwise notes sit inline,
 * which suits print (the evidence pack) and the overview drawer.
 */
export function LedgerTable({
  financials,
  placeholder,
  expandable = false,
}: {
  financials: Financials;
  placeholder: boolean;
  expandable?: boolean;
}) {
  const { t } = useT();
  const rows = financials.ledger;
  const [open, setOpen] = useState<Set<number>>(new Set());
  const allOpen = rows.length > 0 && open.size === rows.length;
  const toggle = (i: number) =>
    setOpen((prev) => {
      const next = new Set(prev);
      if (next.has(i)) next.delete(i);
      else next.add(i);
      return next;
    });

  return (
    <div className="flex flex-col gap-3">
      {expandable && rows.length > 0 && (
        <button
          type="button"
          className="btn btn-quiet min-h-8 self-end px-2 text-xs"
          aria-expanded={allOpen}
          onClick={() => setOpen(allOpen ? new Set() : new Set(rows.map((_, i) => i)))}
        >
          {t(allOpen ? "ledger.collapse" : "ledger.expand")}
          <Icon name="chevron-down" className={`h-3.5 w-3.5 transition-transform ${allOpen ? "rotate-180" : ""}`} />
        </button>
      )}
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
            {rows.map((r, i) => {
              const isOpen = open.has(i);
              return (
                <Fragment key={`${r.from}-${r.kind}-${i}`}>
                  <tr className={`border-t border-rule align-top first:border-t-0 hover:bg-paper ${r.kind === "PAYMENT" ? "bg-ok-wash/40" : ""}`}>
                    <td className="px-3 py-2 font-medium text-ink-900">
                      {expandable ? (
                        <button
                          type="button"
                          className="inline-flex items-center gap-1.5 text-left hover:text-ink-950"
                          aria-expanded={isOpen}
                          aria-label={`${t(`ledger.kind.${r.kind}`)} · ${t("ledger.row_toggle")}`}
                          onClick={() => toggle(i)}
                        >
                          <Icon name="chevron" className={`h-3.5 w-3.5 text-ink-500 transition-transform ${isOpen ? "rotate-90" : ""}`} />
                          {t(`ledger.kind.${r.kind}`)}
                        </button>
                      ) : (
                        <>
                          {t(`ledger.kind.${r.kind}`)}
                          {r.note && <span className="block text-xs font-normal text-ink-600">{r.note}</span>}
                        </>
                      )}
                    </td>
                    <td className="num px-3 py-2">{date(r.from)}</td>
                    <td className="num px-3 py-2">{date(r.to)}</td>
                    <td className="num px-3 py-2 text-right">{money(r.opening)}</td>
                    <td className="num px-3 py-2 text-right">{money(r.interest)}</td>
                    <td className="num px-3 py-2 text-right">{money(r.payment)}</td>
                    <td className="num px-3 py-2 text-right font-medium">{money(r.closing)}</td>
                    <td className="num px-3 py-2 text-right">{pct(r.rate_pct)}</td>
                  </tr>
                  {expandable && isOpen && (
                    <tr className="bg-paper">
                      <td colSpan={8} className="px-3 pb-3 pl-9 text-xs leading-relaxed text-ink-700">
                        {r.note ?? t("ledger.no_note")}
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
      {expandable ? (
        <p className="flex flex-col gap-0.5 text-xs leading-relaxed text-ink-500">
          <span>{t("ledger.rounding")}</span>
          <span>{t("ledger.payment_convention", { conv: t(`convention.${financials.payment_boundary_convention}`) })}</span>
          {placeholder && <span>{t("badge.placeholder")}</span>}
        </p>
      ) : (
        <p className="text-xs leading-relaxed text-ink-500">
          {t("ledger.caption", {
            mode: t(`mode.${financials.rate_mode}`),
            app: t(`appropriation.${financials.appropriation_mode}`),
            conv: t(`convention.${financials.payment_boundary_convention}`),
          })}
          {placeholder && ` (${t("badge.placeholder")})`}
        </p>
      )}
    </div>
  );
}
