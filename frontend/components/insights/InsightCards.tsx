"use client";

// Four plain-language cards from the owner's own book: who the money is owed
// by, which overdue invoices meet 31 March, which customers pay later than the
// legal limit, and (only when the server sends it) a labelled cash-in estimate.
// Compact on top of Dues, full in a section below. Statements are facts about
// the owner's records; the one forward-looking card says it is an estimate.

import Link from "next/link";
import { useMemo } from "react";
import { approxDays, count, date, money, pct } from "@/lib/format";
import { useT } from "@/lib/i18n";
import { useHref } from "@/lib/params";
import { dayMonth, portfolioViews, type CashWeek, type ConcentrationView, type MarchItem, type PortfolioViews, type TermsItem } from "@/lib/portfolioViews";
import type { CustomerRow } from "@/lib/types";
import type { InsightsView } from "@/lib/useInsights";
import { Icon } from "../common/Icon";
import { Money } from "../common/Money";
import { Skeleton } from "../common/States";

type T = ReturnType<typeof useT>["t"];

const SHOWN_SHARES = 5;
// Each fill is at least 3:1 against white (non-text contrast); the legend carries the names and shares.
const SEGMENT = ["bg-ink-950", "bg-ink-950/85", "bg-ink-950/70", "bg-ink-950/60", "bg-ink-950/50"];
const OTHERS = "bg-[repeating-linear-gradient(45deg,var(--color-ink-600)_0_2px,transparent_2px_5px)] border border-ink-600";

export function usePortfolioViews(insights: InsightsView, rows: CustomerRow[] | null): PortfolioViews {
  const names = useMemo(() => new Map((rows ?? []).map((r) => [r.id, r.display_name])), [rows]);
  return useMemo(() => portfolioViews(insights.data, (id) => names.get(id) ?? null), [insights.data, names]);
}

// ---------------------------------------------------------------- headlines --

function concentrationHeadline(c: ConcentrationView, t: T): string {
  return t("insight.conc.headline", { pct: c.top.sharePct, name: c.top.name ?? t("insight.conc.one_customer") });
}

function marchHeadline(items: MarchItem[], t: T): string {
  const invoices = new Set(items.map((i) => i.caseId)).size;
  const customers = new Set(items.map((i) => i.customerId)).size;
  return t("insight.march.headline", {
    n: count(invoices),
    invoices: t(invoices === 1 ? "insight.word.invoice" : "insight.word.invoices"),
    m: count(customers),
    customers: t(customers === 1 ? "insight.word.customer" : "insight.word.customers"),
    date: dayMonth(items[0].nextMarch),
  });
}

function termsHeadline(f: TermsItem, t: T): string {
  return f.capDays === null
    ? f.text ?? t("insight.terms.headline_no_cap", { name: f.customerName, avg: approxDays(f.avgDays) })
    : t("insight.terms.headline", { name: f.customerName, avg: approxDays(f.avgDays), cap: count(f.capDays) });
}

// --------------------------------------------------------------- compact row --

export function InsightsCompact({ insights, views }: { insights: InsightsView; views: PortfolioViews }) {
  const { t } = useT();
  const href = useHref();
  const cards: { key: string; title: string; text: string }[] = [];
  if (views.concentration) cards.push({ key: "conc", title: t("insight.conc.title"), text: concentrationHeadline(views.concentration, t) });
  if (views.beforeMarch.length > 0) cards.push({ key: "march", title: t("insight.march.title", { date: dayMonth(views.beforeMarch[0].nextMarch) }), text: marchHeadline(views.beforeMarch, t) });
  // An average without its sample size is not shown (it would break "based on N").
  if (views.terms.length > 0 && views.terms[0].basedOn !== null) cards.push({ key: "terms", title: t("insight.terms.title"), text: `${termsHeadline(views.terms[0], t)} ${t("stats.based_on", { n: count(views.terms[0].basedOn) })}` });
  if (views.cashIn) cards.push({ key: "cash", title: t("insight.cash.title"), text: t("insight.cash.label") });
  if (insights.loading || cards.length === 0) return insights.loading ? <Skeleton className="h-16" /> : null;
  return (
    <section aria-label={t("insight.compact_label")} className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {cards.map((c) => (
        <article key={c.key} className="panel flex min-w-0 flex-col gap-1.5 p-4">
          <h3 className="text-xs font-medium text-ink-500">{c.title}</h3>
          <p className="text-sm leading-snug text-ink-900">{c.text}</p>
          <Link href={`${href("/")}#insights`} className="link mt-auto self-start text-xs">
            {t("insight.see_details")}
          </Link>
        </article>
      ))}
    </section>
  );
}

