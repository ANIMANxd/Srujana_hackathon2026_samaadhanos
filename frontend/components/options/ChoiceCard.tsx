"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState, type ReactNode } from "react";
import { startRecovery } from "@/lib/api";
import { useEarlyActions } from "@/lib/earlyActions";
import { simClear } from "@/lib/sim";
import { date as fmtDate, money } from "@/lib/format";
import { useT } from "@/lib/i18n";
import type { MessageKey } from "@/lib/i18n/en";
import { useHref } from "@/lib/params";
import type { Stage, Track } from "@/lib/types";
import { useOptions } from "@/lib/useOptions";
import type { TrackView } from "@/lib/useTrack";
import { IdempotentButton } from "../common/IdempotentButton";
import { Icon } from "../common/Icon";
import { Skeleton } from "../common/States";
import { StatusIcon } from "../common/StatusIcon";
import { DemoBadge } from "./DemoBadge";

const DATE = /^\d{4}-\d{2}-\d{2}$/;
const ENDED = new Set(["BUYER_DECLINED", "NO_BIDS", "CANCELLED", "NOT_FINANCEABLE", "DISBURSEMENT_FAILED"]);
const RECOVERY_DONE = new Set(["CLOSED", "PAID", "SETTLED"]);

type Side = "available" | "in_progress" | "ended" | "paused" | "locked";

/**
 * What each option is, given the active track and the actions the server
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

/** The first sentence of a server reason, so a card holds one line, not a paragraph. */
function firstSentence(text: string): string {
  const m = /^.*?[.!?](\s|$)/.exec(text);
  return (m ? m[0] : text).trim();
}

function Status({ side }: { side: Side }) {
  const { t } = useT();
  if (side === "in_progress") return <StatusIcon size="sm" tone="info" icon="clock" label={t("options.in_progress")} />;
  if (side === "paused") return <StatusIcon size="sm" tone="warn" icon="clock" label={t("options.paused")} />;
  if (side === "locked") return <StatusIcon size="sm" tone="block" icon="lock" label={t("options.locked")} />;
  if (side === "ended") return <StatusIcon size="sm" tone="info" icon="block" label={t("options.ended")} />;
  return null;
}

/** One option: title, one number or one reason, one button. */
function Card({
  id,
  title,
  badge,
  side,
  dimmed,
  label,
  number,
  line,
  action,
  extra,
}: {
  id: string;
  title: string;
  badge?: ReactNode;
  side: Side;
  dimmed: boolean;
  label: string | null;
  number: ReactNode;
  line: string;
  action: ReactNode;
  extra?: ReactNode;
}) {
  return (
    <section
      id={id}
      aria-labelledby={`${id}-title`}
      className={`flex flex-col gap-3 rounded-xl border p-5 sm:p-6 ${dimmed ? "border-rule bg-paper-sunk" : "border-rule bg-paper-raised"}`}
    >
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h3 id={`${id}-title`} className="text-lg font-semibold tracking-[-0.01em] text-ink-950">
          {title}
        </h3>
        <span className="flex flex-wrap items-center gap-2">
          <Status side={side} />
          {badge}
        </span>
      </header>
      {label && <p className="text-sm text-ink-600">{label}</p>}
      <p className={`font-mono font-semibold tracking-tight ${dimmed ? "text-lg text-ink-600" : "text-2xl text-ink-950"}`}>{number}</p>
      <p className="text-sm text-ink-700">{line}</p>
      {extra}
      <div className="mt-auto pt-1">{action}</div>
    </section>
  );
}

/**
 * Two ways forward, side by side, each with one button. Never a "best" or
 * "recommended" mark: the server's `recommendation` is always null. Every
 * figure comes from GET /cases/{id}/options.
 */
