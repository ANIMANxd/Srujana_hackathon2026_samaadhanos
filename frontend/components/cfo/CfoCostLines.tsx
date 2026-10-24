"use client";

import { useState } from "react";
import { date, money, pct } from "@/lib/format";
import { useT } from "@/lib/i18n";
import type { CaseRequest, CaseResponse } from "@/lib/types";
import { Money } from "../common/Money";
import { StatusIcon } from "../common/StatusIcon";
import { LiveInterestTicker } from "../case/LiveInterestTicker";
import { PlaceholderBadge } from "../shell/PlaceholderBadge";

const DECIMAL = /^\d+(\.\d{1,4})?$/;

/**
 * Buyer CFO view (F5): three SEPARATE cost lines, advisory tone, never one total
 * (golden rule 8). The only inputs are the buyer's own assumptions, which go
 * back to the engine for recomputation.
 */
export function CfoCostLines({
  request,
  response,
  placeholder,
  onChangeRequest,
}: {
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

  if (!bc) {
    return (
      <section className="panel p-6">
        <p className="text-ink-800">{t("cfo.unavailable")}</p>
      </section>
    );
  }

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
    <div className="flex flex-col gap-5">
      <header className="flex flex-col gap-2">
        <h2 className="font-display text-3xl font-semibold tracking-tight text-ink-950">{t("cfo.title")}</h2>
        <p className="max-w-prose text-ink-700">{t("cfo.intro")}</p>
        {fin && (
          <p className="flex flex-wrap items-baseline gap-2 text-sm text-ink-600">
            <span>{t("cfo.ticker")}:</span>
            <LiveInterestTicker interest={fin.interest_outstanding} dailyAccrual={fin.daily_accrual} className="text-base text-ink-900" />
            {placeholder && <PlaceholderBadge />}
          </p>
        )}
      </header>

      {/* Line 1: permanent */}
      <section aria-labelledby="cfo-1" className="panel p-5">
        <h3 id="cfo-1" className="ledger-rule font-display text-xl font-semibold">{t("cfo.permanent.title")}</h3>
        <p className="mt-3 text-lg text-ink-900">
          {t("cfo.permanent.body", {
            amount: money(bc.permanent_loss.interest_non_deductible),
            rate: pct(bc.permanent_loss.pretax_equivalent_rate_pct),
          })}
        </p>
        <p className="mt-2">
          <Money value={bc.permanent_loss.interest_non_deductible} placeholder={placeholder} className="text-2xl font-semibold" />
        </p>
      </section>

      {/* Line 2: deferral */}
      <section aria-labelledby="cfo-2" className="panel p-5">
        <h3 id="cfo-2" className="ledger-rule font-display text-xl font-semibold">{t("cfo.deferral.title")}</h3>
        <p className="mt-3 text-ink-800">{t("cfo.deferral.body")}</p>
        {bc.deferral.applies && bc.deferral.checkpoints.length > 0 ? (
          <ul className="mt-3 flex flex-col gap-1.5">
            {bc.deferral.checkpoints.map((c) => (
              <li key={c.fy_end} className="num text-ink-900">
                {t("cfo.deferral.checkpoint", {
                  fy: date(c.fy_end),
                  principal: money(c.unpaid_principal),
                  effect: money(c.tax_timing_effect),
                })}
              </li>
            ))}
            {bc.deferral.deferral_cost && (
              <li className="mt-1 font-semibold text-ink-950">
                {t("cfo.deferral.cost", { cost: money(bc.deferral.deferral_cost) })}
                {placeholder && ` (${t("badge.placeholder")})`}
              </li>
            )}
          </ul>
        ) : (
          <p className="mt-3 text-ink-700">{t("cfo.deferral.none")}</p>
        )}
        <p className="mt-2 text-sm text-ink-600">{t("cfo.deferral.note")}</p>

        <fieldset className="mt-4 grid gap-3 border-t border-rule pt-4 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
          <legend className="mb-2 text-sm font-semibold text-ink-800">{t("cfo.deferral.inputs")}</legend>
          <label>
            <span className="field-label">{t("cfo.deferral.coc")}</span>
            <input
              className="field-input num"
              inputMode="decimal"
              value={coc}
              aria-invalid={!cocValid}
              onChange={(e) => setCoc(e.target.value.trim())}
            />
          </label>
          <label>
            <span className="field-label">{t("cfo.deferral.years")}</span>
            <input
              className="field-input num"
              inputMode="decimal"
              value={years}
              aria-invalid={!yearsValid}
              onChange={(e) => setYears(e.target.value.trim())}
            />
          </label>
          <button type="button" className="btn btn-secondary" onClick={apply} disabled={!cocValid || !yearsValid}>
            {t("cfo.deferral.recompute")}
          </button>
        </fieldset>
      </section>

      {/* Line 3: disclosure */}
      <section aria-labelledby="cfo-3" className="panel p-5">
        <h3 id="cfo-3" className="ledger-rule font-display text-xl font-semibold">{t("cfo.disclosure.title")}</h3>
        <ul className="mt-3 flex flex-col gap-2">
          {bc.disclosure_flags.map((f) => (
            <li key={f.id} className="flex flex-col items-start gap-1">
              <span className="text-ink-900">{f.text}</span>
              <StatusIcon size="sm" tone={f.verified ? "ok" : "warn"} label={t(f.verified ? "badge.verified" : "badge.unverified")} />
            </li>
          ))}
        </ul>
      </section>

      {bc.other_pressure_points.length > 0 && (
        <section aria-labelledby="cfo-4" className="panel p-5">
          <h3 id="cfo-4" className="ledger-rule font-display text-xl font-semibold">{t("cfo.other.title")}</h3>
          <ul className="mt-3 list-disc pl-5 text-ink-900">
            {bc.other_pressure_points.map((p) => (
              <li key={p.id}>{p.text}</li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
