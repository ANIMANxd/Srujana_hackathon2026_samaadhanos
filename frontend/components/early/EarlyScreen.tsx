"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState, type ReactNode } from "react";
import { cancelFinancing, getEsignSession, getPayout, listBids, startFinancing, startRecovery } from "@/lib/api";
import { currentStage } from "@/lib/derive";
import { EARLY_STEPS, earlyView, stepIndex, type EarlyStep } from "@/lib/earlyFlow";
import { useT } from "@/lib/i18n";
import type { MessageKey } from "@/lib/i18n/en";
import { useHref } from "@/lib/params";
import { useEvaluation } from "@/lib/useEvaluation";
import { useOptions } from "@/lib/useOptions";
import { useRead } from "@/lib/useRead";
import { CaseHeader } from "../case/CaseHeader";
import { TrackStrip } from "../case/TrackStrip";
import { Icon } from "../common/Icon";
import { IdempotentButton } from "../common/IdempotentButton";
import { CaseSkeleton, ErrorState, NotFoundState } from "../common/States";
import { StatusIcon } from "../common/StatusIcon";
import { DemoBadge } from "../options/DemoBadge";
import { Banner } from "../shell/Banners";
import { AskBuyer } from "./AskBuyer";
import { BidList } from "./BidList";
import { ESignModal } from "./ESignModal";
import { LockedNotice } from "./LockedNotice";
import { SettlementStatus } from "./SettlementStatus";

type StepStatus = "done" | "now" | "later" | "stopped";

/**
 * /case/[id]/early: the Get-paid-early stepper. Which step is "now" comes only
 * from the server's track.state (via useTrack, live over the stream or a 3 s
 * poll). A button here asks the server to do something and then re-reads; no
 * click, timer or response moves a step on its own.
 */
