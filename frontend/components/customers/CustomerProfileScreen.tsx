"use client";

// One customer: who they are (PAN, GSTINs, group), descriptive figures from the
// owner's own records, the payment history, every invoice, what happened and
// when, and what the delays have cost the buyer. Figures come from the profile
// response; where it does not carry one yet (CR-18) the figure comes from the
// engine's own case evaluation, or the screen says it is not available. Never a
// score or a rating.

import Link from "next/link";
import { useMemo, useState } from "react";
import { unlinkFromGroup, detachGstin } from "@/lib/api";
import { announceBookChange, bookAction } from "@/lib/customerBook";
import { trackChip } from "@/lib/dueChip";
import { approxDays, count, date, money, pct } from "@/lib/format";
import { useT } from "@/lib/i18n";
import { en, type MessageKey } from "@/lib/i18n/en";
import { useHref } from "@/lib/params";
import { profileExtras, type SeriesPoint } from "@/lib/profileExtras";
import { configText, useConfig } from "@/lib/useConfig";
import { useCustomer, type HistoryFigure } from "@/lib/useCustomer";
import { useCustomerCases, type CaseExtra } from "@/lib/useCustomerCases";
import type { AuditEvent, CaseSummary, CustomerProfile } from "@/lib/types";
import { LiveInterestTicker } from "../case/LiveInterestTicker";
import { IdempotentButton } from "../common/IdempotentButton";
import { Icon } from "../common/Icon";
import { Money } from "../common/Money";
import { ErrorState, Skeleton } from "../common/States";
import { StatusIcon } from "../common/StatusIcon";
import { Banner, DataBanners } from "../shell/Banners";
import { PlaceholderBadge } from "../shell/PlaceholderBadge";
import { RecordPaymentDrawer } from "../payments/RecordPaymentDrawer";
import { PaymentHistoryChart } from "./PaymentHistoryChart";
import { ReviewedChanges } from "./ReviewedChanges";

type T = ReturnType<typeof useT>["t"];

const GST_STATE = /^(\d{2})/;

// The state names the dictionary has; an unknown code falls back to "State NN".
const STATE_KEYS: Record<string, true> = Object.fromEntries(Object.keys(en).filter((k) => k.startsWith("gst_state.")).map((k) => [k, true]));

function stateKey(gstin: string): MessageKey | null {
  const code = GST_STATE.exec(gstin)?.[1];
  const key = code ? `gst_state.${code}` : null;
  return key && key in STATE_KEYS ? (key as MessageKey) : null;
}

// ------------------------------------------------------------------ header --

