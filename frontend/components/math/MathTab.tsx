"use client";

import { useT } from "@/lib/i18n";
import type { CaseRequest, CaseResponse, StatuteConfig } from "@/lib/types";
import { AssumptionsDrawer } from "../case/AssumptionsDrawer";
import { LedgerTable } from "../case/LedgerTable";
import { KpiCards } from "./KpiCards";
import { PricingToggles } from "./PricingToggles";
import { SettlementSimulator } from "./SettlementSimulator";

/**
 * Math tab (?tab=math): the engine's figures, its ledger, the two pricing
 * choices it can be asked to re-run with, its assumptions, and a settlement
 * simulator. The browser formats; the engine computes.
 */
export function MathTab({
  request,
  response,
  placeholder,
  config,
  configLoading,
  configIsStub,
  onChange,
}: {
  request: CaseRequest;
  response: CaseResponse;
  placeholder: boolean;
  config: StatuteConfig | null;
  configLoading: boolean;
  configIsStub: boolean;
  onChange: (next: CaseRequest) => void;
}) {
  const { t } = useT();
  const fin = response.financials;
  return (
    <div className="flex flex-col gap-4">
      {fin ? (
        <>
          <KpiCards financials={fin} placeholder={placeholder} />
          <PricingToggles request={request} response={response} onChange={onChange} />
          <section aria-labelledby="ledger-title" className="panel flex flex-col gap-3 p-6">
            <h2 id="ledger-title" className="section-title">{t("ledger.title")}</h2>
            <LedgerTable financials={fin} placeholder={placeholder} expandable />
          </section>
        </>
      ) : (
        <section className="panel p-6">
          <p className="text-sm text-ink-600">{t("money.unavailable")}</p>
        </section>
      )}
      <AssumptionsDrawer response={response} config={config} configLoading={configLoading} configIsStub={configIsStub} />
      <SettlementSimulator request={request} hasClaim={Boolean(fin)} />
    </div>
  );
}
