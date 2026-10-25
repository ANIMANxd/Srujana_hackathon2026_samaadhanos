"use client";

import Link from "next/link";
import { currentStage, isStageBlocked, type Tone } from "@/lib/derive";
import { useT } from "@/lib/i18n";
import { useHref } from "@/lib/params";
import { STAGES, type CaseResponse, type ReadinessBand } from "@/lib/types";
import { Icon } from "../common/Icon";
import { StatusIcon } from "../common/StatusIcon";
import { Meaning } from "./Meaning";

const BAND_TONE: Record<ReadinessBand, Tone> = { COURT_READY: "ok", EVIDENCE_COMPLETE: "ok", ACTION_NEEDED: "warn", BLOCKED: "block" };
const BAR: Record<Tone, string> = { ok: "bg-ok", warn: "bg-warn", block: "bg-block", info: "bg-info" };

/** Reason codes that explain why the engine locked Stage 4 (6.6). */
const STAGE4_REASONS = ["MISSING_DELIVERY_PROOF", "GATE_BLOCKED"];

/**
 * evidence_readiness as a gauge: the engine's score and band, every reason
 * with its delta (they add up to the score), and the four stages with locked
 * ones greyed and explained. No number here is computed by the browser.
 */
export function ReadinessGauge({ caseId, response }: { caseId: string; response: CaseResponse }) {
  const { t, tCode } = useT();
  const href = useHref();
  const r = response.evidence_readiness;
  const tone = BAND_TONE[r.band];
  const recommended = currentStage(response);
  const stage4Why = r.reasons.find((x) => STAGE4_REASONS.includes(x.code));
  const suggestCure = isStageBlocked(response, 4) && recommended === 1 && response.timeline?.objection_status === "NO_DELIVERY_PROOF";

  return (
    <section aria-labelledby="gauge-title" className="panel flex flex-col gap-5 p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id="gauge-title" className="section-title">{t("gauge.title")}</h2>
        <StatusIcon size="sm" tone={tone} label={t(`readiness.${r.band}`)} />
      </div>

      <div className="flex flex-col gap-2">
        <p className="figure text-[2.5rem] text-ink-950">
          {r.score}
          <span className="ml-1 text-base font-normal text-ink-500">/ 100</span>
        </p>
        <div
          role="meter"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={r.score}
          aria-label={t("gauge.title")}
          className="h-2 overflow-hidden rounded-full bg-paper-sunk"
        >
          <div className={`h-full rounded-full ${BAR[tone]}`} style={{ width: `${r.score}%` }} />
        </div>
      </div>

      <div className="flex flex-col gap-2">
        <p className="eyebrow">{t("gauge.reasons")}</p>
        {r.reasons.length === 0 ? (
          <p className="text-sm text-ink-600">{t("gauge.no_reasons")}</p>
        ) : (
          <ul className="flex flex-col gap-2 text-sm">
            {r.reasons.map((x, i) => (
              <li key={`${x.code}-${i}`} className="grid grid-cols-[2.75rem_1fr] gap-2">
                <span className={`num text-right ${x.delta < 0 ? "text-warn" : "text-ink-500"}`}>{x.delta > 0 ? `+${x.delta}` : x.delta}</span>
                <span className="text-ink-800">{tCode("reason", x.code, x.text)}</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="flex flex-col gap-2">
        <p className="eyebrow">{t("gauge.stages")}</p>
        <ol className="flex flex-col divide-y divide-rule rounded-lg border border-rule">
          {STAGES.map((s) => {
            const locked = isStageBlocked(response, s);
            return (
              <li key={s} className={`flex flex-col gap-1 px-4 py-3 ${locked ? "bg-paper text-ink-500" : ""}`}>
                <div className="flex items-center justify-between gap-3">
                  <span className={`text-sm ${locked ? "text-ink-500" : "font-medium text-ink-950"}`}>
                    <span className="num mr-2 text-xs text-ink-500">{s}</span>
                    {t(`stage.${s}.title`)}
                  </span>
                  <span className={`inline-flex items-center gap-1 text-xs font-medium ${locked ? "text-ink-500" : "text-ok"}`}>
                    <Icon name={locked ? "lock" : "ok"} className="h-3.5 w-3.5" />
                    {t(locked ? "gauge.stage_locked" : "gauge.stage_open")}
                  </span>
                </div>
                {locked && (
                  <p className="text-xs text-ink-600">
                    {s === 4 && stage4Why
                      ? t("gauge.locked_why", { why: tCode("reason", stage4Why.code, stage4Why.text) })
                      : t("gauge.locked_generic")}
                  </p>
                )}
              </li>
            );
          })}
        </ol>
      </div>

      {suggestCure && (
        <div className="flex flex-col gap-3 rounded-lg border border-saffron-500/40 bg-saffron-100/50 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm text-ink-900">{t("gauge.cure")}</p>
          <Link href={href(`/case/${caseId}`, { send: 1, tab: "evidence" })} scroll={false} className="btn btn-primary shrink-0">
            {t("gauge.cure_button")}
            <Icon name="arrow-right" className="h-4 w-4" />
          </Link>
        </div>
      )}

      <Meaning block="readiness" code={r.band} />
    </section>
  );
}