function Header({ p, offline, refresh }: { p: CustomerProfile; offline: boolean; refresh: () => void }) {
  const { t } = useT();
  const href = useHref();
  const gstins = p.customer.gstins ?? [];
  const done = () => {
    announceBookChange();
    refresh();
  };

  return (
    <header className="flex flex-col gap-4">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex min-w-0 flex-col gap-1.5">
          <h1 className="text-[1.75rem] font-semibold leading-tight tracking-[-0.02em] text-ink-950">{p.customer.display_name}</h1>
          <p className="flex flex-wrap items-center gap-2 text-sm text-ink-600">
            {p.customer.kind === "PAN" ? (
              <span className="num">{t("profile.pan", { pan: p.customer.pan ?? "" })}</span>
            ) : (
              <StatusIcon size="sm" tone="info" icon="open" label={t("profile.provisional")} />
            )}
            {p.group && (
              <span className="inline-flex items-center gap-1">
                <span aria-hidden="true">·</span>
                {t("profile.group_member", { label: p.group.label, n: count(Math.max(p.group.member_count, (p.group.members ?? []).length)) })}
              </span>
            )}
          </p>
        </div>
        <div className="flex flex-wrap items-start gap-2">
          <Link href={href("/upload")} className="btn btn-primary">
            <Icon name="upload" className="h-4 w-4" />
            {t("profile.upload")}
          </Link>
          <Link href={href("/import")} className="btn btn-secondary">
            {t("profile.import")}
          </Link>
          {p.group && (
            <IdempotentButton
              actionId={bookAction.unlinkFromGroup(p.group.id, p.customer.id)}
              run={(opts) => unlinkFromGroup(p.group!.id, p.customer.id, opts)}
              onConflict={refresh}
              onDone={done}
              offline={offline}
              className="btn btn-secondary"
            >
              {t("profile.unlink")}
            </IdempotentButton>
          )}
        </div>
      </div>

      {gstins.length > 0 && (
        <ul aria-label={t("profile.gstins")} className="flex flex-wrap gap-2">
          {gstins.map((g) => {
            const key = stateKey(g);
            const code = GST_STATE.exec(g)?.[1] ?? "";
            return (
              <li key={g} className="inline-flex items-center gap-2 rounded-full border border-rule bg-white py-1 pl-3 pr-1.5 text-xs">
                <span className="font-medium text-ink-800">{key ? t(key) : t("profile.state_code", { code })}</span>
                <span className="num text-ink-500">{g}</span>
                {gstins.length > 1 && (
                  <IdempotentButton
                    actionId={bookAction.detachGstin(p.customer.id, g)}
                    run={(opts) => detachGstin(p.customer.id, g, opts)}
                    onConflict={refresh}
                    onDone={done}
                    offline={offline}
                    className="rounded-full px-2 py-0.5 text-xs text-ink-600 hover:bg-paper-sunk hover:text-ink-950"
                  >
                    {t("profile.detach")}
                  </IdempotentButton>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </header>
  );
}

// ------------------------------------------------------------------- tiles --

function Tile({ label, children, note }: { label: string; children: React.ReactNode; note?: string }) {
  return (
    <div className="flex min-w-0 flex-col gap-1.5 bg-white px-4 py-3.5">
      <dt className="text-xs text-ink-500">{label}</dt>
      <dd className="figure text-lg text-ink-950">{children}</dd>
      {note && <dd className="text-xs leading-snug text-ink-500">{note}</dd>}
    </div>
  );
}

function historyNote(f: HistoryFigure | null, t: T): string | undefined {
  if (!f) return undefined;
  return f.kind === "value" ? t("stats.based_on", { n: count(f.basedOn) }) : t("stats.not_enough_history", { n: count(f.basedOn), min: count(f.min) });
}

function InterestTile({ interestNow, overdue, extras }: { interestNow: string | null; overdue: CaseSummary[]; extras: Map<string, CaseExtra> | null }) {
  const { t } = useT();
  if (interestNow !== null) return <Money value={interestNow} />;
  if (overdue.length === 0) return <span className="text-sm font-normal text-ink-500">{t("customers.interest_none")}</span>;
  if (overdue.length > 1) return <span className="text-sm font-normal text-ink-600">{t("customers.interest_several", { n: count(overdue.length) })}</span>;
  if (extras === null) return <Skeleton className="h-6 w-24" />;
  const fin = extras.get(overdue[0].id)?.detail?.latest_evaluation?.financials;
  return fin ? (
    <LiveInterestTicker interest={fin.interest_outstanding} dailyAccrual={fin.daily_accrual} />
  ) : (
    <span className="text-sm font-normal text-ink-500">{t("customers.interest_unknown")}</span>
  );
}

// ---------------------------------------------------------------- invoices --

function InvoicesTable({ cases, series, extras, payments, offline, refresh }: {
  cases: CaseSummary[];
  series: Map<string, SeriesPoint>;
  extras: Map<string, CaseExtra> | null;
  payments: CustomerProfile["payments"];
  offline: boolean;
  refresh: () => void;
}) {
  const { t } = useT();
  const href = useHref();
  const [recordFor, setRecordFor] = useState<string | null>(null);
  // The last recorded (not voided) payment date per invoice, picked from the profile, not computed.
  const lastPaid = new Map<string, string>();
  for (const pay of payments ?? []) {
    if (pay.voided_at) continue;
    const prev = lastPaid.get(pay.case_id);
    if (!prev || pay.paid_on > prev) lastPaid.set(pay.case_id, pay.paid_on);
  }

  return (
    <section aria-labelledby="invoices-title" className="flex flex-col gap-2">
      <h2 id="invoices-title" className="text-base font-semibold text-ink-950">{t("profile.invoices")}</h2>
      {cases.length === 0 ? (
        <p className="text-sm text-ink-500">{t("customers.no_cases")}</p>
      ) : (
        <div className="panel overflow-x-auto" tabIndex={0} role="region" aria-label={t("profile.invoices")}>
          <table className="w-full min-w-[60rem] text-left text-sm">
            <thead className="border-b border-rule bg-paper text-xs text-ink-500">
              <tr>
                {(["invoice", "status", "amount", "accepted", "due", "paid", "days", "track", "action"] as const).map((c) => (
                  <th key={c} scope="col" className={`px-4 py-2.5 font-medium ${c === "amount" || c === "days" ? "text-right" : ""}`}>
                    {t(`profile.col.${c}`)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-rule">
              {cases.map((c) => {
                const s = series.get(c.id);
                const accepted = s?.accepted_on ?? extras?.get(c.id)?.detail?.latest_evaluation?.timeline?.acceptance_date ?? null;
                const paidOn = s?.paid_on ?? lastPaid.get(c.id) ?? null;
                const chip = trackChip(c.active_track);
                const overdue = (c.days_overdue ?? 0) > 0;
                return (
                  <tr key={c.id} className="align-top">
                    <td className="px-4 py-3">
                      <Link href={href(`/case/${encodeURIComponent(c.id)}`)} className="num whitespace-nowrap font-medium text-ink-950 underline-offset-2 hover:underline">
                        {c.invoice_no}
                      </Link>
                    </td>
                    <td className="px-4 py-3">
                      {s?.days_to_pay !== null && s?.days_to_pay !== undefined ? (
                        <StatusIcon size="sm" tone={s.on_time === false ? "warn" : "ok"} icon={s.on_time === false ? "clock" : "ok"} label={t(s.on_time === false ? "profile.status.paid_late" : "profile.status.paid")} />
                      ) : overdue ? (
                        <StatusIcon size="sm" tone="warn" icon="clock" label={t("profile.status.overdue", { n: count(c.days_overdue) })} />
                      ) : (
                        <StatusIcon size="sm" tone="info" icon="clock" label={t("profile.status.open")} />
                      )}
                    </td>
                    <td className="px-4 py-3 text-right"><span className="figure">{money(c.accepted_amount)}</span></td>
                    <td className="whitespace-nowrap px-4 py-3">{date(accepted)}</td>
                    <td className="whitespace-nowrap px-4 py-3">{date(s?.due_date ?? c.due_date)}</td>
                    <td className="whitespace-nowrap px-4 py-3">{date(paidOn)}</td>
                    <td className="num whitespace-nowrap px-4 py-3 text-right">
                      {s?.days_to_pay != null ? count(s.days_to_pay) : s?.days_open_so_far != null ? t("chart.so_far", { n: count(s.days_open_so_far) }) : "—"}
                    </td>
                    <td className="px-4 py-3">
                      <StatusIcon
                        size="sm"
                        wrap
                        tone={chip.tone}
                        icon={chip.icon}
                        label={chip.prefix ? `${t(chip.prefix)} · ${t(chip.status as MessageKey, chip.vars)}` : t(chip.status as MessageKey)}
                      />
                    </td>
                    <td className="px-4 py-3">
                      {s?.days_to_pay == null && (
                        <button type="button" className="btn btn-secondary min-h-8 px-3 text-xs" disabled={offline} aria-haspopup="dialog" onClick={() => setRecordFor(c.id)}>
                          {t("pay.record")}
                          <span className="sr-only"> {c.invoice_no}</span>
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {recordFor && <RecordPaymentDrawer caseId={recordFor} open onClose={() => setRecordFor(null)} onRecorded={refresh} />}
    </section>
  );
}

// ---------------------------------------------------------------- timeline --

type Entry = { at: string; text: string; icon: "doc" | "send" | "ok" | "info" | "ledger" | "clock" };

const payloadOf = (e: AuditEvent): Record<string, unknown> => (e.payload_json ?? {}) as Record<string, unknown>;

function eventEntry(e: AuditEvent, invoiceNo: string, t: T): Entry {
  const p = payloadOf(e);
  const stage = typeof p.stage === "number" || typeof p.stage === "string" ? String(p.stage) : "";
  const kind = typeof p.kind === "string" ? p.kind : "";
  const base = { at: e.created_at };
  switch (e.type) {
    case "case.created":
      return { ...base, icon: "doc", text: t("history.case_created", { no: invoiceNo }) };
    case "track.created":
      return { ...base, icon: "info", text: t(kind === "FINANCING" ? "history.option_early" : kind === "RECOVERY" ? "history.option_recover" : "history.option", { no: invoiceNo }) };
    case "recovery.prepare":
      return { ...base, icon: "doc", text: t("history.prepared", { n: stage, no: invoiceNo }) };
    case "recovery.mark_sent":
      return { ...base, icon: "send", text: t("history.sent", { n: stage, no: invoiceNo }) };
    case "payment.recorded":
      return { ...base, icon: "ledger", text: t("history.payment", { no: invoiceNo, amount: typeof p.amount === "string" ? money(p.amount) : "" }) };
    case "payment.voided":
      return { ...base, icon: "ledger", text: t("history.payment_voided", { no: invoiceNo }) };
    case "financing.disbursed":
    case "payout.processed":
      return { ...base, icon: "ok", text: t("history.disbursed", { no: invoiceNo }) };
    default:
      return { ...base, icon: "clock", text: t("history.other", { type: e.type, no: invoiceNo }) };
  }
}

function Timeline({ p, extras }: { p: CustomerProfile; extras: Map<string, CaseExtra> | null }) {
  const { t } = useT();
  const entries = useMemo(() => {
    const out: Entry[] = [];
    const cases = p.cases ?? [];
    const withPaymentEvents = new Set<string>();
    for (const c of cases) {
      for (const e of extras?.get(c.id)?.events ?? []) {
        if (e.type.startsWith("payment.")) withPaymentEvents.add(c.id);
        out.push(eventEntry(e, c.invoice_no, t));
      }
    }
    const noOf = new Map(cases.map((c) => [c.id, c.invoice_no]));
    for (const pay of p.payments ?? []) {
      if (withPaymentEvents.has(pay.case_id)) continue;
      const no = noOf.get(pay.case_id) ?? "";
      out.push({ at: pay.created_at, icon: "ledger", text: t("history.payment", { no, amount: money(pay.amount) }) });
      if (pay.voided_at) out.push({ at: pay.voided_at, icon: "ledger", text: t("history.payment_voided", { no }) });
    }
    if (p.group) out.push({ at: p.group.created_at, icon: "info", text: t("history.linked", { label: p.group.label }) });
    // ISO timestamps sort as text; newest first.
    return out.filter((x) => x.at).sort((a, b) => (a.at < b.at ? 1 : a.at > b.at ? -1 : 0));
  }, [p, extras, t]);

  return (
    <section aria-labelledby="history-events-title" className="flex flex-col gap-2">
      <h2 id="history-events-title" className="text-base font-semibold text-ink-950">{t("history.title")}</h2>
      {extras === null ? (
        <Skeleton className="h-24" />
      ) : entries.length === 0 ? (
        <p className="text-sm text-ink-500">{t("history.empty")}</p>
      ) : (
        <ol className="panel flex flex-col divide-y divide-rule">
          {entries.map((e, i) => (
            <li key={`${e.at}-${i}`} className="flex items-start gap-3 px-5 py-3 text-sm">
              <Icon name={e.icon} className="mt-0.5 h-4 w-4 shrink-0 text-ink-500" />
              <span className="flex-1 text-ink-800">{e.text}</span>
              <time dateTime={e.at} className="num shrink-0 text-xs text-ink-500">{date(e.at.slice(0, 10))}</time>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

// -------------------------------------------------------- delay cost panel --

function DelayCosts({ cases, extras, placeholder }: { cases: CaseSummary[]; extras: Map<string, CaseExtra> | null; placeholder: boolean }) {
  const { t } = useT();
  const withCost = cases.filter((c) => extras?.get(c.id)?.detail?.latest_evaluation?.buyer_cost);
  const [pick, setPick] = useState(0);
  const c = withCost[Math.min(pick, withCost.length - 1)];
  const bc = c ? extras?.get(c.id)?.detail?.latest_evaluation?.buyer_cost : null;

  return (
    <section aria-labelledby="costs-title" className="flex flex-col gap-3">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div className="flex flex-col gap-1">
          <h2 id="costs-title" className="text-base font-semibold text-ink-950">{t("profile.costs.title")}</h2>
          <p className="text-sm text-ink-600">{t("profile.costs.sub")}</p>
        </div>
        {withCost.length > 1 && (
          <label className="inline-flex items-center gap-2 text-sm text-ink-700">
            {t("profile.costs.invoice")}
            <select value={pick} onChange={(e) => setPick(Number(e.target.value))} className="min-h-9 rounded-md border border-rule bg-white px-2.5 text-sm text-ink-950">
              {withCost.map((x, i) => (
                <option key={x.id} value={i}>{x.invoice_no}</option>
              ))}
            </select>
          </label>
        )}
      </div>
      {extras === null ? (
        <Skeleton className="h-28" />
      ) : !bc || !c ? (
        <p className="text-sm text-ink-500">{t("profile.costs.none")}</p>
      ) : (
        <div className="grid gap-3 md:grid-cols-3">
          <div className="panel flex flex-col gap-2 p-5">
            <span className="eyebrow">{t("cfo.line", { n: 1 })}</span>
            <h3 className="font-semibold text-ink-950">{t("cfo.permanent.title")}</h3>
            <Money value={bc.permanent_loss.interest_non_deductible} placeholder={placeholder} className="figure text-xl" />
            <p className="text-xs text-ink-600">{t("cfo.permanent.body", { rate: pct(bc.permanent_loss.pretax_equivalent_rate_pct) })}</p>
          </div>
          <div className="panel flex flex-col gap-2 p-5">
            <span className="eyebrow">{t("cfo.line", { n: 2 })}</span>
            <h3 className="font-semibold text-ink-950">{t("cfo.deferral.title")}</h3>
            {bc.deferral.applies && bc.deferral.deferral_cost ? (
              <>
                <Money value={bc.deferral.deferral_cost} placeholder={placeholder} className="figure text-xl" />
                <p className="text-xs text-ink-600">{t("cfo.deferral.cost")}</p>
              </>
            ) : (
              <p className="text-sm text-ink-700">{t("cfo.deferral.none")}</p>
            )}
          </div>
          <div className="panel flex flex-col gap-2 p-5">
            <span className="eyebrow">{t("cfo.line", { n: 3 })}</span>
            <h3 className="font-semibold text-ink-950">{t("cfo.disclosure.title")}</h3>
            {bc.disclosure_flags.length === 0 ? (
              <p className="text-sm text-ink-700">{t("profile.costs.no_flags")}</p>
            ) : (
              <ul className="flex flex-col gap-1.5 text-sm text-ink-700">
                {bc.disclosure_flags.map((f) => (
                  <li key={f.id} className="flex items-start gap-1.5">
                    <Icon name="info" className="mt-0.5 h-3.5 w-3.5 shrink-0 text-ink-500" />
                    {f.text}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
      <p className="text-xs text-ink-500">{t("profile.costs.separate")}</p>
    </section>
  );
}

// ------------------------------------------------------------------ screen --

export function CustomerProfileScreen({ customerId }: { customerId: string }) {
  const { t } = useT();
  const href = useHref();
  const view = useCustomer(customerId);
  const { config } = useConfig();
  const p = view.data;
  const ph = view.placeholder;
  const offline = view.source !== "live";
  const cases = useMemo(() => p?.cases ?? [], [p]);
  const extrasData = useMemo(() => (p ? profileExtras(p) : null), [p]);
  const extras = useCustomerCases(
    cases.map((c) => c.id),
    view.source,
  );
  const series = useMemo(() => new Map((extrasData?.series ?? []).map((s) => [s.case_id, s])), [extrasData]);
  const capText = configText(config, "credit_cap_days");
  const cap = capText !== null && /^\d+$/.test(capText) ? Number(capText) : null;
  const overdue = cases.filter((c) => (c.days_overdue ?? 0) > 0);

  const onTime = view.onTimePct;
  const onTimeText =
    onTime?.kind === "value"
      ? extrasData?.onTimeCount !== null && extrasData?.onTimeCount !== undefined
        ? t("profile.on_time_x_of_n", { x: count(extrasData.onTimeCount), n: count(onTime.basedOn) })
        : pct(onTime.value)
      : null;

  return (
    <div className="flex flex-col gap-7">
      <Link href={href("/")} className="inline-flex items-center gap-1.5 self-start text-sm text-ink-600 hover:text-ink-950">
        <Icon name="arrow-left" className="h-4 w-4" />
        {t("profile.back")}
      </Link>
      {view.source === "offline" && <Banner tone="warn" icon="lock" message="book.offline_sample" />}
      <DataBanners placeholder={ph} />

      {view.error && !p ? (
        <ErrorState message={view.error.detail ?? t(view.error.key)} onRetry={view.refresh} />
      ) : !p ? (
        <div className="panel flex flex-col gap-3 p-5" aria-busy="true">
          <span className="sr-only">{t("state.loading")}</span>
          <Skeleton className="h-8 w-64" />
          <Skeleton className="h-20" />
        </div>
      ) : (
        <>
          <Header p={p} offline={offline} refresh={view.refresh} />
          <ReviewedChanges customerId={p.customer.id} offline={offline} refresh={view.refresh} />

          <section aria-label={t("profile.stats_label")} className="flex flex-col gap-1.5">
            <dl className="panel grid grid-cols-2 gap-px overflow-hidden bg-rule sm:grid-cols-3 xl:grid-cols-6">
              <Tile label={t("insights.outstanding")}>
                <Money value={p.stats.outstanding_total} />
                {ph && <PlaceholderBadge />}
              </Tile>
              <Tile label={t("insights.overdue")} note={p.stats.oldest_overdue_days ? t("profile.oldest", { n: count(p.stats.oldest_overdue_days) }) : undefined}>
                <Money value={p.stats.overdue_total} />
                {ph && <PlaceholderBadge />}
              </Tile>
              <Tile label={t("customers.col.interest")}>
                <InterestTile interestNow={extrasData?.interestNow ?? null} overdue={overdue} extras={extras} />
              </Tile>
              <Tile
                label={t("insights.avg_days")}
                note={[historyNote(view.avgDaysToPay, t), cap !== null ? t("customers.legal_limit", { n: count(cap) }) : null].filter(Boolean).join(" · ")}
              >
                {view.avgDaysToPay?.kind === "value" ? (
                  t("insights.avg_days_value", { n: approxDays(view.avgDaysToPay.value) })
                ) : (
                  <span className="text-sm font-normal text-ink-600">{t("customers.not_enough")}</span>
                )}
              </Tile>
              <Tile label={t("insights.on_time")} note={historyNote(onTime, t)}>
                {onTimeText ?? <span className="text-sm font-normal text-ink-600">{t("customers.not_enough")}</span>}
              </Tile>
              <Tile label={t("profile.last_payment")}>{p.stats.last_payment_on ? date(p.stats.last_payment_on) : <span className="text-sm font-normal text-ink-500">{t("profile.no_payment_yet")}</span>}</Tile>
            </dl>
            <p className="text-xs text-ink-500">
              {t("stats.days_from_acceptance")} {t("stats.on_time_rule")} {t("book.own_data_only")}
            </p>
          </section>

          {extrasData?.series && extrasData.series.length > 0 ? (
            <PaymentHistoryChart series={extrasData.series} cap={cap} />
          ) : (
            <section className="panel flex items-start gap-3 p-5 text-sm text-ink-600">
              <Icon name="info" className="mt-0.5 h-4 w-4 shrink-0" />
              <p>{t(cases.length === 0 ? "chart.no_invoices" : extrasData?.series ? "chart.no_history" : "chart.unavailable")}</p>
            </section>
          )}

          <InvoicesTable cases={cases} series={series} extras={extras} payments={p.payments} offline={offline} refresh={view.refresh} />
          <Timeline p={p} extras={extras} />
          <DelayCosts cases={cases} extras={extras} placeholder={ph} />
        </>
      )}
    </div>
  );
}
