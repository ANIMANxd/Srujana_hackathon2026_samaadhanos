"use client";

import Link from "next/link";
import { useSendLog } from "@/lib/caseStore";
import { isNotCovered, isPlaceholder } from "@/lib/derive";
import { useT } from "@/lib/i18n";
import { useHref, useUrlState } from "@/lib/params";
import { useConfig } from "@/lib/useConfig";
import { useEvaluation } from "@/lib/useEvaluation";
import { CaseSkeleton, ErrorState, NotFoundState } from "../common/States";
import { StatusIcon } from "../common/StatusIcon";
import { DataBanners } from "../shell/Banners";
import { JudgeConsole } from "../shell/JudgeConsole";
import { CfoCostLines } from "../cfo/CfoCostLines";
import { AssumptionsDrawer } from "./AssumptionsDrawer";
import { CaseHeader } from "./CaseHeader";
import { EscalationLadder } from "./EscalationLadder";
import { GuidanceCard } from "./GuidanceCard";
import { LimitationCard } from "./LimitationCard";
import { MoneyCard } from "./MoneyCard";
import { NotCovered } from "./NotCovered";
import { StatuteTimeline } from "./StatuteTimeline";

/** The hero screen (frontend-structure §2): guidance, timeline, money, next step. */
export function CaseScreen({ caseId }: { caseId: string }) {
  const { t } = useT();
  const href = useHref();
  const { view } = useUrlState();
  const ev = useEvaluation(caseId);
  const cfg = useConfig();
  const log = useSendLog(caseId);

  const judge =
    ev.request && ev.base ? { request: ev.request, base: ev.base, setRequest: ev.setRequest, reset: ev.reset } : null;

  if (ev.status === "not_found") return <NotFoundState />;

  const res = ev.response;
  const placeholder = isPlaceholder(res);

  return (
    <div className="flex flex-col gap-6">
      <CaseHeader caseId={caseId} request={ev.request} response={res} showViewToggle={Boolean(res && !isNotCovered(res))} />
      <DataBanners offline={ev.source === "offline"} placeholder={placeholder} needsBackend={ev.status === "needs_backend"} />
      {ev.error && res && <ErrorState message={ev.error} onRetry={ev.retry} />}

      {ev.status === "loading" && !res && <CaseSkeleton />}
      {ev.status === "error" && !res && <ErrorState message={ev.error ?? t("state.error_title")} onRetry={ev.retry} />}
      {ev.status === "needs_backend" && (
        <div className="flex flex-wrap gap-3">
          {ev.isEdited && (
            <button type="button" className="btn btn-secondary" onClick={ev.reset}>
              {t("judge.reset")}
            </button>
          )}
          <button type="button" className="btn btn-secondary" onClick={ev.retry}>
            {t("state.retry")}
          </button>
        </div>
      )}

      {res && ev.request && ev.status !== "needs_backend" && (
        <div className={`flex flex-col gap-6 ${ev.refreshing ? "opacity-80 transition-opacity" : ""}`} aria-busy={ev.refreshing}>
          {isNotCovered(res) ? (
            <NotCovered request={ev.request} response={res} />
          ) : view === "cfo" ? (
            <CfoCostLines request={ev.request} response={res} placeholder={placeholder} onChangeRequest={ev.setRequest} />
          ) : (
            <>
              {res.jurisdiction.status === "INSUFFICIENT_DATA" && (
                <p className="flex flex-wrap items-center gap-2 text-sm text-ink-700">
                  <StatusIcon size="sm" tone="warn" label={t("eligibility.INSUFFICIENT_DATA")} />
                  {t("eligibility.unconfirmed_note")}
                  <Link href={href(`/eligibility/${caseId}`)} className="btn btn-quiet min-h-0 text-sm">
                    {t("eligibility.see_why")}
                  </Link>
                </p>
              )}
              <GuidanceCard caseId={caseId} request={ev.request} response={res} config={cfg.config} placeholder={placeholder} />
              <StatuteTimeline response={res} />
              <div className="grid gap-6 lg:grid-cols-[3fr_2fr]">
                <MoneyCard response={res} placeholder={placeholder} />
                <div className="flex flex-col gap-6">
                  <LimitationCard limitation={res.limitation} />
                  <AssumptionsDrawer response={res} config={cfg.config} configLoading={cfg.loading} configIsStub={cfg.isStub} />
                </div>
              </div>
              <EscalationLadder caseId={caseId} response={res} log={log} />
            </>
          )}
        </div>
      )}

      <JudgeConsole current={judge} />
    </div>
  );
}
