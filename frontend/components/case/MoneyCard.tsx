"use client";

import { useState, type ReactNode } from "react";
import { latestSegment } from "@/lib/derive";
import { date, money, pct } from "@/lib/format";
import { useT } from "@/lib/i18n";
import type { CaseResponse } from "@/lib/types";
import { Drawer } from "../common/Drawer";
import { Icon } from "../common/Icon";
import { Money } from "../common/Money";
import { LedgerTable } from "./LedgerTable";
import { PlaceholderBadge } from "../shell/PlaceholderBadge";
import { LiveInterestTicker } from "./LiveInterestTicker";

function Row({ label, children, strong = false }: { label: ReactNode; children: ReactNode; strong?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-2.5">
      <dt className={`text-sm ${strong ? "font-medium text-ink-950" : "text-ink-600"}`}>{label}</dt>
      <dd className={`text-right ${strong ? "font-semibold text-ink-950" : "text-ink-900"}`}>{children}</dd>
    </div>
  );
}

export function MoneyCard({ response, placeholder }: { response: CaseResponse; placeholder: boolean }) {
  const { t } = useT();
  const [ledgerOpen, setLedgerOpen] = useState(false);
  const fin = response.financials;

  if (!fin) {
    return (
      <section aria-labelledby="money-title" className="panel p-6">
        <h2 id="money-title" className="section-title">{t("money.title")}</h2>
        <p className="mt-2 text-sm text-ink-600">{t("money.unavailable")}</p>
      </section>
    );
  }

  const seg = latestSegment(fin);

  return (
    <section aria-labelledby="money-title" className="panel flex flex-col p-6">
      <div className="flex items-center justify-between gap-3">
        <h2 id="money-title" className="section-title">{t("money.title")}</h2>
        <button type="button" className="btn btn-secondary min-h-8 px-3 text-xs" onClick={() => setLedgerOpen(true)}>
          <Icon name="ledger" className="h-3.5 w-3.5" />
          {t("money.see_ledger")}
        </button>
      </div>

      <dl className="mt-3 flex flex-col divide-y divide-rule">
        <Row label={t("money.principal")}>
          <Money value={fin.principal_outstanding} placeholder={placeholder} className="text-sm" />
        </Row>
        <Row
          label={
            <span className="flex items-center gap-2">
              {t("money.interest")}
              <span className="inline-flex items-center gap-1 text-xs text-saffron-ink">
                <span className="live-dot" aria-hidden="true" />
                {t("money.live")}
              </span>
            </span>
          }
        >
          <LiveInterestTicker interest={fin.interest_outstanding} dailyAccrual={fin.daily_accrual} className="text-sm" />
          {placeholder && <PlaceholderBadge />}
        </Row>
        {seg && (
          <Row label={t("money.rate")}>
            <span className="num text-sm">
              {pct(seg.statutory_rate_pct)}
              <span className="ml-2 text-ink-500">
                {t("money.bank_rate")} {pct(seg.bank_rate_pct)}
              </span>
            </span>
          </Row>
        )}
        <Row label={t("money.total")} strong>
          <Money value={fin.total_claim} placeholder={placeholder} className="text-[0.9375rem]" />
        </Row>
      </dl>

      {fin.rate_segments.length > 1 && (
        <details className="mt-3 text-sm text-ink-700">
          <summary className="cursor-pointer text-xs font-medium text-ink-600 hover:text-ink-950">{t("money.rate_periods")}</summary>
          <ul className="mt-2 flex flex-col gap-1">
            {fin.rate_segments.map((s) => (
              <li key={s.from} className="num text-xs">
                {t("money.rate_period_item", { from: date(s.from), to: date(s.to), rate: pct(s.statutory_rate_pct), bank: pct(s.bank_rate_pct) })}
              </li>
            ))}
          </ul>
        </details>
      )}

      <Drawer open={ledgerOpen} onClose={() => setLedgerOpen(false)} title={t("ledger.title")} width="lg">
        <LedgerTable financials={fin} placeholder={placeholder} />
        <p className="mt-3 text-xs leading-relaxed text-ink-500">{t("money.ticker_note", { daily: money(fin.daily_accrual) })}</p>
      </Drawer>
    </section>
  );
}
