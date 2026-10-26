"use client";

// Days to pay, one bar per invoice, from the server's series (CR-18): solid
// for a paid invoice, outlined and hatched for an open one ("still open, N days
// so far"). A dash on each bar marks that invoice's legal due days, and a
// labelled line marks the credit cap from config. Day counts only; no money is
// drawn. A text summary sits above and a table toggle shows the same data.

import { useState } from "react";
import { Bar, CartesianGrid, ComposedChart, ReferenceLine, ResponsiveContainer, Scatter, Tooltip, XAxis, YAxis } from "recharts";
import { count, date } from "@/lib/format";
import { useT } from "@/lib/i18n";
import type { SeriesPoint } from "@/lib/profileExtras";

type Datum = {
  invoice: string;
  paid: number | null;
  open: number | null;
  due: number | null;
  point: SeriesPoint;
};

function DueTick(props: { cx?: number; cy?: number }) {
  const { cx, cy } = props;
  if (cx === undefined || cy === undefined) return <g />;
  return <line x1={cx - 16} x2={cx + 16} y1={cy} y2={cy} stroke="var(--color-saffron-600)" strokeWidth={2.5} strokeLinecap="round" />;
}

function TooltipBody({ active, payload }: { active?: boolean; payload?: { payload: Datum }[] }) {
  const { t } = useT();
  if (!active || !payload?.length) return null;
  const p = payload[0].payload.point;
  return (
    <div className="rounded-md border border-rule bg-white px-3 py-2 text-xs text-ink-800 shadow-sm">
      <p className="num font-medium text-ink-950">{p.invoice_no}</p>
      <p>{t("chart.tip.accepted", { d: date(p.accepted_on) })}</p>
      <p>{t("chart.tip.due", { d: date(p.due_date) })}</p>
      {p.days_to_pay !== null ? (
        <p>{t("chart.tip.paid", { d: date(p.paid_on), n: count(p.days_to_pay) })}</p>
      ) : (
        <p>{t("chart.open_so_far", { n: count(p.days_open_so_far) })}</p>
      )}
      {p.legal_due_days !== null && <p>{t("chart.tip.legal", { n: count(p.legal_due_days) })}</p>}
    </div>
  );
}