// ------------------------------------------------------------------- full ----

function Card({ id, title, children }: { id: string; title: string; children: React.ReactNode }) {
  return (
    <article aria-labelledby={id} className="panel flex min-w-0 flex-col gap-3 p-5">
      <h3 id={id} className="text-base font-semibold text-ink-950">
        {title}
      </h3>
      {children}
    </article>
  );
}

function Concentration({ c }: { c: ConcentrationView }) {
  const { t } = useT();
  const href = useHref();
  const top = c.shares.slice(0, SHOWN_SHARES);
  const rest = c.shares.length - top.length;
  const summary = top.map((s) => `${s.name} ${pct(s.sharePct)}`).join(", ");
  return (
    <Card id="ins-conc" title={t("insight.conc.title")}>
      <p className="text-sm text-ink-900">{concentrationHeadline(c, t)}</p>
      {top.length > 0 && (
        <>
          <div aria-hidden="true" className="flex h-3 w-full gap-px overflow-hidden rounded-full bg-rule">
            {top.map((s, i) => (
              <span key={s.customerId} className={SEGMENT[i] ?? SEGMENT[4]} style={{ flexGrow: Number(s.sharePct), flexBasis: 0 }} />
            ))}
            {rest > 0 && <span className={OTHERS} style={{ flexGrow: c.shares.slice(SHOWN_SHARES).reduce((n, s) => n + Number(s.sharePct), 0), flexBasis: 0 }} />}
          </div>
          <p className="sr-only">{t("insight.conc.sr", { list: summary, rest: rest > 0 ? t("insight.conc.others", { n: count(rest) }) : "" })}</p>
          <ul className="flex flex-col gap-1 text-sm">
            {top.map((s, i) => (
              <li key={s.customerId} className="flex items-center justify-between gap-3">
                <span className="flex min-w-0 items-center gap-2">
                  <span aria-hidden="true" className={`h-2.5 w-2.5 shrink-0 rounded-sm ${SEGMENT[i] ?? SEGMENT[4]}`} />
                  <Link href={href(`/customers/${encodeURIComponent(s.customerId)}`)} className="truncate hover:underline">
                    {s.name}
                  </Link>
                </span>
                <span className="num text-ink-700">{pct(s.sharePct)}</span>
              </li>
            ))}
            {rest > 0 && (
              <li className="flex items-center gap-2 text-ink-600">
                <span aria-hidden="true" className={`h-2.5 w-2.5 shrink-0 rounded-sm ${OTHERS}`} />
                {t("insight.conc.others", { n: count(rest) })}
              </li>
            )}
          </ul>
        </>
      )}
      {c.flaggedAbove && <p className="text-xs text-ink-600">{t("insight.conc.above", { pct: pct(c.flaggedAbove) })}</p>}
    </Card>
  );
}

function BeforeMarch({ items, sent }: { items: MarchItem[]; sent: boolean }) {
  const { t } = useT();
  const href = useHref();
  return (
    <Card id="ins-march" title={items[0] ? t("insight.march.title", { date: dayMonth(items[0].nextMarch) }) : t("insight.march.title_plain")}>
      {items.length === 0 ? (
        <p className="text-sm text-ink-600">{t(sent ? "insight.nothing" : "insight.pending")}</p>
      ) : (
        <>
          <p className="text-sm text-ink-900">{marchHeadline(items, t)}</p>
          <ul className="divide-y divide-rule">
            {items.map((i) => (
              <li key={i.caseId} className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 py-2 text-sm">
                <span className="min-w-0">
                  <span className="num font-medium text-ink-950">{i.invoiceNo}</span>
                  <span className="text-ink-600"> · {i.customerName}</span>
                  {i.outstanding && <Money value={i.outstanding} className="ml-2 text-xs text-ink-600" />}
                </span>
                <Link href={href(`/case/${encodeURIComponent(i.caseId)}`)} className="link inline-flex items-center gap-1 text-xs">
                  {t("insight.open")}
                  <Icon name="arrow-right" className="h-3 w-3" />
                  <span className="sr-only">{i.invoiceNo}</span>
                </Link>
              </li>
            ))}
          </ul>
          {items[0].note && <p className="text-xs text-ink-500">{items[0].note}</p>}
        </>
      )}
    </Card>
  );
}

