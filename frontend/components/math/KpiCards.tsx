"use client";

import type { ReactNode } from "react";
import { latestSegment } from "@/lib/derive";
import { date, pct } from "@/lib/format";
import { useT } from "@/lib/i18n";
import type { Financials } from "@/lib/types";
import { Icon } from "../common/Icon";
import { Money } from "../common/Money";
import { LiveInterestTicker } from "../case/LiveInterestTicker";
import { PlaceholderBadge } from "../shell/PlaceholderBadge";

function Card({ label, children, accent = false }: { label: ReactNode; children: ReactNode; accent?: boolean }) {
  return (
    <div className={`panel flex flex-col gap-3 p-5 ${accent ? "border-ink-950/20" : ""}`}>
      <span className="flex items-center gap-1.5 text-xs text-ink-500">{label}</span>
      {children}
    </div>
  );
}

/**
 * The money as KPIs. Every figure is the engine's string, formatted only; the
 * live interest card is the one permitted ticker (architecture §10).
 */
export function KpiCards({ financials, placeholder }: { financials: Financials; placeholder: boolean }) {
  const { t } = useT();
  const fin = financials;
  const now = latestSegment(fin);
  const changed = fin.rate_segments.length > 1;

  return (
    <div className="flex flex-col gap-4">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card label={t("kpi.principal")}>
          <Money value={fin.principal_outstanding} placeholder={placeholder} className="figure text-2xl text-ink-950" />
        </Card>
        <Card
          label={
            <>
              <span className="live-dot" aria-hidden="true" />
              {t("kpi.interest")}
            </>
          }
        >
          <span className="figure text-2xl text-ink-950">
            <LiveInterestTicker interest={fin.interest_outstanding} dailyAccrual={fin.daily_accrual} className="figure" />
            {placeholder && <PlaceholderBadge />}
          </span>
        </Card>
        <Card label={t("kpi.total")} accent>
          <Money value={fin.total_claim} placeholder={placeholder} className="figure text-2xl text-ink-950" />
        </Card>
        <Card label={t("kpi.rate")}>
          <span className="figure text-2xl text-ink-950">{now ? pct(now.statutory_rate_pct) : "—"}</span>
          <span className="text-xs text-ink-500">{t("kpi.rate_now")}</span>
        </Card>
      </div>

      <section aria-labelledby="seg-title" className="panel flex flex-col gap-3 p-5">
        <h3 id="seg-title" className="section-title">{t("kpi.segments")}</h3>
        {changed && (
          <p className="flex items-center gap-2 text-sm text-warn">
            <Icon name="info" className="h-4 w-4" />
            {t("kpi.rate_changed")}
          </p>
        )}
        <ol className="flex flex-col divide-y divide-rule rounded-lg border border-rule">
          {fin.rate_segments.map((s) => (
            <li key={s.from} className="flex flex-wrap items-center justify-between gap-2 px-4 py-2.5 text-sm">
              <span className="num text-ink-700">{t("kpi.segment", { from: date(s.from), to: date(s.to) })}</span>
              <span className="num text-ink-950">{t("kpi.segment_rate", { rate: pct(s.statutory_rate_pct), bank: pct(s.bank_rate_pct) })}</span>
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}