export function PaymentHistoryChart({ series, cap }: { series: SeriesPoint[]; cap: number | null }) {
  const { t } = useT();
  const [asTable, setAsTable] = useState(false);
  const data: Datum[] = series.map((p) => ({
    invoice: p.invoice_no,
    paid: p.days_to_pay,
    open: p.days_to_pay === null ? p.days_open_so_far : null,
    due: p.legal_due_days,
    point: p,
  }));
  // Counted from the server's own on_time flags; nothing is compared here.
  const paid = series.filter((p) => p.on_time !== null);
  const late = paid.filter((p) => p.on_time === false).length;
  const open = series.filter((p) => p.days_to_pay === null).length;

  return (
    <section aria-labelledby="history-title" className="panel flex flex-col gap-4 p-5 sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex flex-col gap-1">
          <h2 id="history-title" className="text-base font-semibold text-ink-950">{t("chart.title")}</h2>
          <p className="text-sm text-ink-700">
            {paid.length > 0 ? t("chart.summary", { late: count(late), n: count(paid.length) }) : t("chart.summary_none")}
            {open > 0 ? ` ${t("chart.summary_open", { n: count(open) })}` : ""}
          </p>
        </div>
        <button type="button" className="btn btn-secondary min-h-8 px-3 text-sm" aria-pressed={asTable} onClick={() => setAsTable((v) => !v)}>
          {t(asTable ? "chart.show_chart" : "chart.show_table")}
        </button>
      </div>

      {asTable ? (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[34rem] text-left text-sm">
            <caption className="sr-only">{t("chart.title")}</caption>
            <thead className="text-xs text-ink-500">
              <tr>
                <th scope="col" className="py-2 pr-3 font-medium">{t("chart.col.invoice")}</th>
                <th scope="col" className="py-2 pr-3 font-medium">{t("chart.col.accepted")}</th>
                <th scope="col" className="py-2 pr-3 font-medium">{t("chart.col.due")}</th>
                <th scope="col" className="py-2 pr-3 font-medium">{t("chart.col.paid")}</th>
                <th scope="col" className="py-2 pr-3 text-right font-medium">{t("chart.col.days")}</th>
                <th scope="col" className="py-2 text-right font-medium">{t("chart.col.legal")}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-rule">
              {series.map((p) => (
                <tr key={p.case_id}>
                  <td className="num py-2 pr-3">{p.invoice_no}</td>
                  <td className="py-2 pr-3">{date(p.accepted_on)}</td>
                  <td className="py-2 pr-3">{date(p.due_date)}</td>
                  <td className="py-2 pr-3">{p.days_to_pay !== null ? date(p.paid_on) : t("chart.still_open")}</td>
                  <td className="num py-2 pr-3 text-right">
                    {p.days_to_pay !== null ? count(p.days_to_pay) : t("chart.so_far", { n: count(p.days_open_so_far) })}
                  </td>
                  <td className="num py-2 text-right">{count(p.legal_due_days)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <figure className="flex flex-col gap-2">
          <div className="h-72 w-full" aria-hidden="true">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={data} margin={{ top: 16, right: 16, bottom: 28, left: 8 }}>
                <defs>
                  <pattern id="open-hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
                    <rect width="6" height="6" fill="var(--color-paper-raised)" />
                    <line x1="0" y1="0" x2="0" y2="6" stroke="var(--color-ink-500)" strokeWidth="2" />
                  </pattern>
                </defs>
                <CartesianGrid vertical={false} stroke="var(--color-rule)" />
                <XAxis
                  dataKey="invoice"
                  tick={{ fontSize: 11, fill: "var(--color-ink-600)" }}
                  tickLine={false}
                  axisLine={{ stroke: "var(--color-rule-strong)" }}
                  label={{ value: t("chart.x_label"), position: "insideBottom", offset: -18, fontSize: 12, fill: "var(--color-ink-600)" }}
                />
                <YAxis
                  allowDecimals={false}
                  tick={{ fontSize: 11, fill: "var(--color-ink-600)" }}
                  tickLine={false}
                  axisLine={false}
                  width={44}
                  label={{ value: t("chart.y_label"), angle: -90, position: "insideLeft", offset: 6, fontSize: 12, fill: "var(--color-ink-600)" }}
                />
                <Tooltip content={<TooltipBody />} cursor={{ fill: "var(--color-paper-sunk)" }} />
                <Bar dataKey="paid" stackId="d" fill="var(--color-ink-800)" maxBarSize={44} radius={[3, 3, 0, 0]} isAnimationActive={false} />
                <Bar
                  dataKey="open"
                  stackId="d"
                  fill="url(#open-hatch)"
                  stroke="var(--color-ink-700)"
                  strokeWidth={1.5}
                  strokeDasharray="4 3"
                  maxBarSize={44}
                  isAnimationActive={false}
                />
                <Scatter dataKey="due" shape={<DueTick />} isAnimationActive={false} />
                {cap !== null && (
                  <ReferenceLine
                    y={cap}
                    stroke="var(--color-block)"
                    strokeDasharray="6 4"
                    label={{ value: t("chart.cap_label", { n: count(cap) }), position: "insideTopRight", fontSize: 11, fill: "var(--color-block)" }}
                  />
                )}
              </ComposedChart>
            </ResponsiveContainer>
          </div>
          <figcaption className="flex flex-wrap gap-x-5 gap-y-1.5 text-xs text-ink-600">
            <span className="inline-flex items-center gap-1.5">
              <span className="h-3 w-3 rounded-sm bg-ink-800" aria-hidden="true" />
              {t("chart.legend.paid")}
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="h-3 w-3 rounded-sm border border-dashed border-ink-700 bg-[repeating-linear-gradient(45deg,var(--color-ink-500)_0_2px,transparent_2px_6px)]" aria-hidden="true" />
              {t("chart.legend.open")}
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="h-0.5 w-4 rounded bg-saffron-600" aria-hidden="true" />
              {t("chart.legend.legal")}
            </span>
            {cap !== null && (
              <span className="inline-flex items-center gap-1.5">
                <span className="w-4 border-t-2 border-dashed border-block" aria-hidden="true" />
                {t("chart.legend.cap", { n: count(cap) })}
              </span>
            )}
          </figcaption>
        </figure>
      )}
    </section>
  );
}