function Terms({ items, sent }: { items: TermsItem[]; sent: boolean }) {
  const { t } = useT();
  const href = useHref();
  return (
    <Card id="ins-terms" title={t("insight.terms.title")}>
      {items.length === 0 ? (
        <p className="text-sm text-ink-600">{t(sent ? "insight.nothing" : "insight.pending")}</p>
      ) : (
        <ul className="divide-y divide-rule">
          {items.map((f) => (
            <li key={f.customerId} className="flex flex-col gap-1 py-2 first:pt-0">
              <p className="text-sm text-ink-900">{termsHeadline(f, t)}</p>
              <p className="flex flex-wrap items-center justify-between gap-2 text-xs text-ink-500">
                <span>{f.basedOn !== null ? t("stats.based_on", { n: count(f.basedOn) }) : t("insight.terms.no_n")}</span>
                <Link href={href(`/customers/${encodeURIComponent(f.customerId)}`)} className="link inline-flex items-center gap-1">
                  {f.planStep1Day !== null ? t("insight.terms.plan_day", { day: count(f.planStep1Day) }) : t("insight.terms.plan")}
                  <Icon name="arrow-right" className="h-3 w-3" />
                  <span className="sr-only">{f.customerName}</span>
                </Link>
              </p>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function CashIn({ weeks }: { weeks: CashWeek[] }) {
  const { t } = useT();
  const max = Math.max(...weeks.map((w) => Number(w.amount)), 0);
  return (
    <Card id="ins-cash" title={t("insight.cash.title")}>
      <p className="text-sm font-medium text-ink-900">{weeks[0].label ?? t("insight.cash.label")}</p>
      <p className="text-xs text-ink-600">{t("insight.cash.summary", { n: count(weeks.length), from: date(weeks[0].weekStart), to: date(weeks[weeks.length - 1].weekStart) })}</p>
      <div aria-hidden="true" className="flex h-28 items-end gap-1.5 border-b border-rule">
        {weeks.map((w) => (
          <span
            key={w.isoWeek}
            title={`${date(w.weekStart)}: ${money(w.amount)}`}
            className="flex-1 rounded-t bg-ink-950/60"
            style={{ height: `${max > 0 ? Math.max(4, (Number(w.amount) / max) * 100) : 4}%` }}
          />
        ))}
      </div>
      <details className="text-sm">
        <summary className="cursor-pointer text-xs font-medium text-ink-600 hover:text-ink-950">{t("insight.cash.amounts")}</summary>
        <ul className="mt-2 flex flex-col gap-1">
          {weeks.map((w) => (
            <li key={w.isoWeek} className="flex items-center justify-between gap-3">
              <span className="text-ink-700">{t("insight.cash.week", { date: date(w.weekStart) })}</span>
              <Money value={w.amount} className="text-sm" />
            </li>
          ))}
        </ul>
      </details>
      <p className="text-xs text-ink-500">{t("stats.estimate_note")}</p>
    </Card>
  );
}

export function InsightsSection({ insights, views }: { insights: InsightsView; views: PortfolioViews }) {
  const { t } = useT();
  return (
    <section id="insights" aria-labelledby="insights-title" className="flex scroll-mt-20 flex-col gap-3">
      <div className="flex flex-col gap-0.5">
        <h2 id="insights-title" className="text-lg font-semibold text-ink-950">
          {t("insight.title")}
        </h2>
        <p className="text-sm text-ink-500">{t("insight.subtitle")}</p>
      </div>
      {insights.loading ? (
        <Skeleton className="h-32" />
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          {views.concentration && <Concentration c={views.concentration} />}
          <BeforeMarch items={views.beforeMarch} sent={views.sent.beforeMarch} />
          <Terms items={views.terms} sent={views.sent.terms} />
          {views.cashIn && <CashIn weeks={views.cashIn} />}
        </div>
      )}
      <p className="text-xs text-ink-500">{t("insight.own_data")}</p>
    </section>
  );
}
