"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState, type ReactNode } from "react";
import { startFinancing, startRecovery } from "@/lib/api";
import { date as fmtDate, money } from "@/lib/format";
import { useT } from "@/lib/i18n";
import type { MessageKey } from "@/lib/i18n/en";
import { useHref } from "@/lib/params";
import type { Track } from "@/lib/types";
import { useOptions } from "@/lib/useOptions";
import type { TrackView } from "@/lib/useTrack";
import { IdempotentButton } from "../common/IdempotentButton";
import { Icon } from "../common/Icon";
import { Skeleton } from "../common/States";
import { StatusIcon } from "../common/StatusIcon";
import { Banner } from "../shell/Banners";
import { DemoBadge } from "./DemoBadge";
import { OptionColumn } from "./OptionColumn";
import { UnavailableReason } from "./UnavailableReason";

const DATE = /^\d{4}-\d{2}-\d{2}$/;
const ENDED = new Set(["BUYER_DECLINED", "NO_BIDS", "CANCELLED", "NOT_FINANCEABLE", "DISBURSEMENT_FAILED"]);
const RECOVERY_DONE = new Set(["CLOSED", "PAID", "SETTLED"]);

type Side = "available" | "in_progress" | "ended" | "paused" | "locked";

/**
 * What each column is, given the active track and the actions the server
 * allows. Display logic only: the server owns every transition rule.
 */
function sides(track: Track | null, actions: string[]): { early: Side; recover: Side } {
  if (!track) return { early: "available", recover: "available" };
  if (track.kind === "FINANCING") {
    if (ENDED.has(track.state)) return { early: "ended", recover: "available" };
    return { early: "in_progress", recover: actions.includes("switch_to_recovery") ? "paused" : "locked" };
  }
  if (RECOVERY_DONE.has(track.state)) return { early: "locked", recover: "ended" };
  return { early: actions.includes("switch_to_financing") ? "paused" : "locked", recover: "in_progress" };
}

function sideStatus(side: Side, t: (k: MessageKey) => string): ReactNode {
  if (side === "in_progress") return <StatusIcon size="sm" tone="info" icon="clock" label={t("options.in_progress")} />;
  if (side === "paused") return <StatusIcon size="sm" tone="warn" icon="clock" label={t("options.paused")} />;
  if (side === "locked") return <StatusIcon size="sm" tone="block" icon="lock" label={t("options.locked")} />;
  if (side === "ended") return <StatusIcon size="sm" tone="info" icon="block" label={t("options.ended")} />;
  return null;
}

/**
 * Two ways forward for one invoice (architecture_v4 section 10), side by side.
 * Never a "best" or "recommended" mark: the server's `recommendation` is always
 * null and this card has no place to show one. Every figure comes from
 * GET /cases/{id}/options.
 */
