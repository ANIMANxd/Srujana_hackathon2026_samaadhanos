"use client";

import Link from "next/link";
import type { StageLock } from "@/lib/derive";
import { useT } from "@/lib/i18n";
import { useHref } from "@/lib/params";
import type { CaseResponse, Stage } from "@/lib/types";
import { Icon } from "../common/Icon";

/**
 * Why a step is locked, in the engine's own words wherever it gave any
 * (failed gate checks, its alternative remedy, its readiness reasons). The
 * copy around them is fixed text keyed by the lock code.
 */
export function LockedStage({ caseId, stage, lock, response }: { caseId: string; stage: Stage; lock: StageLock; response: CaseResponse }) {
  const { t } = useT();
  const href = useHref();
  const j = response.jurisdiction;
  const failed = j.checks.filter((c) => c.passed === false);
  const noProof = response.timeline?.objection_status === "NO_DELIVERY_PROOF";
  const cure = lock.code === "BLOCKED_STAGE" && stage === 4 && noProof;

  return (
    <section aria-labelledby="locked-title" className="panel flex flex-col gap-5 p-6 sm:p-8">
      <div className="flex items-start gap-3">
        <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg border border-rule bg-paper text-ink-500">
          <Icon name="lock" className="h-4 w-4" />
        </span>
        <div className="flex flex-col gap-1">
          <p className="eyebrow">{t("stage.of", { n: stage })} · {t(`stage.${stage}.title`)}</p>
          <h2 id="locked-title" className="text-xl font-semibold tracking-[-0.015em] text-ink-950">{t(`esc.lock.${lock.code}.title`)}</h2>
        </div>
      </div>

      <p className="max-w-2xl text-sm leading-relaxed text-ink-700">{t(`esc.lock.${lock.code}.body`)}</p>

      {lock.code === "GATE" && (
        <>
          {failed.length > 0 && (
            <div className="flex flex-col gap-2">
              <p className="eyebrow">{t("esc.lock.GATE.checks")}</p>
              <ul className="flex flex-col divide-y divide-rule rounded-lg border border-rule">
                {failed.map((c) => (
                  <li key={c.id} className="px-4 py-3 text-sm text-ink-800">{c.detail}</li>
                ))}
              </ul>
            </div>
          )}
          {j.alternative_remedy && (
            <div className="flex flex-col gap-2">
              <p className="eyebrow">{t("esc.lock.GATE.remedy")}</p>
              <p className="max-w-2xl rounded-lg bg-paper px-4 py-3 text-sm leading-relaxed text-ink-800">{j.alternative_remedy}</p>
            </div>
          )}
          <Link href={href(`/eligibility/${caseId}`)} className="btn btn-secondary self-start">
            {t("esc.lock.GATE.see_why")}
            <Icon name="arrow-right" className="h-4 w-4" />
          </Link>
        </>
      )}

      {lock.code === "BLOCKED_STAGE" && (
        <ul className="flex flex-col gap-2 rounded-lg border border-rule px-4 py-3 text-sm text-ink-800">
          {lock.reasons.length > 0 ? lock.reasons.map((r) => <li key={r}>{r}</li>) : <li>{t("esc.lock.BLOCKED_STAGE.generic")}</li>}
        </ul>
      )}

      {cure && (
        <div className="flex flex-col gap-3 rounded-lg border border-saffron-500/40 bg-saffron-100/50 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm text-ink-900">{t("esc.lock.cure")}</p>
          <Link href={href(`/case/${caseId}`, { tab: "escalation", step: 1 })} scroll={false} className="btn btn-primary shrink-0">
            {t("esc.lock.cure_button")}
            <Icon name="arrow-right" className="h-4 w-4" />
          </Link>
        </div>
      )}

      {lock.code === "NO_FIGURES" && (
        <Link href={href(`/case/${caseId}`, { tab: "evidence" })} scroll={false} className="btn btn-secondary self-start">
          {t("esc.lock.fix_evidence")}
          <Icon name="arrow-right" className="h-4 w-4" />
        </Link>
      )}
    </section>
  );
}
