"use client";

import { useState } from "react";
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

export function MoneyCard({ response, placeholder }: { response: CaseResponse; placeholder: boolean }) {
  const { t } = useT();
  const [ledgerOpen, setLedgerOpen] = useState(false);
  const fin = response.financials;

  if (!fin) {
    return (
      <section aria-labelledby="money-title" className="panel p-5">
        <h2 id="money-title" className="ledger-rule font-display text-xl font-semibold">{t("money.title")}</h2>
        <p className="mt-3 text-ink-700">{t("money.unavailable")}</p>
      </section>
    );
  }

  const seg = latestSegment(fin);

  return (
    <section aria-labelledby="money-title" className="panel flex flex-col p-5">
      <h2 id="money-title" className="ledger-rule font-display text-xl font-semibold text-ink-950">
        {t("money.title")}
      </h2>

      <dl className="mt-4 flex flex-col divide-y divide-rule">
        <div className="flex items-baseline justify-between gap-3 py-2">
          <dt className="text-ink-700">{t("money.principal")}</dt>
          <dd><Money value={fin.principal_outstanding} placeholder={placeholder} className="text-lg" /></dd>
        </div>
        <div className="flex items-baseline justify-between gap-3 py-2">
          <dt className="flex items-center gap-2 text-ink-700">
            {t("money.interest")}
            <span className="inline-flex items-center gap-1 rounded-sm bg-saffron-100 px-1.5 py-px text-xs font-semibold text-saffron-ink">
              <Icon name="spark" className="h-3 w-3" />
              {t("money.live")}
            </span>
          </dt>
          <dd className="text-right">
            <LiveInterestTicker interest={fin.interest_outstanding} dailyAccrual={fin.daily_accrual} className="text-lg" />
            {placeholder && <PlaceholderBadge />}
          </dd>
        </div>
        <div className="flex items-baseline justify-between gap-3 py-3">
          <dt className="font-semibold text-ink-900">{t("money.total")}</dt>
          <dd><Money value={fin.total_claim} placeholder={placeholder} className="text-xl font-semibold" /></dd>
        </div>
      </dl>

      {seg && (
        <p className="mt-1 text-sm text-ink-700">
          {t("money.rate", { rate: pct(seg.statutory_rate_pct) })} · {t("money.bank_rate", { rate: pct(seg.bank_rate_pct) })}
        </p>
      )}
      {fin.rate_segments.length > 1 && (
        <details className="mt-2 text-sm text-ink-700">
          <summary className="cursor-pointer font-medium text-ink-800">{t("money.rate_periods")}</summary>
          <ul className="mt-1 flex flex-col gap-0.5 pl-4">
            {fin.rate_segments.map((s) => (
              <li key={s.from} className="num">
                {t("money.rate_period_item", {
                  from: date(s.from),
                  to: date(s.to),
                  rate: pct(s.statutory_rate_pct),
                  bank: pct(s.bank_rate_pct),
                })}
              </li>
            ))}
          </ul>
        </details>
      )}
      <p className="mt-2 text-xs text-ink-500">{t("money.ticker_note", { daily: money(fin.daily_accrual) })}</p>

      <button type="button" className="btn btn-secondary mt-4 self-start" onClick={() => setLedgerOpen(true)}>
        <Icon name="ledger" className="h-4 w-4" />
        {t("money.see_ledger")}
      </button>

      <Drawer open={ledgerOpen} onClose={() => setLedgerOpen(false)} title={t("ledger.title")} width="lg">
        <LedgerTable financials={fin} placeholder={placeholder} />
      </Drawer>
    </section>
  );
}