export function ChoiceCard({ caseId, tracking, stage }: { caseId: string; tracking: TrackView; stage: Stage }) {
  const { t } = useT();
  const href = useHref();
  const router = useRouter();
  const search = useSearchParams();
  const [picked, setPicked] = useState<string | null>(null);
  const actions_ = useEarlyActions();
  const offline = tracking.source === "offline";
  const track = tracking.track;
  const actions = tracking.caseDetail?.available_actions ?? [];
  const view = useOptions(caseId, Boolean(tracking.caseDetail), picked, track?.version ?? null, search.get("options"));

  if (view.error && !view.options) {
    return (
      <p role="alert" className="flex items-start gap-2 text-sm text-ink-700">
        <Icon name="warn" className="mt-0.5 h-4 w-4 shrink-0 text-warn" />
        {t("options.error")} {t("options.retry_hint")}
      </p>
    );
  }
  if (!view.options) {
    return (
      <div aria-busy="true" className="grid gap-4 md:grid-cols-2">
        <span className="sr-only">{t("options.loading")}</span>
        <Skeleton className="h-52" />
        <Skeleton className="h-52" />
      </div>
    );
  }

  const o = view.options;
  const early = o.get_paid_early;
  const rec = o.recover_with_law;
  const s = sides(track, actions);
  const expected = picked ?? rec.expected_payment_date ?? "";
  const ind = early.indicative;
  const earlyOpen = s.early === "available" && early.available;
  const recOpen = s.recover === "available" && rec.available;

  // Starting recovery opens the first message, ready to send from your own app.
  const startRecoveryNow = async (opts: Parameters<typeof startRecovery>[2]) => {
    await startRecovery(caseId, stage, opts);
    simClear(caseId); // an ended demo financing track gives way to the real recovery one
    await tracking.refresh();
    router.push(stage === 4 ? href(`/case/${caseId}/pack`) : href(`/case/${caseId}`, { send: stage }));
  };
  const recoverButton = (label: MessageKey, primary: boolean) => (
    <IdempotentButton
      actionId={`recovery.start:${caseId}`}
      run={startRecoveryNow}
      version={track?.version ?? null}
      onConflict={tracking.refresh}
      offline={offline}
      className={primary ? "btn btn-primary" : "btn btn-secondary"}
    >
      {t(label)}
      <Icon name="arrow-right" className="h-4 w-4" />
    </IdempotentButton>
  );
  const continueLink = (to: string) => (
    <Link href={to} className="btn btn-primary">
      {t("options.continue")}
      <Icon name="arrow-right" className="h-4 w-4" />
    </Link>
  );

  let earlyLine = t("options.early.pitch");
  let earlyAction: ReactNode = null;
  if (s.early === "in_progress") earlyAction = continueLink(href(`/case/${caseId}/early`));
  else if (earlyOpen) {
    earlyAction = (
      <IdempotentButton
        actionId={`financing.start:${caseId}`}
        run={async (opts) => {
          await actions_.start(caseId, opts);
          await tracking.refresh();
          router.push(href(`/case/${caseId}/early`));
        }}
        version={track?.version ?? null}
        onConflict={tracking.refresh}
        offline={offline}
      >
        {t("options.early.cta")}
        <Icon name="arrow-right" className="h-4 w-4" />
      </IdempotentButton>
    );
  } else if (s.early === "locked") earlyLine = t("options.locked.early_in_recovery");
  else if (s.early === "paused") earlyLine = t("options.paused.early");
  else {
    // Not available: say why in one line, and make the other option one click away.
    earlyLine = early.unavailable_reasons?.[0] ? firstSentence(early.unavailable_reasons[0]) : t("options.ended.reason");
    if (s.recover === "available") earlyAction = recoverButton("options.recover.cta_instead", true);
  }

  let recLine = t("options.recover.pitch");
  let recAction: ReactNode = null;
  if (s.recover === "in_progress") recAction = continueLink(stage === 4 ? href(`/case/${caseId}/pack`) : href(`/case/${caseId}`, { send: stage }));
  else if (recOpen) recAction = recoverButton("options.recover.cta", !earlyOpen || false);
  else if (s.recover === "locked") recLine = t("options.locked.recovery_after_sign");
  else if (s.recover === "paused") recLine = t("options.paused.recovery");
  else if (rec.notes?.[0]) recLine = firstSentence(rec.notes[0]);

  return (
    <div className={`grid gap-4 md:grid-cols-2 ${view.loading ? "opacity-80" : ""}`} aria-busy={view.loading}>
      <Card
        id="option-early"
        title={t("options.early.title")}
        badge={<DemoBadge />}
        side={s.early}
        dimmed={!earlyOpen && s.early !== "in_progress"}
        label={ind && (earlyOpen || s.early === "in_progress") ? t("options.early.number_label") : null}
        number={
          ind && (earlyOpen || s.early === "in_progress")
            ? t("options.early.range", { low: money(ind.net_receivable_range.low), high: money(ind.net_receivable_range.high) })
            : t("options.early.na")
        }
        line={earlyLine}
        action={earlyAction}
      />
      <Card
        id="option-recover"
        title={t("options.recover.title")}
        side={s.recover}
        dimmed={!recOpen && s.recover !== "in_progress"}
        label={t("options.recover.number_label", { date: fmtDate(expected) })}
        number={money(rec.total_if_paid)}
        line={recLine}
        action={recAction}
        extra={
          recOpen ? (
            <details className="text-sm text-ink-700">
              <summary className="link cursor-pointer select-none">{t("options.change_date")}</summary>
              <label className="mt-2 flex flex-col gap-1">
                <span className="sr-only">{t("options.recover.date_label")}</span>
                <input
                  type="date"
                  className="field-input max-w-[12rem] font-mono"
                  value={expected}
                  onChange={(e) => setPicked(DATE.test(e.target.value) ? e.target.value : null)}
                />
              </label>
            </details>
          ) : null
        }
      />
    </div>
  );
}
