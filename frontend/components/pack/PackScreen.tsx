"use client";

import Link from "next/link";
import { isPlaceholder, isStageBlocked } from "@/lib/derive";
import { date, money } from "@/lib/format";
import { useT } from "@/lib/i18n";
import { useHref } from "@/lib/params";
import { useEvaluation } from "@/lib/useEvaluation";
import type { CaseRequest, ReadinessBand } from "@/lib/types";
import type { Tone } from "@/lib/derive";
import { Icon } from "../common/Icon";
import { CaseSkeleton, ErrorState, NotFoundState } from "../common/States";
import { StatusIcon } from "../common/StatusIcon";
import { Banner, DataBanners } from "../shell/Banners";
import { CaseHeader } from "../case/CaseHeader";
import { JudgeConsole } from "../shell/JudgeConsole";
import { LedgerTable } from "../case/LedgerTable";

const BAND_TONE: Record<ReadinessBand, Tone> = { COURT_READY: "ok", EVIDENCE_COMPLETE: "ok", ACTION_NEEDED: "warn", BLOCKED: "block" };

type ChronoItem = { date: string; label: string; ref: string | null };

function chronology(req: CaseRequest, t: ReturnType<typeof useT>["t"]): ChronoItem[] {
  const tx = req.transaction;
  const items: ChronoItem[] = [];
  if (tx.contract_date) items.push({ date: tx.contract_date, label: t("pack.chrono.contract"), ref: null });
  items.push({ date: tx.invoice_date, label: t("pack.chrono.invoice"), ref: null });
  if (tx.delivery_date) items.push({ date: tx.delivery_date, label: t("pack.chrono.delivery"), ref: null });
  (req.objections ?? []).forEach((o) => items.push({ date: o.raised_date, label: t("pack.chrono.objection"), ref: o.description ?? null }));
  (req.part_payments ?? []).forEach((p) =>
    items.push({ date: p.date, label: t("pack.chrono.payment", { amount: money(p.amount) }), ref: p.reference ?? null }),
  );
  (req.acknowledgments ?? []).forEach((a) =>
    items.push({ date: a.date, label: t("pack.chrono.ack", { kind: t(`ack.${a.kind}`) }), ref: a.source_ref ?? null }),
  );
  // ISO dates sort correctly as text.
  return items.sort((a, b) => a.date.localeCompare(b.date));
}

