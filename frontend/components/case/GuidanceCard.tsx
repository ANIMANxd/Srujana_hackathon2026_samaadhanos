"use client";

import Link from "next/link";
import { useState } from "react";
import { currentStage, isStageBlocked, showDeemedAcceptance, topDefense } from "@/lib/derive";
import { count, date, money, moneyParts } from "@/lib/format";
import { useT } from "@/lib/i18n";
import { useHref } from "@/lib/params";
import type { PaidSummary } from "@/lib/payments";
import type { CaseResponse, StatuteConfig } from "@/lib/types";
import { Icon } from "../common/Icon";
import { StatusIcon } from "../common/StatusIcon";
import { PlaceholderBadge } from "../shell/PlaceholderBadge";
import { DEFENSE_TONE, DefensesDrawer } from "./DefensesDrawer";
import { LiveInterestTicker } from "./LiveInterestTicker";
import { SectionChip } from "./SectionChip";

type T = ReturnType<typeof useT>["t"];

/** "Paid ✓ on 12 Mar 2026 — 31 days after acceptance (legal due: 45 days)"; the day counts only when the engine's dates allow. */
function paidLine(p: PaidSummary, t: T): string {
  if (p.daysAfterAcceptance === null) return t("pay.paid_no_days", { date: date(p.paidOn) });
  if (p.legalDueDays === null) return t("pay.paid_no_legal", { date: date(p.paidOn), n: count(p.daysAfterAcceptance) });
  return t("pay.paid", { date: date(p.paidOn), n: count(p.daysAfterAcceptance), m: count(p.legalDueDays) });
}

/**
 * The hero (spec C1 / F10): one monumental figure, the rules behind it as
 * tags, and ONE next action for the current stage. Every figure is the engine's.
 */
