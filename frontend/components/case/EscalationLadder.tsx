"use client";

import Link from "next/link";
import { currentStage, isStageBlocked } from "@/lib/derive";
import { date } from "@/lib/format";
import { useT } from "@/lib/i18n";
import { useHref } from "@/lib/params";
import { STAGES, type CaseResponse, type Stage } from "@/lib/types";
import type { SendLogEntry } from "@/lib/caseStore";
import { Icon } from "../common/Icon";

/**
 * Four-step stepper. State is always icon + word (Recommended / Available /
 * Locked), never colour alone. Steps 1-3 open the send drawer; 4 the pack.
 */
export function EscalationLadder({
  caseId,
  response,
  log,
}: {
  caseId: string;
  response: CaseResponse;
  log: SendLogEntry[];
}) {
  const { t } = useT();
  const href = useHref();
  const current = currentStage(response);

  const linkFor = (s: Stage) => (s === 4 ? href(`/case/${caseId}/pack`) : href(`/case/${caseId}`, { send: s }));

  return (
    <section aria-labelledby="ladder-title" className="panel p-6">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="ladder-title" className="section-title">{t("ladder.title")}</h2>
        <p className="text-xs text-ink-500">{t("ladder.intro")}</p>
      </div>

      <ol className="mt-5 grid gap-px overflow-hidden rounded-lg border border-rule bg-rule md:grid-cols-4">
        {STAGES.map((s) => {
          const blocked = isStageBlocked(response, s);
          const isCurrent = s === current && !blocked;
          const prepared = log.filter((e) => e.stage === s);
          const state = blocked ? "blocked" : isCurrent ? "recommended" : "available";
          const body = (
            <>
              <div className="flex items-center justify-between gap-2">
                <span
                  aria-hidden="true"
                  className={`num grid h-6 w-6 place-items-center rounded-full text-xs font-medium ${
                    isCurrent ? "bg-ink-950 text-paper-raised" : blocked ? "border border-dashed border-ink-300 text-ink-500" : "border border-ink-300 text-ink-700"
                  }`}
                >
                  {s}
                </span>
                <span
                  className={`inline-flex items-center gap-1 text-xs font-medium ${
                    state === "recommended" ? "text-saffron-ink" : state === "blocked" ? "text-ink-500" : "text-ink-600"
                  }`}
                >
                  <Icon name={state === "blocked" ? "lock" : state === "recommended" ? "arrow-right" : "ok"} className="h-3.5 w-3.5" />
                  {t(state === "blocked" ? "ladder.blocked" : state === "recommended" ? "ladder.recommended" : "ladder.available")}
                </span>
              </div>
              <span className="sr-only">{t("stage.chip", { n: s })}</span>
              <span className={`mt-3 text-sm font-medium ${blocked ? "text-ink-500" : "text-ink-950"}`}>{t(`stage.${s}.title`)}</span>
              {prepared.length > 0 && (
                <span className="mt-1 text-xs text-ink-500">{t("ladder.prepared", { date: date(prepared[prepared.length - 1].at) })}</span>
              )}
            </>
          );
          return (
            <li key={s} aria-current={isCurrent ? "step" : undefined} className="bg-paper-raised">
              {blocked ? (
                <div className="flex h-full flex-col p-4">{body}</div>
              ) : (
                <Link
                  href={linkFor(s)}
                  scroll={false}
                  className={`relative flex h-full flex-col p-4 transition-colors hover:bg-paper ${isCurrent ? "bg-saffron-100/40" : ""}`}
                >
                  {isCurrent && <span aria-hidden="true" className="absolute inset-x-0 top-0 h-0.5 bg-saffron-500" />}
                  {body}
                </Link>
              )}
            </li>
          );
        })}
      </ol>
    </section>
  );
}