/** Stage 4: checklist + evidence bundle + interest sheet. Never a government form. */
export function PackScreen({ caseId }: { caseId: string }) {
  const { t } = useT();
  const href = useHref();
  const ev = useEvaluation(caseId);
  if (ev.status === "not_found") return <NotFoundState />;
  const res = ev.response;
  const req = ev.request;
  const placeholder = isPlaceholder(res);
  const blocked = res ? isStageBlocked(res, 4) : false;

  return (
    <div className="flex flex-col gap-6">
      <CaseHeader caseId={caseId} request={req} response={res} showViewToggle={false} />
      <DataBanners placeholder={placeholder} needsBackend={ev.status === "needs_backend"} />
      {ev.status === "loading" && !res && <CaseSkeleton />}
      {ev.status === "error" && !res && <ErrorState message={ev.error ?? t("state.error_title")} onRetry={ev.retry} />}

      {res && req && (
        <article className="flex flex-col gap-6">
          <p className="hidden border border-ink-900 px-3 py-2 font-semibold print:block">{t("pack.print_banner")}</p>
          <header className="flex flex-col gap-2">
            <div className="flex flex-wrap items-center gap-3">
              <h2 className="text-2xl font-semibold tracking-[-0.02em] text-ink-950">{t("pack.title")}</h2>
              <StatusIcon size="sm" tone="info" icon="doc" label={t("badge.draft")} />
            </div>
            <p className="text-sm text-ink-600">
              {t("pack.subtitle")} · {t("pack.intro")}
            </p>
            <p className="flex items-center gap-1.5 text-xs text-warn">
              <Icon name="info" className="h-3.5 w-3.5" />
              {t("pack.portal_fields")}
            </p>
          </header>

          {blocked && <Banner tone="block" icon="lock" message="pack.blocked" />}

          <section aria-labelledby="pack-check" className="panel p-6">
            <h3 id="pack-check" className="section-title">{t("pack.checklist")}</h3>
            <div className="mt-3 flex flex-wrap items-center gap-3">
              <StatusIcon size="sm" tone={BAND_TONE[res.evidence_readiness.band]} label={t(`readiness.${res.evidence_readiness.band}`)} />
              <span className="num text-sm text-ink-700">
                {t("readiness.score", { n: res.evidence_readiness.score })}
                {placeholder && ` (${t("badge.placeholder")})`}
              </span>
            </div>
            <ul className="mt-4 grid gap-x-8 sm:grid-cols-2">
              {req.evidence.items.map((i) => (
                <li key={i.kind} className="flex items-center justify-between gap-3 border-b border-rule py-2.5">
                  <span className="flex min-w-0 flex-col">
                    <span className="text-sm text-ink-950">{t(`evidence.${i.kind}`)}</span>
                    {i.ref && <span className="num truncate text-xs text-ink-500">{i.ref}</span>}
                  </span>
                  <StatusIcon size="sm" tone={i.present ? "ok" : "warn"} label={t(i.present ? "pack.have" : "pack.missing")} />
                </li>
              ))}
            </ul>
            {res.evidence_readiness.reasons.length > 0 && (
              <ul className="mt-4 flex flex-col gap-1.5 text-sm text-ink-700">
                {res.evidence_readiness.reasons.map((r, i) => (
                  <li key={`${r.code}-${i}`} className="flex gap-3">
                    <span className="num w-8 shrink-0 text-right text-ink-500">{r.delta > 0 ? `+${r.delta}` : r.delta}</span>
                    <span>{r.text}</span>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section aria-labelledby="pack-chrono" className="panel p-6">
            <h3 id="pack-chrono" className="section-title">{t("pack.chronology")}</h3>
            <ol className="mt-3 flex flex-col divide-y divide-rule text-sm">
              {chronology(req, t).map((c, i) => (
                <li key={`${c.date}-${i}`} className="grid gap-1 py-2.5 sm:grid-cols-[8rem_1fr]">
                  <span className="num text-ink-500">{date(c.date)}</span>
                  <span className="text-ink-950">
                    {c.label}
                    {c.ref && <span className="ml-2 font-mono text-xs text-ink-600">{c.ref}</span>}
                  </span>
                </li>
              ))}
            </ol>
          </section>

          {res.financials && (
            <section aria-labelledby="pack-interest" className="panel p-6">
              <h3 id="pack-interest" className="section-title mb-4">{t("pack.interest_sheet")}</h3>
              <LedgerTable financials={res.financials} placeholder={placeholder} />
            </section>
          )}

          <section aria-labelledby="pack-cert" className="panel border-dashed p-6">
            <div className="flex flex-wrap items-center gap-3">
              <h3 id="pack-cert" className="section-title">{t("pack.certificate.title")}</h3>
              <StatusIcon size="sm" tone="warn" icon="doc" label={t("badge.template")} />
            </div>
            <p className="mt-3 max-w-3xl whitespace-pre-line text-sm leading-relaxed text-ink-800">{t("pack.certificate.body", { supplier: req.supplier.name })}</p>
          </section>

          {!blocked && (
            <div className="no-print flex flex-col items-start gap-2">
              <button type="button" className="btn btn-primary" onClick={() => window.print()}>
                <Icon name="doc" className="h-4 w-4" />
                {t("pack.download")}
              </button>
              <p className="text-xs text-ink-500">{t("pack.download_hint")}</p>
            </div>
          )}
        </article>
      )}

      <Link href={href(`/case/${caseId}`)} className="no-print btn btn-quiet self-start">
        <Icon name="arrow-left" className="h-4 w-4" />
        {t("nav.back_to_case")}
      </Link>
      <JudgeConsole current={null} />
    </div>
  );
}
