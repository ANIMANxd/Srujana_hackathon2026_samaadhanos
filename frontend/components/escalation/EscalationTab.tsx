"use client";

import Link from "next/link";
import { currentStage, recommendedWhy, stageLock } from "@/lib/derive";
import { date } from "@/lib/format";
import { useT } from "@/lib/i18n";
import { useHref, useUrlState } from "@/lib/params";
import type { SendLogEntry } from "@/lib/caseStore";
import { STAGES, type CaseRequest, type CaseResponse, type Stage } from "@/lib/types";
import { Icon } from "../common/Icon";
import { SendPanel } from "../send/SendPanel";
import { LockedStage } from "./LockedStage";

type StepState = "recommended" | "available" | "locked";

/**
 * Four-step escalation: acceptance lock and balance confirmation, finance-team
 * advisory, split settlement, evidence pack. The stepper shows each step's
 * state (icon + word); the selected step (?step=) shows its live draft or why
 * it is locked. Availability comes from the engine (blocked_stages, the gate,
 * which blocks it returned); the recommended step carries the engine's reason.
 */
export function EscalationTab({
  caseId,
  request,
  response,
  offlineId,
  log,
}: {
  caseId: string;
  request: CaseRequest;
  response: CaseResponse;
  offlineId: string | null;
  log: SendLogEntry[];
}) {
  const { t } = useT();
  const href = useHref();
  const { step } = useUrlState();

  const locks = Object.fromEntries(STAGES.map((s) => [s, stageLock(response, s)])) as Record<Stage, ReturnType<typeof stageLock>>;
  const why = recommendedWhy(response);
  const recommended = why && !locks[currentStage(response)] ? currentStage(response) : null;
  const state = (s: Stage): StepState => (locks[s] ? "locked" : s === recommended ? "recommended" : "available");
  const selected: Stage = step ?? recommended ?? STAGES.find((s) => !locks[s]) ?? 1;
  const lock = locks[selected];

  return (
    <div className="grid items-start gap-4 lg:grid-cols-[19rem_1fr]">
      <section aria-labelledby="esc-title" className="panel flex flex-col gap-4 p-5 lg:sticky lg:top-20">
        <div className="flex flex-col gap-1">
          <h2 id="esc-title" className="section-title">{t("esc.title")}</h2>
          <p className="text-xs leading-relaxed text-ink-500">{t("esc.intro")}</p>
        </div>
        <ol className="flex flex-col gap-2">
          {STAGES.map((s) => {
            const st = state(s);
            const isSel = s === selected;
            const prepared = log.filter((e) => e.stage === s);
            return (
              <li key={s}>
                <Link
                  href={href(`/case/${caseId}`, { tab: "escalation", step: s })}
                  scroll={false}
                  aria-current={isSel ? "step" : undefined}
                  className={`relative flex flex-col gap-1.5 rounded-lg border px-4 py-3 transition-colors ${
                    isSel ? "border-ink-950/40 bg-paper-raised shadow-[0_1px_2px_rgb(13_13_12/0.06)]" : "border-rule hover:bg-paper"
                  } ${st === "locked" ? "bg-paper" : ""}`}
                >
                  {st === "recommended" && <span aria-hidden="true" className="absolute inset-x-3 top-0 h-0.5 rounded-full bg-saffron-500" />}
                  <span className="flex items-center justify-between gap-2">
                    <span className="flex items-center gap-2.5">
                      <span
                        aria-hidden="true"
                        className={`num grid h-6 w-6 place-items-center rounded-full text-xs font-medium ${
                          st === "recommended" ? "bg-ink-950 text-paper-raised" : st === "locked" ? "border border-dashed border-ink-300 text-ink-300" : "border border-ink-300 text-ink-700"
                        }`}
                      >
                        {s}
                      </span>
                      <span className={`text-sm font-medium ${st === "locked" ? "text-ink-500" : "text-ink-950"}`}>{t(`stage.${s}.title`)}</span>
                    </span>
                  </span>
                  <span
                    className={`inline-flex items-center gap-1 text-xs font-medium ${
                      st === "recommended" ? "text-saffron-ink" : st === "locked" ? "text-ink-500" : "text-ink-600"
                    }`}
                  >
                    <Icon name={st === "locked" ? "lock" : st === "recommended" ? "arrow-right" : "ok"} className="h-3.5 w-3.5" />
                    {t(st === "locked" ? "esc.locked" : st === "recommended" ? "esc.recommended" : "esc.available")}
                  </span>
                  {st === "recommended" && why && <span className="text-xs leading-relaxed text-ink-600">{t(`esc.why.${why}`)}</span>}
                  {prepared.length > 0 && <span className="text-xs text-ink-500">{t("ladder.prepared", { date: date(prepared[prepared.length - 1].at) })}</span>}
                </Link>
              </li>
            );
          })}
        </ol>
      </section>

      <div className="flex min-w-0 flex-col gap-4">
        {lock ? (
          <LockedStage caseId={caseId} stage={selected} lock={lock} response={response} />
        ) : (
          <section aria-labelledby="esc-step" className="panel flex flex-col gap-5 p-6 sm:p-8">
            <div className="flex flex-col gap-1">
              <p className="eyebrow">{t("stage.of", { n: selected })}</p>
              <h2 id="esc-step" className="text-xl font-semibold tracking-[-0.015em] text-ink-950">{t(`stage.${selected}.title`)}</h2>
              {selected === recommended && why && <p className="text-sm text-saffron-ink">{t(`esc.why.${why}`)}</p>}
            </div>
            <SendPanel key={selected} caseId={caseId} stage={selected} request={request} response={response} offlineId={offlineId} />
          </section>
        )}
      </div>
    </div>
  );
}
