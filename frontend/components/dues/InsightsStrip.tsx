"use client";

// Portfolio insights in compact cards. Every figure is the server's
// (GET /insights); averages carry their sample size or "not enough history",
// and the cash-in figure is labelled an estimate. No charts in this form.

import type { ReactNode } from "react";
import { approxDays, count, pct } from "@/lib/format";
import { useT } from "@/lib/i18n";
import type { HistoryFigure } from "@/lib/useCustomer";
import type { InsightsView } from "@/lib/useInsights";
import { Money } from "../common/Money";
import { Skeleton } from "../common/States";
import { PlaceholderBadge } from "../shell/PlaceholderBadge";

function Card({ label, children, note, placeholder }: { label: string; children: ReactNode; note?: string; placeholder: boolean }) {
  return (
    <div className="flex min-w-0 flex-col gap-1.5 px-4 py-3.5">
      <dt className="flex flex-wrap items-center gap-1.5 text-xs text-ink-500">
        {label}
        {placeholder && <PlaceholderBadge />}
      </dt>
      <dd className="figure break-words text-lg text-ink-950">{children}</dd>
      {note && (
        <dd className="line-clamp-2 text-xs leading-snug text-ink-500" title={note}>
          {note}
        </dd>
      )}
    </div>
  );
}

function History({ figure, render }: { figure: HistoryFigure | null; render: (value: string) => string }) {
  const { t } = useT();
  if (!figure) return <Skeleton className="h-6 w-16" />;
  if (figure.kind === "not_enough") return <span className="text-sm font-normal text-ink-500">{t("customers.not_enough")}</span>;
  return <>{render(figure.value)}</>;
}

function historyNote(figure: HistoryFigure | null, t: ReturnType<typeof useT>["t"]): string | undefined {
  if (!figure) return undefined;
  return figure.kind === "value"
    ? t("stats.based_on", { n: count(figure.basedOn) })
    : t("stats.not_enough_history", { n: count(figure.basedOn), min: count(figure.min) });
}

export function InsightsStrip({ insights }: { insights: InsightsView }) {
  const { t } = useT();
  const d = insights.data;
  const ph = insights.placeholder;

  return (
    <section aria-label={t("insights.label")} className="flex flex-col gap-1.5">
      <dl className="panel grid grid-cols-2 gap-px overflow-hidden bg-rule sm:grid-cols-3 xl:grid-cols-6 [&>div]:bg-white">
        <Card placeholder={ph} label={t("insights.outstanding")} note={d ? t("insights.customers", { n: count(d.customer_count), m: count(d.invoice_count) }) : undefined}>
          {d ? <Money value={d.outstanding_total} /> : <Skeleton className="h-6 w-24" />}
        </Card>
        <Card placeholder={ph} label={t("insights.overdue")}>{d ? <Money value={d.overdue_total} /> : <Skeleton className="h-6 w-24" />}</Card>
        <Card placeholder={ph} label={t("insights.avg_days")} note={historyNote(insights.avgDaysToPay, t)}>
          <History figure={insights.avgDaysToPay} render={(v) => t("insights.avg_days_value", { n: approxDays(v) })} />
        </Card>
        <Card placeholder={ph} label={t("insights.on_time")} note={historyNote(insights.onTimePct, t)}>
          <History figure={insights.onTimePct} render={(v) => pct(v)} />
        </Card>
        <Card placeholder={ph} label={t("insights.cash_in")} note={d?.cash_in_estimate ? (d.cash_in_estimate_note ?? t("stats.estimate_note")) : undefined}>
          {d ? d.cash_in_estimate ? <Money value={d.cash_in_estimate} /> : "—" : <Skeleton className="h-6 w-24" />}
        </Card>
        <Card placeholder={ph} label={t("insights.top_share")} note={d ? t("insights.top_share_note") : undefined}>
          {d ? pct(d.top_customer_share_pct) : <Skeleton className="h-6 w-12" />}
        </Card>
      </dl>
      <p className="text-xs text-ink-500">{t("book.own_data_only")}</p>
    </section>
  );
}
