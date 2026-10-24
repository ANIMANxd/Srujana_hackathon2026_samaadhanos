"use client";

import Link from "next/link";
import { currentStage, isStageBlocked } from "@/lib/derive";
import { date } from "@/lib/format";
import { useT } from "@/lib/i18n";
import { useHref } from "@/lib/params";
import { STAGES, type CaseResponse, type Stage } from "@/lib/types";
import type { SendLogEntry } from "@/lib/caseStore";
import { Icon } from "../common/Icon";
import { StatusIcon } from "../common/StatusIcon";

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

  const linkFor = (s: Stage) => (s === 4 ? href(`/case/${caseId}/pack`) : href(`/case/${caseId}/send/${s}`));

  return (
    <section aria-labelledby="ladder-title" className="panel p-5">
      <h2 id="ladder-title" className="ledger-rule font-display text-xl font-semibold text-ink-950">
        {t("ladder.title")}
      </h2>
      <p className="mt-2 text-sm text-ink-700">{t("ladder.intro")}</p>

      <ol className="mt-4 grid gap-3 md:grid-cols-4">
        {STAGES.map((s) => {
          const blocked = isStageBlocked(response, s);
          const isCurrent = s === current && !blocked;
          const prepared = log.filter((e) => e.stage === s);
          return (
            <li
              key={s}
              aria-current={isCurrent ? "step" : undefined}
              className={`flex flex-col gap-2 rounded-md border p-4 ${
                isCurrent ? "border-saffron-600 bg-saffron-100/50" : blocked ? "border-dashed border-rule-strong bg-paper" : "border-rule bg-paper-raised"
              }`}
            >
              <div className="flex items-center gap-2">
                <span
                  className={`num flex h-7 w-7 items-center justify-center rounded-full text-sm font-semibold ${
                    isCurrent ? "bg-ink-900 text-paper" : "border border-ink-300 text-ink-700"
                  }`}
                  aria-hidden="true"
                >
                  {s}
                </span>
                <span className="sr-only">{t("stage.chip", { n: s })}</span>
                <span className={`font-semibold ${blocked ? "text-ink-500" : "text-ink-950"}`}>{t(`stage.${s}.title`)}</span>
              </div>
              <p className="text-sm text-ink-700">{t(`stage.${s}.purpose`)}</p>
              <div className="mt-auto flex flex-wrap items-center gap-2 pt-1">
                {blocked ? (
                  <StatusIcon tone="block" size="sm" icon="lock" label={t("ladder.blocked")} />
                ) : isCurrent ? (
                  <StatusIcon tone="warn" size="sm" icon="arrow-right" label={t("ladder.recommended")} />
                ) : (
                  <StatusIcon tone="info" size="sm" icon="ok" label={t("ladder.available")} />
                )}
                {!blocked && (
                  <Link href={linkFor(s)} className="btn btn-quiet min-h-0 text-sm">
                    {t("common.open")}
                    <Icon name="chevron" className="h-3.5 w-3.5" />
                  </Link>
                )}
              </div>
              {prepared.length > 0 && (
                <p className="text-xs text-ink-600">
                  {t("send.prepared_log", { n: s, date: date(prepared[prepared.length - 1].at) })}
                </p>
              )}
            </li>
          );
        })}
      </ol>
    </section>
  );
}
