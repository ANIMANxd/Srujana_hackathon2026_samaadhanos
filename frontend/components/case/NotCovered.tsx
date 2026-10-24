"use client";

import { eligibilityTone, evidenceKinds } from "@/lib/derive";
import { useT } from "@/lib/i18n";
import type { CaseRequest, CaseResponse } from "@/lib/types";
import { StatusIcon } from "../common/StatusIcon";

/** Full "Not covered" screen: shown instead of the case screen when the gate blocks. */
export function NotCovered({ request, response }: { request: CaseRequest; response: CaseResponse }) {
  const { t, tCode } = useT();
  const j = response.jurisdiction;
  const have = evidenceKinds(request, true);
  const missing = evidenceKinds(request, false);

  return (
    <section aria-labelledby="nc-title" className="flex flex-col gap-5">
      <div className="panel border-block/40 p-6">
        <StatusIcon tone={eligibilityTone(j.status)} label={t(`eligibility.${j.status}`)} />
        <h2 id="nc-title" className="mt-4 font-display text-3xl font-semibold tracking-tight text-ink-950">
          {t("eligibility.screen.title")}
        </h2>
        <p className="mt-3 text-lg text-ink-900">
          <span className="font-semibold">{t("eligibility.screen.reason")}: </span>
          {t(`eligibility.reason.${j.status}`)}
        </p>
        <p className="mt-2 text-sm text-ink-600">{t("eligibility.screen.based_on")}</p>
      </div>

      <div className="grid gap-5 md:grid-cols-2">
        <section aria-labelledby="nc-checks" className="panel p-5">
          <h3 id="nc-checks" className="ledger-rule font-display text-xl font-semibold">{t("eligibility.screen.checks")}</h3>
          <ul className="mt-3 flex flex-col gap-3">
            {j.checks.map((c) => (
              <li key={c.id} className="flex flex-col gap-1">
                <StatusIcon
                  size="sm"
                  tone={c.passed === true ? "ok" : c.passed === false ? "block" : "info"}
                  icon={c.passed === null ? "open" : undefined}
                  label={`${tCode("check", c.id, c.id)}: ${t(
                    c.passed === true ? "eligibility.check.passed" : c.passed === false ? "eligibility.check.failed" : "eligibility.check.open",
                  )}`}
                />
                <span className="text-sm text-ink-800">{c.detail}</span>
                <span className="font-mono text-xs text-ink-500">{c.rule_ref}</span>
              </li>
            ))}
          </ul>
        </section>

        <section aria-labelledby="nc-now" className="panel p-5">
          <h3 id="nc-now" className="ledger-rule font-display text-xl font-semibold">{t("eligibility.screen.what_now")}</h3>
          <p className="mt-3 text-ink-900">{j.alternative_remedy ?? t("eligibility.screen.alt_default")}</p>
          <h4 className="mt-5 text-sm font-semibold text-ink-800">{t("eligibility.screen.keep_evidence")}</h4>
          <ul className="mt-2 flex flex-col gap-1.5">
            {have.map((k) => (
              <li key={k}><StatusIcon size="sm" tone="ok" label={`${t(`evidence.${k}`)}: ${t("pack.have")}`} /></li>
            ))}
            {missing.map((k) => (
              <li key={k}><StatusIcon size="sm" tone="warn" label={`${t(`evidence.${k}`)}: ${t("pack.missing")}`} /></li>
            ))}
          </ul>
        </section>
      </div>
    </section>
  );
}
