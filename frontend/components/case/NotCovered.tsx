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
    <section aria-labelledby="nc-title" className="flex flex-col gap-4">
      <div className="panel flex flex-col gap-4 p-6 sm:p-8">
        <StatusIcon tone={eligibilityTone(j.status)} label={t(`eligibility.${j.status}`)} />
        <h2 id="nc-title" className="max-w-2xl text-2xl font-semibold leading-tight tracking-[-0.02em] text-ink-950 sm:text-[1.75rem]">
          {t("eligibility.screen.title")}
        </h2>
        <p className="max-w-2xl text-[0.9375rem] leading-relaxed text-ink-700">{t(`eligibility.reason.${j.status}`)}</p>
        <p className="text-xs text-ink-500">{t("eligibility.screen.based_on")}</p>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <section aria-labelledby="nc-checks" className="panel p-6">
          <h3 id="nc-checks" className="section-title">{t("eligibility.screen.checks")}</h3>
          <ul className="mt-4 flex flex-col divide-y divide-rule">
            {j.checks.map((c) => (
              <li key={c.id} className="flex flex-col gap-1.5 py-3 first:pt-0 last:pb-0">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="text-sm font-medium text-ink-950">{tCode("check", c.id, c.id)}</span>
                  <StatusIcon
                    size="sm"
                    tone={c.passed === true ? "ok" : c.passed === false ? "block" : "info"}
                    icon={c.passed === null ? "open" : undefined}
                    label={t(c.passed === true ? "eligibility.check.passed" : c.passed === false ? "eligibility.check.failed" : "eligibility.check.open")}
                  />
                </div>
                <span className="text-sm text-ink-600">{c.detail}</span>
                <span className="num text-xs text-ink-500">{c.rule_ref}</span>
              </li>
            ))}
          </ul>
        </section>

        <section aria-labelledby="nc-now" className="panel p-6">
          <h3 id="nc-now" className="section-title">{t("eligibility.screen.what_now")}</h3>
          <p className="mt-3 text-sm leading-relaxed text-ink-800">{j.alternative_remedy ?? t("eligibility.screen.alt_default")}</p>
          <h4 className="eyebrow mt-6">{t("eligibility.screen.keep_evidence")}</h4>
          <ul className="mt-3 flex flex-col gap-2">
            {have.map((k) => (
              <li key={k} className="flex items-center justify-between gap-3 text-sm">
                <span className="text-ink-900">{t(`evidence.${k}`)}</span>
                <StatusIcon size="sm" tone="ok" label={t("pack.have")} />
              </li>
            ))}
            {missing.map((k) => (
              <li key={k} className="flex items-center justify-between gap-3 text-sm">
                <span className="text-ink-900">{t(`evidence.${k}`)}</span>
                <StatusIcon size="sm" tone="warn" label={t("pack.missing")} />
              </li>
            ))}
          </ul>
        </section>
      </div>
    </section>
  );
}