export function ChoiceCard({ caseId, tracking }: { caseId: string; tracking: TrackView }) {
  const { t } = useT();
  const href = useHref();
  const router = useRouter();
  const search = useSearchParams();
  const [picked, setPicked] = useState<string | null>(null);
  const offline = tracking.source === "offline";
  const track = tracking.track;
  const actions = tracking.caseDetail?.available_actions ?? [];
  const view = useOptions(caseId, Boolean(tracking.caseDetail), picked, track?.version ?? null, search.get("options"));

  if (view.error && !view.options) {
    return (
      <section className="panel p-5 sm:p-6" aria-labelledby="options-title">
        <h2 id="options-title" className="section-title">
          {t("options.title")}
        </h2>
        <p role="alert" className="mt-2 flex items-start gap-2 text-sm text-ink-700">
          <Icon name="warn" className="mt-0.5 h-4 w-4 shrink-0 text-warn" />
          {t("options.error")} {t("options.retry_hint")}
        </p>
      </section>
    );
  }
  if (!view.options) {
    return (
      <section className="panel p-5 sm:p-6" aria-busy="true" aria-labelledby="options-title">
        <h2 id="options-title" className="section-title">
          {t("options.title")}
        </h2>
        <span className="sr-only">{t("options.loading")}</span>
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <Skeleton className="h-48" />
          <Skeleton className="h-48" />
        </div>
      </section>
    );
  }

  const o = view.options;
  const early = o.get_paid_early;
  const rec = o.recover_with_law;
  const s = sides(track, actions);
  const expected = picked ?? rec.expected_payment_date ?? "";
  const earlyDimmed = s.early !== "in_progress" && !(s.early === "available" && early.available);
  const recDimmed = s.recover !== "in_progress" && !(s.recover === "available" && rec.available);

  let earlyBlocked: ReactNode = null;
  if (s.early === "locked") {
    earlyBlocked = <UnavailableReason reason={t("options.locked.early_in_recovery")} otherHref="#option-recover" otherLabel="options.go_recover" />;
  } else if (s.early === "paused") {
    earlyBlocked = <UnavailableReason reason={t("options.paused.early")} otherHref="#option-recover" otherLabel="options.go_recover" />;
  } else if (s.early === "ended" || (s.early === "available" && !early.available)) {
    earlyBlocked = (
      <UnavailableReason
        reason={early.unavailable_reasons?.[0] ?? (s.early === "ended" ? t("options.ended.reason") : null)}
        otherHref="#option-recover"
        otherLabel="options.switch_to_recovery"
      />
    );
  }

  let recBlocked: ReactNode = null;
  if (s.recover === "locked") {
    recBlocked = <UnavailableReason reason={t("options.locked.recovery_after_sign")} otherHref="#option-early" otherLabel="options.go_early" />;
  } else if (s.recover === "paused") {
    recBlocked = <UnavailableReason reason={t("options.paused.recovery")} otherHref="#option-early" otherLabel="options.go_early" />;
  } else if (s.recover === "available" && !rec.available) {
    recBlocked = <UnavailableReason reason={rec.notes?.[0] ?? null} otherHref="#option-early" otherLabel="options.switch_to_early" />;
  }

  const ind = early.indicative;
  let earlyAction: ReactNode = null;
  if (s.early === "in_progress") {
    earlyAction = (
      <Link href={href(`/case/${caseId}/early`)} className="btn btn-primary">
        {t("options.continue")}
        <Icon name="arrow-right" className="h-4 w-4" />
      </Link>
    );
  } else if (s.early === "available" && early.available) {
    earlyAction = (
      <IdempotentButton
        actionId={`financing.start:${caseId}`}
        run={async (opts) => {
          await startFinancing(caseId, opts);
          await tracking.refresh();
          router.push(href(`/case/${caseId}/early`));
        }}
        onConflict={tracking.refresh}
        offline={offline}
      >
        {t("options.early.start")}
      </IdempotentButton>
    );
  }

  let recoverAction: ReactNode = null;
  if (s.recover === "in_progress") {
    recoverAction = (
      <Link href={href(`/case/${caseId}`, { tab: "escalation" })} className="btn btn-primary">
        {t("options.continue")}
        <Icon name="arrow-right" className="h-4 w-4" />
      </Link>
    );
  } else if (s.recover === "available" && rec.available) {
    recoverAction = (
      <IdempotentButton
        actionId={`recovery.start:${caseId}`}
        run={async (opts) => {
          await startRecovery(caseId, null, opts);
          await tracking.refresh();
          router.push(href(`/case/${caseId}`, { tab: "escalation" }));
        }}
        version={track?.version}
        onConflict={tracking.refresh}
        offline={offline}
        className="btn btn-secondary"
      >
        {t("options.recover.start")}
      </IdempotentButton>
    );
  }

  return (
    <section className="panel overflow-hidden" aria-labelledby="options-title" aria-busy={view.loading}>
      <div className="flex flex-col gap-1 border-b border-rule px-5 py-4 sm:px-6">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 id="options-title" className="section-title">
            {t("options.title")}
          </h2>
          {view.loading && <span className="text-xs text-ink-500">{t("options.refreshing")}</span>}
        </div>
        <p className="text-sm text-ink-600">{t("options.intro")}</p>
      </div>
      {view.source === "offline" && (
        <div className="px-5 pt-4 sm:px-6">
          <Banner tone="warn" icon="lock" message="options.offline_sample" />
        </div>
      )}

      <div className={`grid divide-rule md:grid-cols-2 md:divide-x ${view.loading ? "opacity-80" : ""}`}>
        <OptionColumn
          id="option-early"
          title={t("options.early.title")}
          badge={<DemoBadge />}
          status={sideStatus(s.early, t)}
          dimmed={earlyDimmed}
          numberLabel={t("options.early.number_label")}
          number={
            ind ? t("options.early.range", { low: money(ind.net_receivable_range.low), high: money(ind.net_receivable_range.high) }) : "—"
          }
          what={t("options.early.what")}
          cost={
            ind
              ? t("options.early.cost", {
                  fee: ind.platform_fee_pct,
                  low: ind.rate_band_pct.low,
                  high: ind.rate_band_pct.high,
                  label: ind.rate_band_pct.label,
                  days: ind.tenor_days,
                })
              : ""
          }
          action={earlyAction}
          blocked={earlyBlocked}
          notes={ind ? [...(early.notes ?? []), `${t("options.early.settlement")}: ${ind.settlement}`] : (early.notes ?? [])}
          citations={early.citations ?? []}
        />
        <OptionColumn
          id="option-recover"
          title={t("options.recover.title")}
          status={sideStatus(s.recover, t)}
          dimmed={recDimmed}
          numberLabel={t("options.recover.number_label", { date: fmtDate(expected) })}
          number={money(rec.total_if_paid)}
          what={t("options.recover.what")}
          cost={t("options.recover.cost")}
          extra={
            <label className="flex flex-col gap-1 text-sm text-ink-700">
              <span className="font-medium">{t("options.recover.date_label")}</span>
              <input
                type="date"
                className="field-input max-w-[12rem] font-mono"
                value={expected}
                onChange={(e) => setPicked(DATE.test(e.target.value) ? e.target.value : null)}
                aria-describedby="option-date-hint"
              />
              <span id="option-date-hint" className="text-xs text-ink-500">
                {t("options.recover.date_hint")}
              </span>
            </label>
          }
          action={recoverAction}
          blocked={recBlocked}
          notes={[
            ...(rec.notes ?? []),
            `${t("options.recover.principal")}: ${money(rec.principal)}`,
            `${t("options.recover.interest")}: ${money(rec.interest_to_expected_date)}`,
            ...(rec.current_stage ? [t("options.recover.stage", { stage: rec.current_stage })] : []),
          ]}
          citations={rec.citations ?? []}
        />
      </div>
    </section>
  );
}