export function GuidanceCard({
  caseId,
  response,
  config,
  placeholder,
  paid = null,
}: {
  caseId: string;
  response: CaseResponse;
  config: StatuteConfig | null;
  placeholder: boolean;
  /** Set when the engine shows nothing left to pay: replaces the next step. */
  paid?: PaidSummary | null;
}) {
  const { t } = useT();
  const href = useHref();
  const [defensesOpen, setDefensesOpen] = useState(false);
  const tl = response.timeline;
  const fin = response.financials;
  const stage = currentStage(response);
  const blocked = isStageBlocked(response, stage);
  const defense = topDefense(response.defenses);
  const days = tl?.days_overdue ?? null;
  const overdue = days !== null && days > 0;
  const total = moneyParts(fin?.total_claim);
  const status = tl?.objection_status;

  const actionHref = stage === 4 ? href(`/case/${caseId}/pack`) : href(`/case/${caseId}`, { send: stage });

  return (
    <section aria-labelledby="hero-figure" className="panel grid overflow-hidden lg:grid-cols-[1.45fr_1fr]">
      {/* Left: the claim */}
      <div className="flex flex-col gap-6 p-6 sm:p-8">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p id="hero-figure" className="eyebrow">{t("hero.claim")}</p>
          {fin &&
            (overdue ? (
              <StatusIcon size="sm" tone="warn" icon="clock" label={t("hero.overdue", { n: count(days) })} />
            ) : (
              <StatusIcon size="sm" tone="ok" label={t("hero.not_due")} />
            ))}
        </div>

        {fin ? (
          <>
            <p className="figure flex flex-wrap items-baseline text-[2.5rem] text-ink-950 sm:text-[2.75rem]">
              <span>{total.whole}</span>
              <span className="text-[0.5em] font-medium text-ink-500">{total.paise}</span>
              {placeholder && <PlaceholderBadge />}
            </p>

            <dl className="grid grid-cols-2 gap-6 border-t border-rule pt-5 sm:max-w-md">
              <div className="flex flex-col gap-1">
                <dt className="text-xs text-ink-500">{t("hero.principal")}</dt>
                <dd className="num text-[0.9375rem] text-ink-950">{money(fin.principal_outstanding)}</dd>
              </div>
              <div className="flex flex-col gap-1">
                <dt className="flex items-center gap-1.5 text-xs text-ink-500">
                  {overdue && <span className="live-dot" aria-hidden="true" />}
                  {t("hero.interest")}
                </dt>
                <dd className="text-[0.9375rem] text-ink-950">
                  <LiveInterestTicker interest={fin.interest_outstanding} dailyAccrual={fin.daily_accrual} />
                </dd>
              </div>
            </dl>
            {overdue && <p className="-mt-3 text-xs text-ink-500">{t("hero.accruing", { daily: money(fin.daily_accrual) })}</p>}
          </>
        ) : (
          <div className="flex flex-col gap-2">
            <p className="text-2xl font-semibold tracking-[-0.02em] text-ink-950">{t("hero.no_money")}</p>
            <p className="max-w-md text-sm text-ink-600">{t("hero.no_money_body")}</p>
          </div>
        )}

        <div className="mt-auto flex flex-wrap gap-2">
          {tl?.appointed_day && <SectionChip id="s16" config={config} />}
          {tl?.applied_days !== null && tl?.applied_days !== undefined && (
            <SectionChip id="s15" config={config} label={t("chip.s15.days", { n: tl.applied_days })} />
          )}
          {status && status !== "NO_DELIVERY_PROOF" && (
            <SectionChip
              id="s2b"
              config={config}
              label={t(showDeemedAcceptance(response) ? "chip.s2b.DEEMED_ACCEPTANCE" : `chip.s2b.${status}`)}
            />
          )}
          {tl?.clamped && (
            <span className="tag border-warn/30 bg-warn-wash text-warn">
              {t("timeline.clamped", { agreed: tl.agreed_days ?? "—", applied: tl.applied_days ?? "—" })}
            </span>
          )}
        </div>
      </div>

      {/* Right: the one next step */}
      <div className="flex flex-col gap-5 border-t border-rule bg-paper/60 p-6 sm:p-8 lg:border-l lg:border-t-0">
        <div className="flex items-center justify-between gap-3">
          <p className="eyebrow">{t("hero.next")}</p>
          <span className="num text-xs text-ink-500">{t("stage.of", { n: stage })}</span>
        </div>

        {paid ? (
          <div className="flex flex-col gap-1.5">
            <StatusIcon tone="ok" icon="ok" label={paidLine(paid, t)} wrap />
            <p className="text-sm text-ink-600">{t("pay.paid_note")}</p>
          </div>
        ) : status === "NO_DELIVERY_PROOF" ? (
          <p className="text-lg font-semibold leading-snug tracking-[-0.01em] text-ink-950">{t("hero.no_money_action")}</p>
        ) : (
          <div className="flex flex-col gap-1.5">
            <p className="text-lg font-semibold leading-snug tracking-[-0.01em] text-ink-950">{t(`stage.${stage}.title`)}</p>
            <p className="text-sm text-ink-600">{t(`stage.${stage}.purpose`)}</p>
          </div>
        )}

        {!paid &&
          status !== "NO_DELIVERY_PROOF" &&
          (blocked ? (
            <StatusIcon tone="block" icon="lock" label={t("ladder.blocked")} />
          ) : (
            <Link href={actionHref} scroll={false} className="btn btn-primary self-start">
              {t(`stage.${stage}.button`)}
              <Icon name="arrow-right" className="h-4 w-4" />
            </Link>
          ))}

        <div className="mt-auto flex flex-col gap-2.5 border-t border-rule pt-5">
          <p className="eyebrow">{t("defense.label")}</p>
          {defense ? (
            <>
              <p className="line-clamp-2 text-sm leading-relaxed text-ink-800">“{defense.buyer_says}”</p>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <StatusIcon size="sm" tone={DEFENSE_TONE[defense.status]} label={t(`defense.${defense.status}`)} />
                <button type="button" className="link text-sm" onClick={() => setDefensesOpen(true)}>
                  {t("defense.see_all", { n: response.defenses.length })}
                </button>
              </div>
            </>
          ) : (
            <p className="text-sm text-ink-600">{t("defense.none")}</p>
          )}
        </div>
      </div>

      <DefensesDrawer defenses={response.defenses} open={defensesOpen} onClose={() => setDefensesOpen(false)} />
    </section>
  );
}
