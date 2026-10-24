"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { currentStage, isStageBlocked, latestSegment, showDeemedAcceptance, topDefense } from "@/lib/derive";
import { date, money, pct } from "@/lib/format";
import { useT } from "@/lib/i18n";
import { useHref } from "@/lib/params";
import type { CaseRequest, CaseResponse, StatuteConfig } from "@/lib/types";
import { Icon } from "../common/Icon";
import { PlaceholderBadge } from "../shell/PlaceholderBadge";
import { SectionChip } from "./SectionChip";
import { LiveInterestTicker } from "./LiveInterestTicker";

/**
 * Need-based guidance for the CURRENT stage only (spec C1 / F10):
 * one headline, one law line, one likely objection, one action, one button.
 */
export function GuidanceCard({
  caseId,
  request,
  response,
  config,
  placeholder,
}: {
  caseId: string;
  request: CaseRequest;
  response: CaseResponse;
  config: StatuteConfig | null;
  placeholder: boolean;
}) {
  const { t, tCode } = useT();
  const href = useHref();
  const tl = response.timeline;
  const fin = response.financials;
  const stage = currentStage(response);
  const blocked = isStageBlocked(response, stage);
  const defense = topDefense(response.defenses);
  const segment = latestSegment(fin);
  const buyer = request.buyer.name;

  const overdue = tl?.days_overdue !== null && tl?.days_overdue !== undefined && tl.days_overdue > 0;
  const principal = money(fin?.principal_outstanding ?? request.transaction.principal, { paise: "auto" });

  let lawLine: ReactNode = null;
  if (tl?.objection_status === "NO_DELIVERY_PROOF") {
    lawLine = <span>{t("guidance.no_delivery")}</span>;
  } else if (tl?.objection_status === "PENDING_RESOLUTION") {
    lawLine = (
      <span>
        {t("guidance.pending")}
        <SectionChip id="s2b" config={config} />
      </span>
    );
  } else if (tl?.appointed_day) {
    lawLine = (
      <span>
        {segment
          ? t("guidance.law.s16", { rate: pct(segment.statutory_rate_pct), date: date(tl.appointed_day) })
          : t("guidance.law.s16_no_rate", { date: date(tl.appointed_day) })}
        <SectionChip id="s16" config={config} />
      </span>
    );
  } else {
    lawLine = <span>{t("guidance.law.not_started")}</span>;
  }

  const actionKey = tl?.objection_status === "NO_DELIVERY_PROOF" ? null : stage;
  const actionHref = stage === 4 ? href(`/case/${caseId}/pack`) : href(`/case/${caseId}/send/${stage}`);

  return (
    <section aria-labelledby="guidance-title" className="panel relative overflow-hidden border-ink-800 bg-paper-raised">
      <div className="absolute inset-y-0 left-0 w-1.5 bg-saffron-500" aria-hidden="true" />
      <div className="flex flex-col gap-5 py-6 pl-7 pr-5 sm:pl-9 sm:pr-8">
        <p className="text-xs font-semibold uppercase tracking-[0.12em] text-ink-500">{t("guidance.label")}</p>

        <h2 id="guidance-title" className="font-display text-2xl font-semibold leading-[1.15] tracking-tight text-ink-950 sm:text-3xl">
          {overdue
            ? t("guidance.headline_overdue", {
                n: tl?.days_overdue ?? 0,
                buyer,
                principal,
                interest: money(fin?.interest_outstanding ?? "0", { paise: "auto" }),
              })
            : t("guidance.headline_not_due", { buyer, principal })}
          {placeholder && <PlaceholderBadge />}
        </h2>

        {overdue && fin && (
          <p className="-mt-2 flex flex-wrap items-baseline gap-x-2 text-sm text-ink-600">
            <span>{t("money.ticker_label")}:</span>
            <LiveInterestTicker
              interest={fin.interest_outstanding}
              dailyAccrual={fin.daily_accrual}
              className="text-base font-medium text-saffron-ink"
            />
            {placeholder && <PlaceholderBadge />}
          </p>
        )}

        <dl className="grid gap-3 border-t border-rule pt-4 text-base sm:grid-cols-[11rem_1fr] sm:gap-x-6">
          <dt className="font-semibold text-ink-800">{t("guidance.law_label")}</dt>
          <dd className="text-ink-900">
            {lawLine}
            {tl && showDeemedAcceptance(response) && tl.delivery_date && tl.objection_window_end && (
              <span className="mt-1.5 block text-ink-700">
                {t("guidance.deemed", { delivery: date(tl.delivery_date), window_end: date(tl.objection_window_end) })}
                <SectionChip id="s2b" config={config} />
              </span>
            )}
          </dd>

          <dt className="font-semibold text-ink-800">{t("guidance.buyer_may_say")}</dt>
          <dd className="text-ink-900">
            {defense ? (
              <>
                <span className="italic">“{defense.buyer_says}”</span>{" "}
                <span className="text-ink-700">
                  {defense.status === "OPEN_QUESTION"
                    ? t("guidance.counter_open")
                    : [
                        defense.evidence_have.length > 0 &&
                          `${t("guidance.buyer_counter")} ${t("guidance.counter_have", {
                            items: defense.evidence_have.map((k) => tCode("evidence", k, k)).join(", "),
                          })}`,
                        defense.evidence_missing.length > 0 &&
                          t("guidance.counter_missing", {
                            items: defense.evidence_missing.map((k) => tCode("evidence", k, k)).join(", "),
                          }),
                      ]
                        .filter(Boolean)
                        .join(" ")}
                </span>
              </>
            ) : (
              <span className="text-ink-700">{t("guidance.no_defense")}</span>
            )}
          </dd>

          <dt className="font-semibold text-ink-800">{t("guidance.do_now")}</dt>
          <dd className="flex flex-col items-start gap-3 sm:flex-row sm:items-center sm:justify-between">
            <span className="text-lg font-medium text-ink-950">
              {actionKey === null ? t("guidance.no_delivery_action") : t(`stage.${actionKey}.action`)}
            </span>
            {actionKey !== null && !blocked && (
              <Link href={actionHref} className="btn btn-primary">
                {t(`stage.${actionKey}.button`)}
                <Icon name="arrow-right" className="h-4 w-4" />
              </Link>
            )}
          </dd>
        </dl>
      </div>
    </section>
  );
}
