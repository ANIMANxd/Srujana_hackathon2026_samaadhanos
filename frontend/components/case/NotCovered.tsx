"use client";

import Link from "next/link";
import { evidenceKinds, isNotCovered } from "@/lib/derive";
import { useT } from "@/lib/i18n";
import { useHref } from "@/lib/params";
import type { CaseRequest, CaseResponse } from "@/lib/types";
import { Icon } from "../common/Icon";
import { StatusIcon } from "../common/StatusIcon";
import { EligibilityPill } from "./EligibilityPill";

/**
 * The eligibility explanation panel. Shown instead of the case screen when the
 * gate blocks, and at /eligibility/[id] for any status (the pill links here).
 */
export function NotCovered({ request, response }: { request: CaseRequest; response: CaseResponse }) {
  const { t, tCode } = useT();
  const href = useHref();
  const j = response.jurisdiction;
  const blocked = isNotCovered(response);
  const title = blocked
    ? t("eligibility.screen.title")
    : j.status === "ELIGIBLE"
      ? t("eligibility.screen.title_eligible")
      : t("eligibility.screen.title_unconfirmed");
  const have = evidenceKinds(request, true);
  const missing = evidenceKinds(request, false);

  return (
    <section aria-labelledby="nc-title" className="flex flex-col gap-4">
      <div className="panel flex flex-col gap-4 p-6 sm:p-8">
        <EligibilityPill status={j.status} />
        <h2 id="nc-title" className="max-w-2xl text-2xl font-semibold leading-tight tracking-[-0.02em] text-ink-950 sm:text-[1.75rem]">
          {title}
        </h2>
        <p className="max-w-2xl text-[0.9375rem] leading-relaxed text-ink-700">{t(`eligibility.reason.${j.status}`)}</p>
        <p className="text-xs text-ink-500">{t("eligibility.screen.based_on")}</p>
        {!blocked && (
          <Link href={href(`/case/${response.case_id}`)} className="btn btn-secondary self-start">
            <Icon name="arrow-left" className="h-4 w-4" />
            {t("eligibility.screen.back")}
          </Link>
        )}
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