export function EarlyScreen({ caseId }: { caseId: string }) {
  const { t } = useT();
  const href = useHref();
  const router = useRouter();
  const search = useSearchParams();
  const ev = useEvaluation(caseId);
  const tracking = ev.tracking;
  const [signOpen, setSignOpen] = useState(false);
  const [signedWaiting, setSignedWaiting] = useState(false);

  const detail = tracking?.caseDetail ?? null;
  const track = tracking?.track ?? null;
  const state = track?.kind === "FINANCING" ? track.state : null;
  const view = earlyView(state);
  const actions = detail?.available_actions ?? [];
  const offline = tracking?.source === "offline";
  const version = tracking?.version ?? null;
  const refresh = tracking?.refresh ?? (async () => {});
  const readKey = `${caseId}:${version ?? "-"}`;

  const bidsOn = state === "BIDS_AVAILABLE" || state === "AWAITING_ESIGN";
  const bids = useRead(`bids:${readKey}`, bidsOn, () => listBids(caseId));
  const esign = useRead(`esign:${readKey}`, state === "AWAITING_ESIGN", () => getEsignSession(caseId));
  const payoutOn = state === "DISBURSED" || state === "SETTLED" || state === "SETTLED_WITHOUT_RECOURSE" || state === "AWAITING_DISBURSEMENT";
  const payout = useRead(`payout:${readKey}`, payoutOn, () => getPayout(caseId));
  const options = useOptions(caseId, view.failure === "NOT_FINANCEABLE", null, version, search.get("options"));

  if (ev.status === "not_found") return <NotFoundState />;

  const back = (
    <Link href={href(`/case/${caseId}`)} className="link inline-flex items-center gap-1 text-sm">
      <Icon name="arrow-left" className="h-4 w-4" />
      {t("early.back")}
    </Link>
  );

  const shell = (body: ReactNode) => (
    <div className="flex flex-col gap-6">
      <CaseHeader caseId={caseId} request={ev.request} response={ev.response} showViewToggle={false} />
      {back}
      {body}
    </div>
  );

  if (!tracking) return shell(ev.status === "loading" ? <CaseSkeleton /> : <EmptyNote text={t("early.not_started")} />);
  if (tracking.status === "error" && !detail) return shell(<ErrorState message={tracking.error ?? t("state.error_title")} onRetry={ev.retry} />);
  if (!detail) return shell(<CaseSkeleton />);
  if (track?.kind === "RECOVERY") return shell(<EmptyNote text={t("early.recovery_active")} />);

  const invoiceNo = detail.case.invoice_no;
  const dueDate = detail.latest_evaluation?.timeline?.due_date ?? null;
  const selectedBid = bids.data?.find((b) => b.status === "SELECTED") ?? null;
  const goOption2 = () => router.push(href(`/case/${caseId}`, { tab: "escalation" }));

  function statusOf(step: EarlyStep): StepStatus {
    const i = stepIndex(step);
    if (view.failure) {
      if (view.stoppedAt === null) return "later";
      const at = stepIndex(view.stoppedAt);
      return i < at ? "done" : i === at ? "stopped" : "later";
    }
    if (view.finished) return "done";
    const cur = view.current ? stepIndex(view.current) : 0;
    return i < cur ? "done" : i === cur ? "now" : "later";
  }

  const bodyOf = (step: EarlyStep): ReactNode => {
    const st = statusOf(step);
    if (step === "check") {
      if (state === null) {
        return (
          <IdempotentButton
            actionId={`financing.start:${caseId}`}
            run={async (opts) => {
              await startFinancing(caseId, opts);
              await refresh();
            }}
            onConflict={refresh}
            offline={offline}
          >
            {t("early.check.start")}
          </IdempotentButton>
        );
      }
      if (view.failure === "NOT_FINANCEABLE") {
        const reasons = options.options?.get_paid_early.unavailable_reasons ?? [];
        return (
          <div className="flex flex-col gap-2 text-sm text-ink-800">
            <p className="font-medium">{t("early.check.fail_title")}</p>
            <ul className="list-disc space-y-1 pl-5">
              {reasons.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
          </div>
        );
      }
      return st === "done" ? <p className="text-sm text-ink-700">{t("early.check.ok")}</p> : null;
    }
    if (step === "ask" && (st === "now" || st === "stopped")) {
      if (st === "stopped") return null;
      return (
        <AskBuyer
          caseId={caseId}
          invoiceNo={invoiceNo}
          canRequest={actions.includes("request_buyer_acceptance")}
          waiting={state === "AWAITING_BUYER_ACCEPTANCE"}
          version={version}
          offline={offline}
          onConflict={refresh}
        />
      );
    }
    if (step === "bid" && st === "now") {
      if (state === "BIDDING_OPEN") {
        return (
          <div role="status" aria-live="polite" className="flex flex-col gap-1">
            <StatusIcon tone="info" icon="clock" label={t("early.bid.waiting")} />
            <span className="text-xs text-ink-500">{t("early.bid.waiting_hint")}</span>
          </div>
        );
      }
      if (!bids.data) return <p className="text-sm text-ink-500">{t("early.bid.loading")}</p>;
      return <BidList caseId={caseId} bids={bids.data} version={version} offline={offline} onConflict={refresh} onSelected={refresh} />;
    }
    if (step === "sign" && st === "now") {
      return (
        <div className="flex flex-col gap-3">
          <p className="text-sm text-ink-700">{t("early.sign.intro")}</p>
          {signedWaiting && (
            <div role="status" aria-live="polite">
              <StatusIcon tone="info" icon="clock" label={t("early.sign.waiting")} />
            </div>
          )}
          <div className="flex flex-wrap items-start gap-3">
            <button type="button" className="btn btn-primary" disabled={signedWaiting} onClick={() => setSignOpen(true)}>
              {t("early.sign.open")}
            </button>
            {actions.includes("cancel_financing") && (
              <IdempotentButton
                actionId={`financing.cancel:${caseId}`}
                run={async (opts) => {
                  await cancelFinancing(caseId, opts);
                  await refresh();
                }}
                version={version}
                onConflict={refresh}
                offline={offline}
                className="btn btn-quiet"
              >
                {t("early.cancel")}
              </IdempotentButton>
            )}
          </div>
        </div>
      );
    }
    if (step === "money" && st === "now") return <SettlementStatus payout={payout.data} />;
    if (step === "done" && st === "done") {
      return (
        <div className="flex flex-col gap-4">
          <SettlementStatus payout={payout.data} />
          <LockedNotice dueDate={dueDate} />
        </div>
      );
    }
    return null;
  };

  return shell(
    <>
      <TrackStrip tracking={tracking} />
      {offline && <Banner tone="warn" icon="lock" message="early.offline" />}
      <header className="flex flex-col gap-1">
        <h2 className="text-xl font-semibold tracking-[-0.015em] text-ink-950">{t("early.title")}</h2>
        <p className="text-sm text-ink-600">{t("early.intro")}</p>
      </header>
      <Banner tone="warn" icon="info" message="early.demo_banner" />

      {view.failure && (
        <section role="status" className="panel flex flex-col gap-3 p-5">
          <p className="flex items-start gap-2 text-sm text-ink-800">
            <Icon name="info" className="mt-0.5 h-4 w-4 shrink-0 text-ink-600" />
            {t(`early.fail.${view.failure}` as MessageKey)}
          </p>
          {(actions.includes("switch_to_recovery") || view.failure === "NOT_FINANCEABLE" || view.failure === "CANCELLED") &&
            view.failure !== "DISBURSEMENT_FAILED" && (
              <div>
                <IdempotentButton
                  actionId={`recovery.switch:${caseId}`}
                  run={async (opts) => {
                    await startRecovery(caseId, ev.response ? currentStage(ev.response) : 1, opts);
                    await refresh();
                    goOption2();
                  }}
                  version={version}
                  onConflict={refresh}
                  offline={offline}
                >
                  {t("early.switch")}
                </IdempotentButton>
              </div>
            )}
        </section>
      )}

      {/* Tells a screen reader which step the server says is current, without moving focus. */}
      <p className="sr-only" role="status" aria-live="polite">
        {view.finished
          ? t("early.stepper.finished", { total: EARLY_STEPS.length })
          : view.failure && view.stoppedAt
            ? t("early.stepper.stopped", { n: stepIndex(view.stoppedAt) + 1, total: EARLY_STEPS.length, title: t(`early.step.${view.stoppedAt}` as MessageKey) })
            : view.current
              ? t("early.stepper.now", { n: stepIndex(view.current) + 1, total: EARLY_STEPS.length, title: t(`early.step.${view.current}` as MessageKey) })
              : ""}
      </p>
      <ol aria-label={t("early.stepper")} className="flex flex-col gap-3">
        {EARLY_STEPS.map((step, n) => {
          const st = statusOf(step);
          const body = bodyOf(step);
          return (
            <li
              key={step}
              aria-current={st === "now" ? "step" : undefined}
              className={`panel flex flex-col gap-3 p-4 sm:p-5 ${st === "later" ? "bg-paper-sunk text-ink-600" : ""}`}
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h3 className="section-title flex items-center gap-2">
                  <span className="font-mono text-xs text-ink-500" aria-hidden="true">{n + 1}</span>
                  {t(`early.step.${step}` as MessageKey)}
                  <span className="sr-only">{t("early.step_of", { n: n + 1, total: EARLY_STEPS.length })}</span>
                </h3>
                <span className="flex flex-wrap items-center gap-2">
                  <StepStatusPill status={st} />
                  <DemoBadge />
                </span>
              </div>
              {body}
            </li>
          );
        })}
      </ol>

      {state === "AWAITING_ESIGN" && (
        <ESignModal
          open={signOpen}
          onClose={() => setSignOpen(false)}
          onSigned={() => {
            setSignOpen(false);
            setSignedWaiting(true);
          }}
          supplierName={ev.request?.supplier.name ?? ""}
          buyerName={ev.request?.buyer.name ?? ""}
          caseId={caseId}
          invoiceNo={invoiceNo}
          acceptedAmount={detail.case.accepted_amount}
          bid={selectedBid}
          session={esign.data}
          version={version}
          offline={offline}
          onConflict={refresh}
        />
      )}
    </>,
  );
}

function EmptyNote({ text }: { text: string }) {
  return <p className="panel p-5 text-sm text-ink-700">{text}</p>;
}

function StepStatusPill({ status }: { status: StepStatus }) {
  const { t } = useT();
  const label = t(`early.status.${status}` as MessageKey);
  if (status === "done") return <StatusIcon size="sm" tone="ok" label={label} />;
  if (status === "now") return <StatusIcon size="sm" tone="info" icon="clock" label={label} />;
  if (status === "stopped") return <StatusIcon size="sm" tone="warn" icon="block" label={label} />;
  return <StatusIcon size="sm" tone="info" icon="lock" label={label} />;
}
