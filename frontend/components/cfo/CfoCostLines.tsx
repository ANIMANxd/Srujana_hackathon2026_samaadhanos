"use client";

import { useState, type ReactNode } from "react";
import { date, money, pct } from "@/lib/format";
import { useT } from "@/lib/i18n";
import type { CaseRequest, CaseResponse } from "@/lib/types";
import { Icon } from "../common/Icon";
import { Money } from "../common/Money";
import { StatusIcon } from "../common/StatusIcon";
import { LiveInterestTicker } from "../case/LiveInterestTicker";
import { PlaceholderBadge } from "../shell/PlaceholderBadge";
import { CfoSettlementOptions } from "./CfoSettlementOptions";
import { CfoUnavailable } from "./CfoUnavailable";

const DECIMAL = /^\d+(\.\d{1,4})?$/;

function Line({ n, title, sub, children }: { n: number; title: string; sub: string; children: ReactNode }) {
  const { t } = useT();
  return (
    <section aria-labelledby={`cfo-${n}`} className="panel flex flex-col gap-4 p-6">
      <div className="flex flex-col gap-1">
        <span className="eyebrow">{t("cfo.line", { n })}</span>
        <h3 id={`cfo-${n}`} className="text-lg font-semibold tracking-[-0.01em] text-ink-950">{title}</h3>
        <p className="text-sm text-ink-600">{sub}</p>
      </div>
      {children}
    </section>
  );
}

/**
 * Buyer CFO view (F6): three SEPARATE cost lines, advisory tone, never one total
 * (golden rule 8). The only inputs are the buyer's own assumptions, which go
 * back to the engine for recomputation.
 */
export function CfoCostLines({
  caseId,
  request,
  response,
  placeholder,
  onChangeRequest,
}: {
  caseId: string;
  request: CaseRequest;
  response: CaseResponse;
  placeholder: boolean;
  onChangeRequest: (next: CaseRequest) => void;
}) {
  const { t } = useT();
  const bc = response.buyer_cost;
  const fin = response.financials;
  const [coc, setCoc] = useState(request.buyer.cost_of_capital_pct);
  const [years, setYears] = useState(request.transaction.years_deferred ?? "");

  if (!bc) return <CfoUnavailable caseId={caseId} response={response} />;

  const cocValid = DECIMAL.test(coc);
  const yearsValid = years === "" || DECIMAL.test(years);

  function apply() {
    if (!cocValid || !yearsValid) return;
    onChangeRequest({
      ...request,
      buyer: { ...request.buyer, cost_of_capital_pct: coc },
      transaction: { ...request.transaction, years_deferred: years === "" ? null : years },
    });
  }

  return (
    <div className="flex flex-col gap-4">
      <header className="flex flex-col gap-3 py-2 sm:flex-row sm:items-end sm:justify-between">
        <div className="flex flex-col gap-1.5">
          <h2 className="text-2xl font-semibold tracking-[-0.02em] text-ink-950">{t("cfo.title")}</h2>
          <p className="max-w-xl text-sm text-ink-600">{t("cfo.intro")}</p>
        </div>
        {fin && (
          <p className="flex items-center gap-2 text-sm text-ink-600">
            <span className="live-dot" aria-hidden="true" />
            {t("cfo.ticker")}
            <LiveInterestTicker interest={fin.interest_outstanding} dailyAccrual={fin.daily_accrual} className="text-ink-950" />
            {placeholder && <PlaceholderBadge />}
          </p>
        )}
      </header>

      <div className="grid gap-4 lg:grid-cols-3">
        <Line n={1} title={t("cfo.permanent.title")} sub={t("cfo.permanent.sub")}>
          <Money value={bc.permanent_loss.interest_non_deductible} placeholder={placeholder} className="figure text-[2rem]" />
          <p className="text-sm text-ink-700">{t("cfo.permanent.body", { rate: pct(bc.permanent_loss.pretax_equivalent_rate_pct) })}</p>
        </Line>

        <Line n={2} title={t("cfo.deferral.title")} sub={t("cfo.deferral.sub")}>
          {bc.deferral.applies && bc.deferral.checkpoints.length > 0 ? (
            <>
              {bc.deferral.deferral_cost && (
                <div className="flex flex-col gap-1">
                  <Money value={bc.deferral.deferral_cost} placeholder={placeholder} className="figure text-[2rem]" />
                  <span className="text-xs text-ink-500">{t("cfo.deferral.cost")}</span>
                </div>
              )}
              <ul className="flex flex-col divide-y divide-rule border-y border-rule text-sm">
                {bc.deferral.checkpoints.map((c) => (
                  <li key={c.fy_end} className="flex flex-col gap-0.5 py-2.5">
                    <span className="text-ink-950">{t("cfo.deferral.checkpoint", { fy: date(c.fy_end) })}</span>
                    <span className="num text-xs text-ink-600">
                      {t("cfo.deferral.unpaid", { principal: money(c.unpaid_principal) })} · {t("cfo.deferral.effect", { effect: money(c.tax_timing_effect) })}
                    </span>
                  </li>
                ))}
              </ul>
            </>
          ) : (
            <p className="text-sm text-ink-700">{t("cfo.deferral.none")}</p>
          )}
          <p className="flex gap-2 rounded-md bg-paper px-3 py-2.5 text-sm font-medium text-ink-900">
            <Icon name="info" className="mt-0.5 h-4 w-4 shrink-0 text-saffron-600" />
            {t("cfo.deferral.explainer")}
          </p>
          <p className="text-xs text-ink-500">{t("cfo.deferral.body")} {t("cfo.deferral.note")}</p>
        </Line>

        <Line n={3} title={t("cfo.disclosure.title")} sub={t("cfo.disclosure.sub")}>
          <ul className="flex flex-col gap-3">
            {bc.disclosure_flags.map((f) => (
              <li key={f.id} className="flex flex-col items-start gap-2 text-sm">
                <span className="text-ink-800">{f.text}</span>
                <StatusIcon size="sm" tone={f.verified ? "ok" : "warn"} label={t(f.verified ? "badge.verified" : "badge.unverified")} />
              </li>
            ))}
          </ul>
        </Line>
      </div>

      <section aria-labelledby="cfo-inputs" className="panel p-6">
        <h3 id="cfo-inputs" className="section-title">{t("cfo.deferral.inputs")}</h3>
        <div className="mt-4 grid gap-3 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
          <label>
            <span className="field-label">{t("cfo.deferral.coc")}</span>
            <input className="field-input num" inputMode="decimal" value={coc} aria-invalid={!cocValid} onChange={(e) => setCoc(e.target.value.trim())} />
          </label>
          <label>
            <span className="field-label">{t("cfo.deferral.years")}</span>
            <input className="field-input num" inputMode="decimal" value={years} aria-invalid={!yearsValid} onChange={(e) => setYears(e.target.value.trim())} />
          </label>
          <button type="button" className="btn btn-primary" onClick={apply} disabled={!cocValid || !yearsValid}>
            {t("cfo.deferral.recompute")}
          </button>
        </div>
      </section>

      {bc.other_pressure_points.length > 0 && (
        <section aria-labelledby="cfo-4" className="panel p-6">
          <h3 id="cfo-4" className="section-title">{t("cfo.other.title")}</h3>
          <ul className="mt-3 list-disc pl-5 text-sm text-ink-800">
            {bc.other_pressure_points.map((p) => (
              <li key={p.id}>{p.text}</li>
            ))}
          </ul>
        </section>
      )}
      {fin && <CfoSettlementOptions caseId={caseId} request={request} />}
    </div>
  );
}
